"""Metrics computed from simulation results."""

from __future__ import annotations

import numpy as np

from .engine import SimResult


def gini(x: np.ndarray) -> float:
    """Gini coefficient of a non-negative vector (0 = equal, 1 = one holder)."""
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    if n == 0 or x.sum() <= 0:
        return 0.0
    cum = np.cumsum(x)
    return float((n + 1 - 2 * (cum / cum[-1]).sum()) / n)


def _ratio(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.divide(a, b, out=np.ones_like(a, dtype=float), where=b > 1e-12)


def household_costs(r: SimResult) -> np.ndarray:
    """Energy cost per household in NGN: grid + fuel + bought - sold."""
    p = r.params
    st = r.ledger.statements(r.fleet.n)
    return (
        r.hh["grid_kwh"] * p.grid_tariff_ngn_per_kwh
        + r.hh["fuel_l"] * p.fuel_ngn_per_l
        - st["ngn_net"].to_numpy()
    )


def household_crit_coverage(r: SimResult) -> np.ndarray:
    """Share of critical load served during outages, per household."""
    return _ratio(r.hh["out_crit_served_kwh"], r.hh["out_crit_load_kwh"])


def summarize(r: SimResult, ref: SimResult | None = None) -> dict:
    """Headline metrics. `ref` is the islanded (S0) run used for comparisons."""
    h = r.hh
    p = r.params
    cov = household_crit_coverage(r)
    out_load = h["out_crit_load_kwh"].sum()
    cost = household_costs(r)
    out = {
        "strategy": p.strategy,
        "households": r.fleet.n,
        "crit_coverage_outage_pct": 100 * h["out_crit_served_kwh"].sum() / out_load if out_load > 0 else 100.0,
        "crit_coverage_all_pct": 100 * h["crit_served_kwh"].sum() / h["crit_load_kwh"].sum(),
        "worst_household_crit_coverage_pct": 100 * float(cov.min()),
        "households_below_90pct_crit": int((cov < 0.9).sum()),
        "unserved_crit_kwh": float((h["crit_load_kwh"] - h["crit_served_kwh"]).sum()),
        "unserved_total_kwh": float(
            (h["crit_load_kwh"] - h["crit_served_kwh"] + h["nonc_load_kwh"] - h["nonc_served_kwh"]).sum()
        ),
        "gen_runtime_h": float(h["gen_hours"].sum()),
        "fuel_l": float(h["fuel_l"].sum()),
        "co2_kg": float(h["fuel_l"].sum() * p.co2_kg_per_l),
        "grid_kwh": float(h["grid_kwh"].sum()),
        "community_cost_ngn": float(cost.sum()),
        "mean_household_cost_ngn": float(cost.mean()),
        "shared_delivered_kwh": float(h["received_kwh"].sum()),
        "losses_kwh": float(h["sent_kwh"].sum() - h["received_kwh"].sum()),
        "pv_kwh": float(h["pv_kwh"].sum()),
        "curtailed_kwh": float(h["curtailed_kwh"].sum()),
        "ledger_entries": len(r.ledger.entries),
        "runtime_s": r.runtime_s,
    }
    if ref is not None:
        out["curtailment_avoided_kwh"] = float(ref.hh["curtailed_kwh"].sum() - h["curtailed_kwh"].sum())
        out["fuel_saved_l"] = float(ref.hh["fuel_l"].sum() - h["fuel_l"].sum())
        out["co2_avoided_kg"] = out["fuel_saved_l"] * p.co2_kg_per_l
        b = benefit_ngn(r, ref)
        out["gini_benefit"] = gini(np.clip(b, 0.0, None))
        out["households_worse_off"] = int((b < -1.0).sum())
    return out


def benefit_ngn(r: SimResult, ref: SimResult) -> np.ndarray:
    """Per-household benefit relative to islanded operation, in NGN.

    Cost saving plus extra energy served valued at the generator cost per kWh
    (what the household would otherwise pay to self-supply it). Households
    without a generator still value served energy this way, which is a
    simplification noted in docs/limitations.md.
    """
    voll = r.params.gen_cost_ngn_per_kwh()
    served = r.hh["crit_served_kwh"] + r.hh["nonc_served_kwh"]
    served0 = ref.hh["crit_served_kwh"] + ref.hh["nonc_served_kwh"]
    return (household_costs(ref) - household_costs(r)) + voll * (served - served0)
