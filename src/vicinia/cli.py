"""Command line interface.

vicinia simulate --scenario scenarios/baseline_lagos.yaml [--strategy S2]
vicinia compare  [--scenario scenarios/baseline_lagos.yaml]
vicinia reproduce [--quick] [--out results]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from . import experiments as ex
from . import metrics, scenario

SHOW = [
    "run",
    "crit_coverage_outage_pct",
    "crit_coverage_no_gen_pct",
    "worst_household_crit_coverage_pct",
    "gen_runtime_h",
    "fuel_l",
    "co2_kg",
    "mean_household_cost_ngn",
    "shared_delivered_kwh",
    "ledger_entries",
    "runtime_s",
]


def _print(df: pd.DataFrame) -> None:
    cols = [c for c in SHOW if c in df.columns]
    with pd.option_context("display.width", 200, "display.max_columns", 30, "display.float_format", "{:,.1f}".format):
        print(df[cols].to_string(index=False))


def cmd_simulate(a) -> int:
    cfg = scenario.load(a.scenario)
    b = scenario.build(cfg, days=a.days)
    r = ex.run_one(b, a.strategy)
    ref = ex.run_one(b, "S0") if a.strategy != "S0" else r
    m = metrics.summarize(r, ref)
    print(f"scenario {cfg['name']}: {b.fleet.n} households, {len(b.inputs.times)} intervals, strategy {a.strategy}")
    for k, v in m.items():
        print(f"  {k:36s} {v:,.3f}" if isinstance(v, float) else f"  {k:36s} {v}")
    print(f"  {'ledger_verified':36s} {r.ledger.verify()}")
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        r.ledger.to_frame().to_csv(out / f"{cfg['name']}_{a.strategy}_ledger.csv", index=False)
        r.ledger.statements(b.fleet.n).to_csv(out / f"{cfg['name']}_{a.strategy}_statements.csv", index=False)
        pd.DataFrame([m]).to_csv(out / f"{cfg['name']}_{a.strategy}_summary.csv", index=False)
        print(f"wrote ledger, statements and summary to {out}")
    return 0


def cmd_compare(a) -> int:
    cfg = scenario.load(a.scenario)
    b = scenario.build(cfg, days=a.days)
    df, _ = ex.compare(b)
    print(f"scenario {cfg['name']}: {b.fleet.n} households, {len(b.inputs.times)} intervals")
    _print(df)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(a.out, index=False)
        print(f"wrote {a.out}")
    return 0


def cmd_reproduce(a) -> int:
    from . import reproduce

    reproduce.run(root=a.root, out=a.out, quick=a.quick)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="vicinia", description="Neighbourhood solar sharing simulator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("simulate", help="run one strategy on a scenario")
    s.add_argument("--scenario", required=True)
    s.add_argument("--strategy", default="S2", choices=list(ex.STRATEGY_RUNS))
    s.add_argument("--days", type=int, default=None, help="override scenario length")
    s.add_argument("--out", default=None, help="directory for ledger and statements CSV")
    s.set_defaults(func=cmd_simulate)

    c = sub.add_parser("compare", help="compare all strategies on a scenario")
    c.add_argument("--scenario", default="scenarios/baseline_lagos.yaml")
    c.add_argument("--days", type=int, default=None)
    c.add_argument("--out", default=None, help="CSV path for the comparison table")
    c.set_defaults(func=cmd_compare)

    r = sub.add_parser("reproduce", help="regenerate results/ from fixed seeds")
    r.add_argument("--root", default=".")
    r.add_argument("--out", default="results")
    r.add_argument("--quick", action="store_true", help="short smoke run")
    r.set_defaults(func=cmd_reproduce)

    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
