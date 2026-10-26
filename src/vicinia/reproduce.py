"""Regenerate every table and figure in results/ from fixed seeds."""

from __future__ import annotations

import copy
import glob
import json
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import experiments as ex
from . import figures, html, scenario
from .ledger import Ledger

BASELINES = ["baseline_lagos", "baseline_abuja", "baseline_kano"]
SEEDS = [42, 101, 202, 303, 404]
STRESS = [
    "stress_blackout_72h",
    "stress_harmattan_week",
    "stress_contributor_dropout",
    "stress_feeder_halved",
    "stress_comm_loss",
]


def _round(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if out[c].dtype.kind == "f":
            out[c] = out[c].round(3)
    return out


def tamper_demo(led: Ledger) -> dict:
    """Alter one entry in a copy of the ledger and check that verify() catches it."""
    if not led.entries:
        return {"entries": 0, "verified": led.verify(), "tamper_detected": None}
    t = Ledger(led.price_ngn_per_kwh, list(led.entries), list(led.hashes))
    i = len(t.entries) // 2
    e = copy.copy(t.entries[i])
    e.kwh_received += 0.01
    t.entries[i] = e
    return {
        "entries": len(led.entries),
        "head_hash": led.head,
        "verified": led.verify(),
        "tampered_index": i,
        "tamper_detected": not t.verify(),
        "first_invalid_after_tamper": t.first_invalid(),
    }


def run(root: str | Path = ".", out: str | Path = "results", quick: bool = False, log=print) -> dict:
    root = Path(root)
    out = Path(out)
    figdir = out / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    days_base = 28 if quick else None
    days_stress = None
    t_all = time.perf_counter()
    summary: dict = {"quick": quick}

    # 1. Baseline strategy comparison per site.
    frames = []
    lagos = None
    for name in BASELINES:
        cfg = scenario.load(root / "scenarios" / f"{name}.yaml")
        t0 = time.perf_counter()
        b = scenario.build(cfg, days=days_base)
        build_s = time.perf_counter() - t0
        df, res = ex.compare(b)
        df["build_s"] = build_s
        frames.append(df)
        log(f"{name}: done in {time.perf_counter() - t0:.1f} s")
        if name == "baseline_lagos":
            lagos = (b, res, build_s)
    base = pd.concat(frames, ignore_index=True)
    _round(base).to_csv(out / "baseline_comparison.csv", index=False)

    # 2. Runtime for the one-year, 50-household Lagos run.
    b, res, build_s = lagos
    rt = pd.DataFrame(
        [
            {
                "scenario": "baseline_lagos",
                "days": len(b.inputs.times) * b.inputs.dt_h / 24,
                "households": b.fleet.n,
                "intervals": len(b.inputs.times),
                "run": k,
                "runtime_s": round(v.runtime_s, 2),
                "input_build_s": round(build_s, 2),
                "ledger_entries": len(v.ledger.entries),
            }
            for k, v in res.items()
            if k in ("S0", "S1", "S2")
        ]
    )
    rt["machine"] = f"{platform.machine()} {platform.python_implementation()} {platform.python_version()}"
    rt.to_csv(out / "runtime.csv", index=False)

    # 3. Ledger outputs for Lagos S2.
    r2 = res["S2"]
    day = np.asarray((b.inputs.times.normalize() - b.inputs.times[0].normalize()).days)
    r2.ledger.statements(b.fleet.n).assign(archetype=b.fleet.archetype).to_csv(
        out / "ledger_statements_lagos_S2.csv", index=False
    )
    net = r2.ledger.netting(b.fleet.n, day)
    net.to_csv(out / "ledger_daily_netting_lagos_S2.csv", index=False)
    r2.ledger.to_frame().head(200).to_csv(out / "ledger_sample_lagos_S2.csv", index=False)
    led_sum = tamper_demo(r2.ledger)
    led_sum["daily_netting_max_abs_kobo"] = int(net.groupby("period")["net_kobo"].sum().abs().max()) if len(net) else 0
    (out / "ledger_check_lagos_S2.json").write_text(json.dumps(led_sum, indent=2) + "\n")
    log(f"ledger: {led_sum['entries']} entries, verified={led_sum['verified']}, tamper detected={led_sum['tamper_detected']}")

    # Fleet description.
    f = b.fleet
    pd.DataFrame(
        {
            "household": np.arange(f.n),
            "archetype": f.archetype,
            "pv_kwp": f.pv_kwp,
            "battery_kwh": f.batt_kwh,
            "battery_kw": f.batt_kw,
            "generator_kw": f.gen_kw,
            "crit_kwh_day": b.inputs.crit_kw.sum(axis=1) * b.inputs.dt_h / (len(b.inputs.times) * b.inputs.dt_h / 24),
            "noncrit_kwh_day": b.inputs.nonc_kw.sum(axis=1) * b.inputs.dt_h / (len(b.inputs.times) * b.inputs.dt_h / 24),
        }
    ).round(3).to_csv(out / "fleet_lagos.csv", index=False)

    # 4. Figures for the baseline.
    figures.coverage_lagos(base, figdir / "coverage_lagos.png")
    figures.household_coverage(res, figdir / "household_coverage_lagos.png")
    start = int(b.inputs.times.searchsorted(pd.Timestamp("2026-01-12", tz=b.inputs.times.tz))) if not quick else 0
    figures.week_timeseries(res, start, figdir / "week_lagos.png", "One week in Lagos (12 to 18 January)")

    # 5. Pressure tests.
    sframes = []
    blackout = None
    for name in STRESS:
        cfg = scenario.load(root / "scenarios" / f"{name}.yaml")
        df, res_s, res_c = ex.stress_test(cfg, days=days_stress)
        sframes.append(df)
        if name == "stress_blackout_72h":
            blackout = (res_s, scenario.build(cfg).window)
        log(f"{name}: done")
    stress = pd.concat(sframes, ignore_index=True)
    _round(stress).to_csv(out / "stress_tests.csv", index=False)
    figures.stress_overview(stress, figdir / "stress_tests.png")
    figures.blackout_detail(blackout[0], blackout[1], figdir / "blackout_72h.png")

    # 6. Sensitivity of S2.
    cfg = scenario.load(root / "scenarios" / "baseline_lagos.yaml")
    sens = ex.sensitivity(cfg, days=days_base)
    _round(sens).to_csv(out / "sensitivity_lagos_S2.csv", index=False)
    figures.sensitivity(sens, figdir / "sensitivity_lagos.png")
    figures.defaults_sweep(sens, figdir / "defaults_sweep_lagos.png")
    choices = ex.defaults_comparison(b, res["S0"])
    _round(choices).to_csv(out / "defaults_comparison_lagos.csv", index=False)
    log("sensitivity: done")

    # 7. Seed-to-seed variation for Lagos.
    seeds = ex.seed_sweep(cfg, SEEDS[:2] if quick else SEEDS, days=days_base)
    _round(seeds).to_csv(out / "seed_variation_lagos.csv", index=False)
    log("seed sweep: done")

    # 8. Robustness of the chosen S2 defaults across seeds and pressure tests.
    rob_cfgs = [cfg] + [scenario.load(root / "scenarios" / f"{n}.yaml") for n in STRESS]
    # The quick run skips the year-long baseline here to stay fast.
    rob = ex.robustness(rob_cfgs[1:], SEEDS[:2]) if quick else ex.robustness(rob_cfgs, SEEDS)
    _round(rob).to_csv(out / "robustness_S2.csv", index=False)
    log("robustness: done")

    summary["total_s"] = time.perf_counter() - t_all
    extra = {"seeds": seeds, "rob": rob, "choices": choices, "prices": cfg["prices"]}
    html.write_report_md(out, base, stress, sens, rt, led_sum, quick, **extra)
    html.write_report_html(out, base, stress, sens, rt, led_sum, quick, **extra)
    log(f"reproduce finished in {summary['total_s']:.0f} s; outputs in {out}")
    return summary


def available_scenarios(root: str | Path = ".") -> list[str]:
    return sorted(Path(p).stem for p in glob.glob(str(Path(root) / "scenarios" / "*.yaml")))
