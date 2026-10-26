"""Interval-by-interval simulation of a neighbourhood with optional sharing.

Strategies
----------
S0  islanded: each home uses its own PV and battery, then its generator.
S1  greedy sharing: during outages, PV surplus that a home cannot use or store
    is offered to the feeder and allocated to whole household deficits
    (critical plus non-critical) in a random arrival order.
S2  critical-first: PV surplus is allocated pro-rata to critical deficits
    first, then pro-rata to non-critical deficits. Batteries hold a reserve
    that only critical load may use, and battery energy above a donor's
    reserve may be offered to neighbours' remaining critical deficits.

Order of operations in each outage interval, per household:
own PV -> own battery charging from PV surplus -> sharing of PV surplus ->
own battery discharge -> (S2) sharing of battery energy above reserve ->
generator -> unserved.

When the grid is on, PV serves load first, the grid covers the rest, and
batteries charge from PV surplus and then from the grid. No sharing happens
while the grid is on, because the settlement price is set above the grid
tariff and a rational buyer would use the grid.

If communication is lost (comm_on is False) no sharing happens and each home
falls back to islanded operation, keeping its local battery policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .ledger import Ledger
from .sharing import EPS, contributions, greedy, pair_flows, pro_rata

STRATEGIES = ("S0", "S1", "S2")


@dataclass
class Fleet:
    archetype: np.ndarray
    pv_kwp: np.ndarray
    batt_kwh: np.ndarray
    batt_kw: np.ndarray
    gen_kw: np.ndarray
    batt_eff_rt: np.ndarray
    batt_min_soc: np.ndarray
    batt_init_soc: np.ndarray
    grid_charge_soc: np.ndarray  # charge from grid up to this SoC fraction (0 = never)

    @property
    def n(self) -> int:
        return len(self.pv_kwp)


@dataclass
class SimInputs:
    times: pd.DatetimeIndex
    dt_h: float
    pv_per_kwp: np.ndarray  # (T,) kW per kWp
    crit_kw: np.ndarray  # (H, T)
    nonc_kw: np.ndarray  # (H, T)
    grid_on: np.ndarray  # (T,) bool
    comm_on: np.ndarray  # (T,) bool
    connected: np.ndarray  # (H, T) bool, household linked to the sharing feeder
    feeder_kw: np.ndarray  # (T,) shared feeder transfer limit, sent side


@dataclass
class Params:
    strategy: str = "S2"
    loss_fraction: float = 0.05
    reserve_soc: float = 0.5
    share_battery: bool = True
    settlement_ngn_per_kwh: float = 400.0
    grid_tariff_ngn_per_kwh: float = 209.5
    fuel_ngn_per_l: float = 950.0
    gen_fuel_noload_l_per_kw_h: float = 0.25
    gen_fuel_l_per_kwh: float = 0.35
    gen_min_load_kw: float = 0.10
    co2_kg_per_l: float = 2.27
    seed: int = 0

    def gen_cost_ngn_per_kwh(self, load_fraction: float = 0.4) -> float:
        litres = self.gen_fuel_noload_l_per_kw_h / load_fraction + self.gen_fuel_l_per_kwh
        return litres * self.fuel_ngn_per_l


HH_FIELDS = (
    "pv_kwh", "curtailed_kwh", "grid_kwh", "gen_kwh", "gen_hours", "fuel_l",
    "sent_kwh", "received_kwh", "batt_charge_kwh", "batt_discharge_kwh",
    "crit_load_kwh", "crit_served_kwh", "nonc_load_kwh", "nonc_served_kwh",
    "out_crit_load_kwh", "out_crit_served_kwh", "out_nonc_load_kwh", "out_nonc_served_kwh",
    "soc_min_kwh", "soc_max_kwh",
)
TS_FIELDS = (
    "pv_kwh", "crit_load_kwh", "crit_unserved_kwh", "nonc_unserved_kwh",
    "shared_sent_kwh", "shared_received_kwh", "gen_kwh", "curtailed_kwh", "soc_kwh",
)
REC_FIELDS = (
    "pv", "grid", "gen", "recv", "sent", "dis", "chg", "curt", "crit_served", "nonc_served", "soc",
)


@dataclass
class SimResult:
    params: Params
    fleet: Fleet
    inputs: SimInputs
    hh: dict[str, np.ndarray]
    ts: dict[str, np.ndarray]
    ledger: Ledger
    rec: dict[str, np.ndarray] | None = None
    runtime_s: float = 0.0
    extra: dict = field(default_factory=dict)


def simulate(
    inp: SimInputs, fleet: Fleet, p: Params, record: bool = False, window: slice | None = None
) -> SimResult:
    """Run one strategy. Household totals cover `window` (default: all intervals)."""
    if p.strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {p.strategy}")
    if not 0.0 <= p.loss_fraction < 1.0:
        raise ValueError("loss_fraction must be in [0, 1)")
    H, T = inp.crit_kw.shape
    dt = inp.dt_h
    keep = 1.0 - p.loss_fraction
    s1 = p.strategy == "S1"
    s2 = p.strategy == "S2"
    rng = np.random.default_rng(p.seed)

    cap = fleet.batt_kwh.astype(float)
    eta = np.sqrt(np.clip(fleet.batt_eff_rt, 1e-6, 1.0))
    floor = cap * fleet.batt_min_soc
    reserve = cap * np.maximum(fleet.batt_min_soc, p.reserve_soc) if s2 else floor
    pmax = fleet.batt_kw * dt
    gen_e = fleet.gen_kw * dt
    has_gen = fleet.gen_kw > 0
    grid_target = cap * np.clip(fleet.grid_charge_soc, 0.0, 1.0)
    soc = np.clip(cap * fleet.batt_init_soc, floor, cap)

    PV = fleet.pv_kwp[:, None] * inp.pv_per_kwp[None, :] * dt
    CE = inp.crit_kw * dt
    NE = inp.nonc_kw * dt

    hh = {k: np.zeros(H) for k in HH_FIELDS}
    hh["soc_min_kwh"] = soc.copy()
    hh["soc_max_kwh"] = soc.copy()
    ts = {k: np.zeros(T) for k in TS_FIELDS}
    rec = {k: np.zeros((H, T)) for k in REC_FIELDS} if record else None
    ledger = Ledger(p.settlement_ngn_per_kwh)
    zeros = np.zeros(H)

    w0, w1 = (0, T) if window is None else (window.start or 0, T if window.stop is None else window.stop)

    for t in range(T):
        pv = PV[:, t]
        c = CE[:, t]
        nn = NE[:, t]
        pv_c = np.minimum(pv, c)
        rc = c - pv_c
        rem = pv - pv_c
        pv_n = np.minimum(rem, nn)
        rn = nn - pv_n
        surplus = rem - pv_n

        chg = np.clip(np.minimum(surplus, np.minimum(pmax, (cap - soc) / eta)), 0.0, None)
        soc = soc + chg * eta
        surplus = surplus - chg

        sent = zeros
        recv = zeros
        dis = zeros
        grid = zeros
        gen_out = zeros
        outage = not inp.grid_on[t]

        if not outage:
            grid = rc + rn
            gch = np.clip(np.minimum(pmax - chg, (grid_target - soc) / eta), 0.0, None)
            soc = soc + gch * eta
            grid = grid + gch
            chg = chg + gch
            rc = zeros
            rn = zeros
        else:
            sharing = (s1 or s2) and bool(inp.comm_on[t])
            cap_left = float(inp.feeder_kw[t]) * dt
            conn = inp.connected[:, t]
            sent = np.zeros(H)
            recv = np.zeros(H)
            rc = np.where(rc > EPS, rc, 0.0)
            rn = np.where(rn > EPS, rn, 0.0)
            if sharing and cap_left > EPS:
                offer = np.where(conn & (surplus > EPS), surplus, 0.0)
                dem_c = np.where(conn, rc, 0.0)
                dem_n = np.where(conn, rn, 0.0)
                supply = min(float(offer.sum()), cap_left) * keep
                if supply > EPS and dem_c.sum() + dem_n.sum() > EPS:
                    if s1:
                        order = rng.permutation(H)
                        got = greedy(supply, dem_c + dem_n, order)
                        got_c = np.minimum(got, dem_c)
                        got_n = got - got_c
                        d_order = order
                    else:
                        got_c = pro_rata(supply, dem_c)
                        got_n = pro_rata(max(supply - float(got_c.sum()), 0.0), dem_n)
                        got = got_c + got_n
                        order = np.arange(H)
                        d_order = None
                    total_sent = float(got.sum()) / keep
                    s = contributions(total_sent, offer, d_order)
                    for d, r, a in pair_flows(s, got, p.loss_fraction, order, order):
                        ledger.append(t, d, r, a, a * keep)
                    surplus = surplus - s
                    sent += s
                    recv += got
                    rc = rc - got_c
                    rn = rn - got_n
                    cap_left -= total_sent

            # Own battery: critical first, non-critical only above reserve (S2).
            pw = pmax.copy()
            bc = np.minimum(rc, np.minimum(np.clip((soc - floor) * eta, 0.0, None), pw))
            soc = soc - bc / eta
            rc = rc - bc
            pw = pw - bc
            bn = np.minimum(rn, np.minimum(np.clip((soc - reserve) * eta, 0.0, None), pw))
            soc = soc - bn / eta
            rn = rn - bn
            pw = pw - bn
            dis = bc + bn
            rc = np.where(rc > EPS, rc, 0.0)

            if s2 and p.share_battery and sharing and cap_left > EPS:
                offer2 = np.where(conn, np.minimum(np.clip((soc - reserve) * eta, 0.0, None), pw), 0.0)
                offer2 = np.where(offer2 > EPS, offer2, 0.0)
                dem2 = np.where(conn, rc, 0.0)
                supply2 = min(float(offer2.sum()), cap_left) * keep
                if supply2 > EPS and dem2.sum() > EPS:
                    got2 = pro_rata(supply2, dem2)
                    total_sent2 = float(got2.sum()) / keep
                    s2_sent = pro_rata(total_sent2, offer2)
                    idx = np.arange(H)
                    for d, r, a in pair_flows(s2_sent, got2, p.loss_fraction, idx, idx):
                        ledger.append(t, d, r, a, a * keep)
                    soc = soc - s2_sent / eta
                    dis = dis + s2_sent
                    sent += s2_sent
                    recv += got2
                    rc = rc - got2
                    cap_left -= total_sent2

            need = rc + rn
            run = has_gen & (need >= p.gen_min_load_kw * dt)
            gen_out = np.where(run, np.minimum(need, gen_e), 0.0)
            gc = np.minimum(gen_out, rc)
            rc = rc - gc
            rn = rn - (gen_out - gc)
            gen_h = run * dt
            fuel = np.where(run, p.gen_fuel_noload_l_per_kw_h * gen_e + p.gen_fuel_l_per_kwh * gen_out, 0.0)

        if (soc < floor - 1e-9).any() or (soc > cap + 1e-9).any():
            raise RuntimeError(f"battery state of charge out of bounds at interval {t}")
        soc = np.clip(soc, floor, cap)  # remove floating point residue only
        crit_served = c - rc
        nonc_served = nn - rn
        curt = np.clip(surplus, 0.0, None)
        np.minimum(hh["soc_min_kwh"], soc, out=hh["soc_min_kwh"])
        np.maximum(hh["soc_max_kwh"], soc, out=hh["soc_max_kwh"])
        ts["pv_kwh"][t] = pv.sum()
        ts["crit_load_kwh"][t] = c.sum()
        ts["crit_unserved_kwh"][t] = rc.sum()
        ts["nonc_unserved_kwh"][t] = rn.sum()
        ts["shared_sent_kwh"][t] = sent.sum()
        ts["shared_received_kwh"][t] = recv.sum()
        ts["gen_kwh"][t] = gen_out.sum()
        ts["curtailed_kwh"][t] = curt.sum()
        ts["soc_kwh"][t] = soc.sum()

        if rec is not None:
            rec["pv"][:, t] = pv
            rec["grid"][:, t] = grid
            rec["gen"][:, t] = gen_out
            rec["recv"][:, t] = recv
            rec["sent"][:, t] = sent
            rec["dis"][:, t] = dis
            rec["chg"][:, t] = chg
            rec["curt"][:, t] = curt
            rec["crit_served"][:, t] = crit_served
            rec["nonc_served"][:, t] = nonc_served
            rec["soc"][:, t] = soc

        if not w0 <= t < w1:
            continue
        if outage:
            hh["gen_hours"] += gen_h
            hh["fuel_l"] += fuel
        hh["pv_kwh"] += pv
        hh["curtailed_kwh"] += curt
        hh["grid_kwh"] += grid
        hh["gen_kwh"] += gen_out
        hh["sent_kwh"] += sent
        hh["received_kwh"] += recv
        hh["batt_charge_kwh"] += chg
        hh["batt_discharge_kwh"] += dis
        hh["crit_load_kwh"] += c
        hh["crit_served_kwh"] += crit_served
        hh["nonc_load_kwh"] += nn
        hh["nonc_served_kwh"] += nonc_served
        if outage:
            hh["out_crit_load_kwh"] += c
            hh["out_crit_served_kwh"] += crit_served
            hh["out_nonc_load_kwh"] += nn
            hh["out_nonc_served_kwh"] += nonc_served

    return SimResult(params=p, fleet=fleet, inputs=inp, hh=hh, ts=ts, ledger=ledger, rec=rec)
