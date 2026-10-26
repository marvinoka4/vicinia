"""Synthetic household archetypes and load profiles.

All numbers here are assumptions, not measurements. They are documented with
their reasoning in docs/assumptions.md. Profiles are built from hourly shape
templates (24 values) that are normalised, scaled to a daily energy target per
household, and perturbed with seeded day-level and interval-level noise.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def _shape(points: dict[tuple[int, int], float], base: float = 0.0) -> np.ndarray:
    """Build a 24-hour shape from {(start_hour, end_hour): kW} blocks."""
    s = np.full(24, base)
    for (a, b), v in points.items():
        hours = range(a, b) if a < b else list(range(a, 24)) + list(range(0, b))
        for h in hours:
            s[h] += v
    return s


# Critical loads: lighting, fans, refrigeration, phone charging.
CRIT_LIGHTS = _shape({(18, 23): 0.15, (5, 7): 0.08})
CRIT_FANS = _shape({(21, 6): 0.10}, base=0.04)
CRIT_FRIDGE = np.full(24, 0.06)
CRIT_PHONES = _shape({(19, 23): 0.02, (6, 8): 0.02})
CRITICAL_SHAPE = CRIT_LIGHTS + CRIT_FANS + CRIT_FRIDGE + CRIT_PHONES

# Non-critical: TV and entertainment, ironing and washing, water pumping,
# air conditioning at night, kitchen appliances.
NONCRITICAL_SHAPE = (
    _shape({(19, 23): 0.15, (12, 16): 0.08})
    + _shape({(7, 10): 0.25})
    + _shape({(6, 8): 0.30, (17, 18): 0.20})
    + _shape({(22, 5): 0.40})
    + _shape({(18, 21): 0.20, (7, 9): 0.15})
    + 0.05
)

# Medical device such as an oxygen concentrator or CPAP, as continuous draw.
MEDICAL_KW = 0.12


@dataclass(frozen=True)
class Archetype:
    name: str
    crit_kwh_day: tuple[float, float]
    noncrit_kwh_day: tuple[float, float]
    pv_kwp: tuple[float, float]
    batt_kwh: tuple[float, float]
    batt_kw: tuple[float, float]
    gen_kw: float
    gen_probability: float
    medical: bool = False


ARCHETYPES: dict[str, Archetype] = {
    "solar_battery": Archetype(
        "solar_battery", (2.5, 3.5), (6.0, 10.0), (3.0, 6.0), (5.0, 15.0), (3.0, 5.0), 2.8, 0.5
    ),
    "battery_only": Archetype(
        "battery_only", (1.8, 2.6), (3.5, 6.0), (0.0, 0.0), (2.4, 4.8), (1.0, 1.5), 1.6, 0.6
    ),
    "grid_only": Archetype(
        "grid_only", (1.2, 2.2), (2.0, 4.5), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0), 1.2, 0.7
    ),
    "medical": Archetype(
        "medical", (1.2, 2.0), (1.5, 3.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0), 1.2, 0.5, medical=True
    ),
}

DEFAULT_MIX = {"solar_battery": 0.30, "battery_only": 0.10, "grid_only": 0.56, "medical": 0.04}


def _hourly_to_steps(shape: np.ndarray, times: pd.DatetimeIndex) -> np.ndarray:
    return shape[times.hour.to_numpy()]


def build_profiles(
    times: pd.DatetimeIndex,
    crit_kwh_day: np.ndarray,
    noncrit_kwh_day: np.ndarray,
    medical: np.ndarray,
    rng: np.random.Generator,
    day_sigma: float = 0.15,
    step_sigma: float = 0.20,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (critical_kw, noncritical_kw), each shaped (households, steps)."""
    n_h = len(crit_kwh_day)
    n = len(times)
    day_idx = np.asarray((times.normalize() - times[0].normalize()).days)
    n_days = int(day_idx.max()) + 1

    crit_base = _hourly_to_steps(CRITICAL_SHAPE / CRITICAL_SHAPE.sum(), times)
    nonc_base = _hourly_to_steps(NONCRITICAL_SHAPE / NONCRITICAL_SHAPE.sum(), times)

    # Households differ in timing: shift each profile by up to +/- 1 hour.
    step_h = (times[1] - times[0]).total_seconds() / 3600.0 if n > 1 else 0.25
    max_shift = int(round(1.0 / step_h))
    shifts = rng.integers(-max_shift, max_shift + 1, size=n_h)

    crit = np.empty((n_h, n))
    nonc = np.empty((n_h, n))
    for h in range(n_h):
        day_c = np.exp(day_sigma * rng.standard_normal(n_days) - day_sigma**2 / 2)[day_idx]
        day_n = np.exp(day_sigma * 1.5 * rng.standard_normal(n_days) - (1.5 * day_sigma) ** 2 / 2)[day_idx]
        noise_c = np.clip(1.0 + step_sigma * rng.standard_normal(n), 0.3, 2.0)
        noise_n = np.clip(1.0 + 2 * step_sigma * rng.standard_normal(n), 0.0, 3.0)
        cb = np.roll(crit_base, shifts[h])
        nb = np.roll(nonc_base, shifts[h])
        # base arrays hold fraction of daily energy per hour; convert to kW.
        crit[h] = crit_kwh_day[h] * cb * day_c * noise_c
        nonc[h] = noncrit_kwh_day[h] * nb * day_n * noise_n
        if medical[h]:
            crit[h] += MEDICAL_KW
    return crit, nonc
