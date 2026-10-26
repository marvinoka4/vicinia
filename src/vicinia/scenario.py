"""Scenario files: YAML in, simulation inputs out.

A scenario fixes the site, period, household fleet, grid schedule, sharing
parameters, prices and stress events. Every random draw comes from a seed in
the file, split into independent streams so that, for example, changing the
fleet size does not change the weather.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from . import grid as grid_mod
from . import loads, solar
from .engine import Fleet, Params, SimInputs

DEFAULTS: dict[str, Any] = {
    "name": "unnamed",
    "description": "",
    "seed": 42,
    "site": "lagos",
    "start": "2026-01-01",
    "days": 365,
    "timestep_minutes": 15,
    "solar": {"source": "clearsky", "pvgis_csv": None},
    "households": {"count": 50, "mix": dict(loads.DEFAULT_MIX)},
    "batteries": {
        "solar_battery": {"eff_rt": 0.90, "min_soc": 0.20},
        "battery_only": {"eff_rt": 0.80, "min_soc": 0.50},
        "init_soc": 0.80,
        "grid_charge_soc": 0.70,
    },
    "grid": {},
    "sharing": {"feeder_kw": 25.0, "loss_fraction": 0.05, "reserve_soc": 0.5, "share_battery": True},
    "prices": {"settlement_ngn_per_kwh": 600.0, "grid_tariff_ngn_per_kwh": 209.5, "fuel_ngn_per_l": 1596.0},
    "generator": {"fuel_noload_l_per_kw_h": 0.25, "fuel_l_per_kwh": 0.35, "min_load_kw": 0.10, "co2_kg_per_l": 2.27},
    "events": [],
    "window": None,
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: str | Path) -> dict:
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    cfg = _merge(DEFAULTS, raw)
    cfg["_path"] = str(path)
    return cfg


def from_dict(d: dict) -> dict:
    return _merge(DEFAULTS, d)


@dataclass
class Built:
    cfg: dict
    inputs: SimInputs
    fleet: Fleet
    base_params: Params
    window: slice

    def params(self, strategy: str, **over: Any) -> Params:
        p = copy.copy(self.base_params)
        p.strategy = strategy
        for k, v in over.items():
            setattr(p, k, v)
        return p


def build_fleet(cfg: dict, rng: np.random.Generator) -> Fleet:
    n = int(cfg["households"]["count"])
    mix = cfg["households"]["mix"]
    names = list(mix)
    weights = np.array([mix[k] for k in names], dtype=float)
    weights = weights / weights.sum()
    counts = np.floor(weights * n).astype(int)
    # Largest remainders get the leftover households.
    for i in np.argsort(-(weights * n - counts))[: n - counts.sum()]:
        counts[i] += 1
    arche = np.array([nm for nm, c in zip(names, counts) for _ in range(c)])
    arche = arche[rng.permutation(n)]

    bat = cfg["batteries"]
    pv = np.zeros(n)
    bkwh = np.zeros(n)
    bkw = np.zeros(n)
    gen = np.zeros(n)
    eff = np.ones(n)
    msoc = np.zeros(n)
    for i, nm in enumerate(arche):
        a = loads.ARCHETYPES[nm]
        pv[i] = round(rng.uniform(*a.pv_kwp), 1)
        bkwh[i] = round(rng.uniform(*a.batt_kwh), 1)
        bkw[i] = round(rng.uniform(*a.batt_kw), 1) if bkwh[i] > 0 else 0.0
        gen[i] = a.gen_kw if rng.random() < a.gen_probability else 0.0
        if nm in bat:
            eff[i] = bat[nm]["eff_rt"]
            msoc[i] = bat[nm]["min_soc"]
    return Fleet(
        archetype=arche,
        pv_kwp=pv,
        batt_kwh=bkwh,
        batt_kw=bkw,
        gen_kw=gen,
        batt_eff_rt=eff,
        batt_min_soc=msoc,
        batt_init_soc=np.full(n, float(bat["init_soc"])),
        grid_charge_soc=np.full(n, float(bat["grid_charge_soc"])),
    )


def _index(times: pd.DatetimeIndex, when: str) -> int:
    return int(times.searchsorted(pd.Timestamp(when, tz=times.tz)))


def build(cfg: dict, days: int | None = None) -> Built:
    seeds = np.random.SeedSequence(int(cfg["seed"])).spawn(6)
    r_fleet, r_load, r_sky, r_grid, r_sim, r_misc = (np.random.default_rng(s) for s in seeds)
    n_days = int(days if days is not None else cfg["days"])
    step = int(cfg["timestep_minutes"])
    times = solar.make_times(cfg["start"], n_days, step)
    dt = step / 60.0
    T = len(times)
    site = solar.SITES[cfg["site"]]

    fleet = build_fleet(cfg, r_fleet)
    H = fleet.n

    events = cfg.get("events") or []
    sky_events = []
    for ev in events:
        if ev["type"] == "sky":
            s = _index(times, ev["start"])
            sky_events.append((s, s + int(round(ev["days"] * 24 / dt)), float(ev["multiplier"])))

    if cfg["solar"].get("source") == "pvgis":
        tmy = solar.load_pvgis_tmy(cfg["solar"]["pvgis_csv"])
        poa, temp = solar.pvgis_poa(site, times, tmy)
        factor = np.ones(T)
        for s, e, m in sky_events:
            factor[s:e] *= m
        pv_per_kwp = solar.pv_per_kwp(poa, factor, temp)
    else:
        poa = solar.clear_sky_poa(site, times)
        factor = solar.sky_factor(site, times, r_sky, sky_events)
        pv_per_kwp = solar.pv_per_kwp(poa, factor)

    crit_day = np.zeros(H)
    nonc_day = np.zeros(H)
    medical = np.zeros(H, dtype=bool)
    for i, nm in enumerate(fleet.archetype):
        a = loads.ARCHETYPES[nm]
        crit_day[i] = r_load.uniform(*a.crit_kwh_day)
        nonc_day[i] = r_load.uniform(*a.noncrit_kwh_day)
        medical[i] = a.medical
    crit_kw, nonc_kw = loads.build_profiles(times, crit_day, nonc_day, medical, r_load)

    gcfg_raw = dict(cfg["grid"])
    blackouts = [(str(ev["start"]), float(ev["hours"])) for ev in events if ev["type"] == "blackout"]
    gcfg_raw["blackouts"] = list(gcfg_raw.get("blackouts", [])) + blackouts
    for k in ("blocks_per_day", "fault_hours", "collapse_hours"):
        if k in gcfg_raw:
            gcfg_raw[k] = tuple(gcfg_raw[k])
    gcfg = grid_mod.GridConfig(**gcfg_raw)
    grid_on = grid_mod.availability(gcfg, times, r_grid)

    comm_on = np.ones(T, dtype=bool)
    connected = np.ones((H, T), dtype=bool)
    feeder = np.full(T, float(cfg["sharing"]["feeder_kw"]))
    for ev in events:
        typ = ev["type"]
        if typ in ("sky", "blackout"):
            continue
        s = _index(times, ev["start"])
        e = s + int(round(float(ev.get("hours", 1e9)) / dt)) if "hours" in ev else T
        if typ == "comm_loss":
            comm_on[s:e] = False
        elif typ == "feeder":
            feeder[s:e] *= float(ev["multiplier"])
        elif typ == "dropout":
            who = ev.get("household", "largest_pv")
            hh = int(np.argmax(fleet.pv_kwp)) if who == "largest_pv" else int(who)
            connected[hh, s:e] = False
        else:
            raise ValueError(f"unknown event type {typ}")

    inputs = SimInputs(
        times=times,
        dt_h=dt,
        pv_per_kwp=pv_per_kwp,
        crit_kw=crit_kw,
        nonc_kw=nonc_kw,
        grid_on=grid_on,
        comm_on=comm_on,
        connected=connected,
        feeder_kw=feeder,
    )
    sh, pr, gn = cfg["sharing"], cfg["prices"], cfg["generator"]
    params = Params(
        strategy="S2",
        loss_fraction=float(sh["loss_fraction"]),
        reserve_soc=float(sh["reserve_soc"]),
        share_battery=bool(sh["share_battery"]),
        settlement_ngn_per_kwh=float(pr["settlement_ngn_per_kwh"]),
        grid_tariff_ngn_per_kwh=float(pr["grid_tariff_ngn_per_kwh"]),
        fuel_ngn_per_l=float(pr["fuel_ngn_per_l"]),
        gen_fuel_noload_l_per_kw_h=float(gn["fuel_noload_l_per_kw_h"]),
        gen_fuel_l_per_kwh=float(gn["fuel_l_per_kwh"]),
        gen_min_load_kw=float(gn["min_load_kw"]),
        co2_kg_per_l=float(gn["co2_kg_per_l"]),
        seed=int(r_sim.integers(0, 2**31 - 1)),
    )
    lo = params.grid_tariff_ngn_per_kwh
    hi = params.gen_cost_ngn_per_kwh()
    if not lo <= params.settlement_ngn_per_kwh <= hi:
        raise ValueError(
            f"settlement price {params.settlement_ngn_per_kwh} must lie between grid tariff {lo} "
            f"and generator cost {hi:.0f} NGN/kWh"
        )

    win = cfg.get("window")
    if win:
        ws = _index(times, win["start"])
        window = slice(ws, min(T, ws + int(round(float(win["days"]) * 24 / dt))))
    else:
        window = slice(0, T)
    return Built(cfg=cfg, inputs=inputs, fleet=fleet, base_params=params, window=window)
