"""Pressure tests: the system degrades gracefully and never does worse than islanded."""

from pathlib import Path

import numpy as np
import pytest

from vicinia import experiments as ex
from vicinia import scenario

SCEN = Path(__file__).resolve().parents[1] / "scenarios"
NAMES = [
    "stress_blackout_72h",
    "stress_harmattan_week",
    "stress_contributor_dropout",
    "stress_feeder_halved",
    "stress_comm_loss",
]


@pytest.fixture(scope="module", params=NAMES)
def stressed(request):
    cfg = scenario.load(SCEN / f"{request.param}.yaml")
    df, res, resc = ex.stress_test(cfg)
    return request.param, df, res, resc


def _m(df, case, run, col="crit_coverage_outage_pct"):
    return float(df[(df.case == case) & (df.run == run)][col].iloc[0])


def test_sharing_never_worse_than_islanded_under_stress(stressed):
    name, df, res, _ = stressed
    for run in ("S1", "S2"):
        assert _m(df, "stress", run) >= _m(df, "stress", "S0") - 1e-9, (name, run)
    assert _m(df, "stress", "S2", "worst_household_crit_coverage_pct") >= _m(df, "stress", "S0", "worst_household_crit_coverage_pct")


def test_stress_does_not_improve_on_control(stressed):
    name, df, _, _ = stressed
    for run in ("S0", "S1", "S2"):
        assert _m(df, "stress", run) <= _m(df, "control", run) + 0.5, (name, run)


def test_ledger_valid_under_stress(stressed):
    _, _, res, _ = stressed
    for run in ("S1", "S2"):
        assert res[run].ledger.verify()


def test_islanded_unaffected_by_sharing_only_events(stressed):
    name, df, _, _ = stressed
    if name in ("stress_contributor_dropout", "stress_feeder_halved", "stress_comm_loss"):
        assert _m(df, "stress", "S0") == pytest.approx(_m(df, "control", "S0"))


def test_comm_loss_falls_back_to_islanded():
    cfg = scenario.load(SCEN / "stress_comm_loss.yaml")
    b = scenario.build(cfg)
    r2 = ex.run_one(b, "S2")
    local = ex.run_one(b, "S2-local")
    w = b.window
    # No transfers or ledger entries while communication is down.
    assert np.allclose(r2.ts["shared_sent_kwh"][w], 0)
    assert not any(w.start <= e.interval < w.stop for e in r2.ledger.entries)
    # Each home falls back to its local policy and does no worse than S0.
    r0 = ex.run_one(b, "S0")
    assert r2.hh["out_crit_served_kwh"].sum() >= r0.hh["out_crit_served_kwh"].sum() - 1e-9
    s1 = ex.run_one(b, "S1")
    assert np.allclose(s1.ts["shared_sent_kwh"][w], 0)
    assert local.ledger.entries == []


def test_blackout_keeps_critical_coverage_close_to_pooled_reference():
    cfg = scenario.load(SCEN / "stress_blackout_72h.yaml")
    df, _, _ = ex.stress_test(cfg)
    s2 = _m(df, "stress", "S2", "crit_coverage_no_gen_pct")
    ref = _m(df, "stress", "pooled-ref", "crit_coverage_no_gen_pct")
    assert s2 <= ref + 1e-9
    assert _m(df, "stress", "S2") > _m(df, "stress", "S0")
