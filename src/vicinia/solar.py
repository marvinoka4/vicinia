"""Solar resource and PV output.

Default path: pvlib clear-sky irradiance (Ineichen model with the pvlib
Linke turbidity climatology) transposed to a fixed tilted plane, multiplied
by a seeded stochastic sky factor that represents cloud, rainy-season
overcast and harmattan dust. The sky factor is synthetic and is described in
docs/assumptions.md.

Optional path: a PVGIS typical meteorological year (TMY) CSV fetched with
scripts/fetch_pvgis.py. PVGIS data carries its own weather, so no sky factor
is applied on top of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib

TZ = "Africa/Lagos"


@dataclass(frozen=True)
class Site:
    name: str
    lat: float
    lon: float
    altitude_m: float
    # Mean daily sky factor by month (Jan..Dec), 1.0 = clear sky.
    sky_mean: tuple[float, ...]
    # Extra fractional attenuation from harmattan dust by month (Jan..Dec).
    dust: tuple[float, ...]


SITES: dict[str, Site] = {
    "lagos": Site(
        "Lagos", 6.45, 3.40, 41.0,
        (0.92, 0.92, 0.90, 0.86, 0.80, 0.68, 0.64, 0.70, 0.68, 0.78, 0.88, 0.92),
        (0.06, 0.05, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.08),
    ),
    "abuja": Site(
        "Abuja", 9.06, 7.49, 476.0,
        (0.97, 0.97, 0.95, 0.92, 0.86, 0.80, 0.72, 0.70, 0.76, 0.86, 0.97, 0.97),
        (0.08, 0.07, 0.03, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.08),
    ),
    "kano": Site(
        "Kano", 12.00, 8.52, 488.0,
        (1.00, 1.00, 0.98, 0.96, 0.93, 0.90, 0.82, 0.78, 0.86, 0.95, 1.00, 1.00),
        (0.14, 0.12, 0.06, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.06, 0.12),
    ),
}

PERFORMANCE_RATIO = 0.80  # wiring, inverter, soiling and mismatch losses
TEMP_COEFF = -0.004  # per degC above 25 degC cell temperature
NOCT_RISE = 0.03  # degC per W/m2 of plane-of-array irradiance (simple model)


def make_times(start: str, days: int, step_min: int) -> pd.DatetimeIndex:
    periods = int(days * 24 * 60 / step_min)
    return pd.date_range(start=start, periods=periods, freq=f"{step_min}min", tz=TZ)


def clear_sky_poa(site: Site, times: pd.DatetimeIndex) -> np.ndarray:
    """Clear-sky plane-of-array irradiance in W/m2 for a south-facing plane."""
    loc = pvlib.location.Location(site.lat, site.lon, tz=TZ, altitude=site.altitude_m)
    # Evaluate at the middle of each interval so energy per interval is unbiased.
    step = times[1] - times[0] if len(times) > 1 else pd.Timedelta(minutes=15)
    mid = times + step / 2
    cs = loc.get_clearsky(mid, model="ineichen")
    sp = loc.get_solarposition(mid)
    tilt = max(10.0, abs(site.lat))
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=180.0,
        solar_zenith=sp["apparent_zenith"],
        solar_azimuth=sp["azimuth"],
        dni=cs["dni"],
        ghi=cs["ghi"],
        dhi=cs["dhi"],
    )["poa_global"]
    return np.nan_to_num(poa.to_numpy(dtype=float), nan=0.0).clip(min=0.0)


def sky_factor(
    site: Site,
    times: pd.DatetimeIndex,
    rng: np.random.Generator,
    events: list[tuple[int, int, float]] | None = None,
) -> np.ndarray:
    """Seeded stochastic sky factor in [0.05, 1.0] per interval.

    Day-level clearness follows an AR(1) process around the monthly mean so
    that cloudy days cluster. Within a day a smaller AR(1) term adds
    intermittent cloud, stronger on cloudier days. Harmattan dust is a
    separate multiplicative attenuation in the dry season months.
    `events` is a list of (start_index, end_index, multiplier) windows, used
    for stress tests such as a cloudy or dusty week.
    """
    n = len(times)
    day_idx = np.asarray((times.normalize() - times[0].normalize()).days)
    n_days = int(day_idx.max()) + 1 if n else 0
    months = times.month.to_numpy() - 1

    phi_day = 0.6
    z = np.empty(n_days)
    z_prev = 0.0
    for d in range(n_days):
        z_prev = phi_day * z_prev + np.sqrt(1 - phi_day**2) * rng.standard_normal()
        z[d] = z_prev
    dust_noise = rng.standard_normal(n_days)

    mean = np.asarray(site.sky_mean)[months]
    dust = np.asarray(site.dust)[months]
    k_day = np.clip(mean + 0.15 * z[day_idx], 0.12, 1.0)
    dust_day = np.clip(dust * (1.0 + 0.5 * dust_noise[day_idx]), 0.0, 0.6)

    # Intra-day variability.
    phi_int = 0.8
    e = rng.standard_normal(n)
    w = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc = phi_int * acc + np.sqrt(1 - phi_int**2) * e[i]
        w[i] = acc
    sigma = 0.35 * (1.0 - k_day)
    intra = np.clip(1.0 + sigma * w, 0.2, 1.3)

    f = np.clip(k_day * intra * (1.0 - dust_day), 0.05, 1.0)
    for start, end, mult in events or []:
        f[start:end] *= mult
    return f


def pv_per_kwp(poa: np.ndarray, factor: np.ndarray, temp_air: np.ndarray | float = 28.0) -> np.ndarray:
    """AC power in kW per kWp installed, given POA irradiance and sky factor."""
    g = poa * factor
    t_cell = temp_air + NOCT_RISE * g
    derate = 1.0 + TEMP_COEFF * (t_cell - 25.0)
    return np.clip(g / 1000.0 * PERFORMANCE_RATIO * derate, 0.0, None)


def load_pvgis_tmy(path: str | Path) -> pd.DataFrame:
    """Parse a PVGIS TMY CSV (outputformat=csv) into an hourly frame.

    Returns columns ghi, dni, dhi, temp_air indexed by (month, day, hour) in
    local time so it can be mapped onto any simulation year.
    """
    lines = Path(path).read_text().splitlines()
    head = next(i for i, ln in enumerate(lines) if ln.startswith("time(UTC)"))
    rows = []
    for ln in lines[head + 1:]:
        parts = ln.split(",")
        if len(parts) < 6 or not parts[0][:8].isdigit():
            break
        rows.append(parts)
    cols = lines[head].split(",")
    df = pd.DataFrame(rows, columns=cols[: len(rows[0])])
    t = pd.to_datetime(df["time(UTC)"], format="%Y%m%d:%H%M", utc=True).dt.tz_convert(TZ)
    out = pd.DataFrame(
        {
            "month": t.dt.month.to_numpy(),
            "day": t.dt.day.to_numpy(),
            "hour": t.dt.hour.to_numpy(),
            "ghi": df["G(h)"].astype(float).to_numpy(),
            "dni": df["Gb(n)"].astype(float).to_numpy(),
            "dhi": df["Gd(h)"].astype(float).to_numpy(),
            "temp_air": df["T2m"].astype(float).to_numpy(),
        }
    )
    return out.set_index(["month", "day", "hour"]).sort_index()


def pvgis_poa(site: Site, times: pd.DatetimeIndex, tmy: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Map PVGIS TMY hourly data onto simulation times and transpose to POA."""
    key = list(zip(times.month, times.day, times.hour))
    # Feb 29 is absent from a TMY; fall back to Feb 28.
    key = [(m, 28, h) if (m == 2 and d == 29) else (m, d, h) for m, d, h in key]
    sub = tmy.reindex(key)
    loc = pvlib.location.Location(site.lat, site.lon, tz=TZ, altitude=site.altitude_m)
    sp = loc.get_solarposition(times)
    tilt = max(10.0, abs(site.lat))
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=180.0,
        solar_zenith=sp["apparent_zenith"],
        solar_azimuth=sp["azimuth"],
        dni=sub["dni"].to_numpy(),
        ghi=sub["ghi"].to_numpy(),
        dhi=sub["dhi"].to_numpy(),
    )["poa_global"]
    poa = np.nan_to_num(np.asarray(poa, dtype=float), nan=0.0).clip(min=0.0)
    return poa, sub["temp_air"].to_numpy(dtype=float)
