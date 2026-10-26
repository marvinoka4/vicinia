"""Strategy comparisons, pressure tests and sensitivity runs."""

from __future__ import annotations

import copy
import dataclasses
import time

import numpy as np
import pandas as pd

from . import metrics, scenario
from .engine import Fleet, SimResult, simulate

# S2-local is an ablation: the S2 battery reserve policy with sharing switched
# off. It separates the effect of the reserve from the effect of sharing.
# S2-pv-only switches off sharing of battery energy above the donor reserve.
STRATEGY_RUNS = ("S0", "S1", "S2", "S2-local", "S2-pv-only")


def run_one(b: scenario.Built, name: str, record: bool = False, window: slice | None = None, **over) -> SimResult:
    inp = b.inputs
    strategy = name
    if name == "S2-local":
        strategy = "S2"
        inp = dataclasses.replace(inp, comm_on=np.zeros_like(inp.comm_on))
    elif name == "S2-pv-only":
        strategy = "S2"
        over = {"share_battery": False, **over}
    p = b.params(strategy, **over)
    win = window if window is not None else b.window
    t0 = time.perf_counter()
    r = simulate(inp, b.fleet, p, record=record, window=win)
    r.runtime_s = time.perf_counter() - t0
    r.extra["name"] = name
    r.extra["window"] = win
    return r


def pooled_reference(b: scenario.Built) -> SimResult:
    """Whole neighbourhood as one lossless household with no feeder limit.

    PV and batteries are pooled, generators are excluded, and batteries serve
    only critical load. Its critical coverage is what the installed PV and
    storage could deliver to critical load with perfect, free sharing. Dispatch
    is myopic, so this is a reference point, not a proven upper bound.
    Compare it with crit_coverage_no_gen_pct of the strategies.
    """
    f = b.fleet
    cap = f.batt_kwh
    w = cap / cap.sum() if cap.sum() > 0 else np.ones_like(cap) / len(cap)
    one = lambda v: np.array([v])  # noqa: E731
    fleet = Fleet(
        archetype=one("pooled"),
        pv_kwp=one(f.pv_kwp.sum()),
        batt_kwh=one(cap.sum()),
        batt_kw=one(f.batt_kw.sum()),
        gen_kw=one(0.0),
        batt_eff_rt=one(float((f.batt_eff_rt * w).sum())),
        batt_min_soc=one(float((f.batt_min_soc * w).sum())),
        batt_init_soc=one(float((f.batt_init_soc * w).sum())),
        grid_charge_soc=one(float((f.grid_charge_soc * w).sum())),
    )
    inp = dataclasses.replace(
        b.inputs,
        crit_kw=b.inputs.crit_kw.sum(axis=0, keepdims=True),
        nonc_kw=b.inputs.nonc_kw.sum(axis=0, keepdims=True),
        connected=np.ones((1, len(b.inputs.times)), dtype=bool),
    )
    p = b.params("S2", reserve_soc=1.0, loss_fraction=0.0)
    t0 = time.perf_counter()
    r = simulate(inp, fleet, p, window=b.window)
    r.runtime_s = time.perf_counter() - t0
    r.extra["name"] = "pooled-ref"
    r.extra["window"] = b.window
    return r


def compare(b: scenario.Built, runs=STRATEGY_RUNS, with_pooled: bool = True) -> tuple[pd.DataFrame, dict[str, SimResult]]:
    results = {name: run_one(b, name) for name in runs}
    ref = results.get("S0")
    rows = []
    for name, r in results.items():
        row = {"scenario": b.cfg["name"], "run": name}
        row.update(metrics.summarize(r, ref))
        rows.append(row)
    if with_pooled:
        pr = pooled_reference(b)
        results["pooled-ref"] = pr
        h = pr.hh
        rows.append(
            {
                "scenario": b.cfg["name"],
                "run": "pooled-ref",
                "strategy": "pooled",
                "households": b.fleet.n,
                "crit_coverage_outage_pct": 100 * h["out_crit_served_kwh"].sum() / max(h["out_crit_load_kwh"].sum(), 1e-12),
                "crit_coverage_no_gen_pct": 100 * h["out_crit_served_kwh"].sum() / max(h["out_crit_load_kwh"].sum(), 1e-12),
                "runtime_s": pr.runtime_s,
            }
        )
    return pd.DataFrame(rows), results


def without_events(cfg: dict) -> dict:
    c = copy.deepcopy(cfg)
    c["events"] = []
    c["name"] = cfg["name"] + "_control"
    return c


def stress_test(cfg: dict, days: int | None = None) -> tuple[pd.DataFrame, dict[str, SimResult], dict[str, SimResult]]:
    """Run a stress scenario and its event-free control over the same window."""
    b = scenario.build(cfg, days=days)
    df, res = compare(b)
    bc = scenario.build(without_events(cfg), days=days)
    bc.window = b.window
    dfc, resc = compare(bc)
    df["case"] = "stress"
    dfc["case"] = "control"
    out = pd.concat([df, dfc], ignore_index=True)
    out["scenario"] = cfg["name"]
    return out, res, resc


def sensitivity(cfg: dict, days: int | None = None) -> pd.DataFrame:
    """One-at-a-time sweeps of feeder capacity, losses and battery reserve for S2."""
    b = scenario.build(cfg, days=days)
    s0 = run_one(b, "S0")
    rows = []
    sweeps = {
        "feeder_kw": [5.0, 10.0, 25.0, 50.0, 100.0],
        "loss_fraction": [0.0, 0.05, 0.10, 0.20],
        "reserve_soc": [0.2, 0.3, 0.4, 0.5, 0.65, 0.8],
        "battery_settlement_ngn_per_kwh": [600.0, 900.0, 1200.0, 1500.0],
    }
    for param, values in sweeps.items():
        for v in values:
            if param == "feeder_kw":
                bb = dataclasses.replace(b, inputs=dataclasses.replace(b.inputs, feeder_kw=np.full_like(b.inputs.feeder_kw, v)))
                r = run_one(bb, "S2")
            else:
                r = run_one(b, "S2", **{param: v})
            m = metrics.summarize(r, s0)
            rows.append({"parameter": param, "value": v, **m})
    return pd.DataFrame(rows)


def seed_sweep(cfg: dict, seeds, days: int | None = None) -> pd.DataFrame:
    """Repeat S0, S1 and S2 with different seeds (new fleet, loads, weather and grid)."""
    frames = []
    for s in seeds:
        b = scenario.build(dict(cfg, seed=int(s)), days=days)
        df, _ = compare(b, runs=("S0", "S1", "S2"), with_pooled=False)
        df["seed"] = int(s)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)
