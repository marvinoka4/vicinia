"""Physical and accounting invariants, checked on random small systems."""

import numpy as np
from hypothesis import given, settings

from vicinia.engine import Params, simulate

from helpers import make_system, system_args

TOL = 1e-8


def run(args, strategy):
    inp, fleet = make_system(**{k: v for k, v in args.items() if k != "loss"})
    p = Params(strategy=strategy, loss_fraction=args["loss"], seed=args["seed"] % 1000)
    return inp, fleet, simulate(inp, fleet, p, record=True)


@settings(max_examples=60, deadline=None)
@given(system_args)
def test_household_energy_balance(args):
    for strat in ("S0", "S1", "S2"):
        inp, fleet, r = run(args, strat)
        x = r.rec
        supply = x["pv"] + x["grid"] + x["gen"] + x["recv"] + x["dis"]
        use = x["crit_served"] + x["nonc_served"] + x["sent"] + x["chg"] + x["curt"]
        assert np.allclose(supply, use, atol=TOL)


@settings(max_examples=60, deadline=None)
@given(system_args)
def test_battery_state_follows_flows_and_stays_in_bounds(args):
    for strat in ("S0", "S1", "S2"):
        inp, fleet, r = run(args, strat)
        x = r.rec
        eta = np.sqrt(fleet.batt_eff_rt)[:, None]
        cap = fleet.batt_kwh[:, None]
        floor = cap * fleet.batt_min_soc[:, None]
        soc0 = np.clip(fleet.batt_kwh * fleet.batt_init_soc, fleet.batt_kwh * fleet.batt_min_soc, fleet.batt_kwh)
        prev = np.concatenate([soc0[:, None], x["soc"][:, :-1]], axis=1)
        assert np.allclose(x["soc"], prev + x["chg"] * eta - x["dis"] / eta, atol=1e-7)
        assert (x["soc"] >= floor - TOL).all() and (x["soc"] <= cap + TOL).all()


@settings(max_examples=60, deadline=None)
@given(system_args)
def test_transfers_conserve_energy_and_respect_limits(args):
    for strat in ("S0", "S1", "S2"):
        inp, fleet, r = run(args, strat)
        x = r.rec
        keep = 1 - r.params.loss_fraction
        sent_t = x["sent"].sum(axis=0)
        recv_t = x["recv"].sum(axis=0)
        # Energy sent minus losses equals energy received, every interval.
        assert np.allclose(sent_t * keep, recv_t, atol=TOL)
        # Feeder limit never exceeded.
        assert (sent_t <= inp.feeder_kw * inp.dt_h + TOL).all()
        # No household receives more than its deficit after its own PV.
        load = (inp.crit_kw + inp.nonc_kw) * inp.dt_h
        deficit = load - np.minimum(x["pv"], load)
        assert (x["recv"] <= deficit + TOL).all()
        # No sharing while the grid is on, without communication, or for S0.
        idle = inp.grid_on | ~inp.comm_on
        assert np.allclose(x["sent"][:, idle], 0) and np.allclose(x["recv"][:, idle], 0)
        if strat == "S0":
            assert np.allclose(x["sent"], 0) and len(r.ledger.entries) == 0
        # Disconnected households neither send nor receive.
        assert np.allclose(x["sent"][~inp.connected], 0) and np.allclose(x["recv"][~inp.connected], 0)
        # Served energy never exceeds load.
        assert (x["crit_served"] <= inp.crit_kw * inp.dt_h + TOL).all()
        assert (x["crit_served"] >= -TOL).all() and (x["nonc_served"] >= -TOL).all()


@settings(max_examples=60, deadline=None)
@given(system_args)
def test_ledger_matches_physical_flows(args):
    for strat in ("S1", "S2"):
        inp, fleet, r = run(args, strat)
        x = r.rec
        H, T = x["sent"].shape
        sent = np.zeros((H, T))
        recv = np.zeros((H, T))
        keep = 1 - r.params.loss_fraction
        for e in r.ledger.entries:
            assert e.sender != e.receiver
            assert abs(e.kwh_sent * keep - e.kwh_received) < 1e-12
            sent[e.sender, e.interval] += e.kwh_sent
            recv[e.receiver, e.interval] += e.kwh_received
        assert np.allclose(sent, x["sent"], atol=1e-7)
        assert np.allclose(recv, x["recv"], atol=1e-7)
        assert r.ledger.verify()
        net = r.ledger.netting(H)
        assert net["net_kobo"].sum() == 0


@settings(max_examples=25, deadline=None)
@given(system_args)
def test_deterministic_for_fixed_seed(args):
    for strat in ("S0", "S1", "S2"):
        _, _, a = run(args, strat)
        _, _, b = run(args, strat)
        for k in a.rec:
            assert np.array_equal(a.rec[k], b.rec[k])
        assert a.ledger.head == b.ledger.head


@settings(max_examples=30, deadline=None)
@given(system_args)
def test_sharing_without_communication_equals_islanded(args):
    args = dict(args, comm_frac=0.0)
    _, _, s0 = run(args, "S0")
    _, _, s1 = run(args, "S1")
    for k in s0.rec:
        assert np.allclose(s0.rec[k], s1.rec[k])
