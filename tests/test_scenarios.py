"""Scenario building, determinism and strategy-level checks on real inputs."""

from pathlib import Path

import numpy as np
import pytest

from vicinia import experiments as ex
from vicinia import metrics, scenario

ROOT = Path(__file__).resolve().parents[1]
SCEN = ROOT / "scenarios"


@pytest.fixture(scope="module")
def lagos():
    return scenario.build(scenario.load(SCEN / "baseline_lagos.yaml"), days=14)


def test_all_scenarios_build():
    for p in sorted(SCEN.glob("*.yaml")):
        b = scenario.build(scenario.load(p), days=3)
        assert b.inputs.crit_kw.shape == (b.fleet.n, len(b.inputs.times))
        assert (b.inputs.pv_per_kwp >= 0).all()


def test_inputs_deterministic_for_fixed_seed():
    cfg = scenario.load(SCEN / "baseline_lagos.yaml")
    a = scenario.build(cfg, days=5)
    b = scenario.build(cfg, days=5)
    assert np.array_equal(a.inputs.crit_kw, b.inputs.crit_kw)
    assert np.array_equal(a.inputs.grid_on, b.inputs.grid_on)
    assert np.array_equal(a.inputs.pv_per_kwp, b.inputs.pv_per_kwp)
    assert np.array_equal(a.fleet.pv_kwp, b.fleet.pv_kwp)
    cfg2 = dict(cfg, seed=43)
    c = scenario.build(cfg2, days=5)
    assert not np.array_equal(a.inputs.crit_kw, c.inputs.crit_kw)


def test_results_deterministic(lagos):
    for name in ("S0", "S1", "S2"):
        r1 = ex.run_one(lagos, name)
        r2 = ex.run_one(lagos, name)
        assert r1.ledger.head == r2.ledger.head
        for k in r1.hh:
            assert np.array_equal(r1.hh[k], r2.hh[k])


def test_sharing_improves_critical_coverage(lagos):
    df, _ = ex.compare(lagos)
    m = df.set_index("run")
    assert m.loc["S1", "crit_coverage_outage_pct"] >= m.loc["S0", "crit_coverage_outage_pct"]
    assert m.loc["S2", "crit_coverage_outage_pct"] >= m.loc["S1", "crit_coverage_outage_pct"]
    assert m.loc["S2", "worst_household_crit_coverage_pct"] >= m.loc["S0", "worst_household_crit_coverage_pct"]
    # Clean coverage never exceeds the pooled, lossless reference.
    assert m.loc["S2", "crit_coverage_no_gen_pct"] <= m.loc["pooled-ref", "crit_coverage_no_gen_pct"] + 1e-9


def test_full_ledger_verifies_and_nets(lagos):
    r = ex.run_one(lagos, "S2")
    assert len(r.ledger.entries) > 0
    assert r.ledger.verify()
    day = np.asarray((lagos.inputs.times.normalize() - lagos.inputs.times[0].normalize()).days)
    net = r.ledger.netting(lagos.fleet.n, day)
    assert (net.groupby("period")["net_kobo"].sum() == 0).all()
    # Settlement makes total household cost equal grid plus fuel spend.
    cost = metrics.household_costs(r).sum()
    p = r.params
    assert cost == pytest.approx((r.hh["grid_kwh"] * p.grid_tariff_ngn_per_kwh + r.hh["fuel_l"] * p.fuel_ngn_per_l).sum())


def test_settlement_price_must_sit_between_tariff_and_generator_cost():
    cfg = scenario.load(SCEN / "baseline_lagos.yaml")
    cfg["prices"]["settlement_ngn_per_kwh"] = 100.0
    with pytest.raises(ValueError):
        scenario.build(cfg, days=1)
    cfg["prices"]["settlement_ngn_per_kwh"] = 5000.0
    with pytest.raises(ValueError):
        scenario.build(cfg, days=1)


def test_gini():
    assert metrics.gini(np.ones(10)) == pytest.approx(0.0)
    x = np.zeros(10)
    x[0] = 1
    assert metrics.gini(x) == pytest.approx(0.9)
