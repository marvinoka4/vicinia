"""Grid availability schedules.

Supply-hour bands follow the minimum daily supply hours of the Nigerian
Electricity Regulatory Commission (NERC) Service-Based Tariff bands as
reported in the press (Band A 20 h, B 16 h, C 12 h, D 8 h, E 4 h). The
primary NERC order could not be accessed while building this, so treat the
values as documented assumptions; see docs/assumptions.md.

Band hours are a minimum obligation, and many feeders deliver less. The
schedule therefore draws each day's supply hours around the band value and
then removes further random fault outages and multi-day grid collapses.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

BAND_HOURS = {"A": 20.0, "B": 16.0, "C": 12.0, "D": 8.0, "E": 4.0}


@dataclass
class GridConfig:
    band: str = "C"
    supply_hours: float | None = None  # overrides band if set
    daily_sd_hours: float = 2.0
    blocks_per_day: tuple[int, int] = (1, 3)
    fault_rate_per_week: float = 2.0
    fault_hours: tuple[float, float] = (1.0, 6.0)
    collapse_rate_per_year: float = 6.0
    collapse_hours: tuple[float, float] = (12.0, 48.0)
    blackouts: list[tuple[str, float]] = field(default_factory=list)  # (start, hours)

    @property
    def mean_hours(self) -> float:
        return self.supply_hours if self.supply_hours is not None else BAND_HOURS[self.band.upper()]


def availability(cfg: GridConfig, times: pd.DatetimeIndex, rng: np.random.Generator) -> np.ndarray:
    """Boolean array, True when the grid supplies the neighbourhood feeder."""
    n = len(times)
    step_h = (times[1] - times[0]).total_seconds() / 3600.0 if n > 1 else 0.25
    per_day = int(round(24 / step_h))
    day_idx = np.asarray((times.normalize() - times[0].normalize()).days)
    n_days = int(day_idx.max()) + 1

    on = np.ones(n, dtype=bool)
    # Scheduled load shedding: off-hours split into a few blocks per day.
    for d in range(n_days):
        idx = np.flatnonzero(day_idx == d)
        hours = np.clip(cfg.mean_hours + cfg.daily_sd_hours * rng.standard_normal(), 0.0, 24.0)
        off_steps = int(round((24.0 - hours) / step_h))
        if off_steps <= 0:
            continue
        k = int(rng.integers(cfg.blocks_per_day[0], cfg.blocks_per_day[1] + 1))
        k = max(1, min(k, off_steps))
        cuts = np.sort(rng.choice(np.arange(1, off_steps), size=k - 1, replace=False)) if k > 1 else []
        lengths = np.diff(np.concatenate([[0], cuts, [off_steps]])).astype(int)
        starts = np.sort(rng.choice(per_day, size=k, replace=False))
        for s, ln in zip(starts, lengths):
            on[idx[0] + s: min(idx[0] + s + ln, n)] = False

    # Random feeder faults.
    weeks = n * step_h / (24 * 7)
    for _ in range(rng.poisson(cfg.fault_rate_per_week * weeks)):
        s = int(rng.integers(0, n))
        ln = int(round(rng.uniform(*cfg.fault_hours) / step_h))
        on[s: s + ln] = False

    # National grid collapses: multi-day blackouts.
    years = n * step_h / (24 * 365)
    for _ in range(rng.poisson(cfg.collapse_rate_per_year * years)):
        s = int(rng.integers(0, n))
        ln = int(round(rng.uniform(*cfg.collapse_hours) / step_h))
        on[s: s + ln] = False

    # Explicit blackouts from the scenario (pressure tests).
    for start, hours in cfg.blackouts:
        s = int(times.searchsorted(pd.Timestamp(start, tz=times.tz)))
        on[s: s + int(round(hours / step_h))] = False
    return on
