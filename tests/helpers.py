import numpy as np
import pandas as pd
from hypothesis import strategies as st

from vicinia.engine import Fleet, SimInputs


def make_system(seed: int, H: int, T: int, loss: float = 0.05, feeder_kw: float = 5.0,
                comm_frac: float = 1.0, conn_frac: float = 1.0, outage_frac: float = 0.6):
    """Small random neighbourhood for invariant checks."""
    rng = np.random.default_rng(seed)
    times = pd.date_range("2026-01-01", periods=T, freq="15min", tz="Africa/Lagos")
    hours = times.hour.to_numpy() + times.minute.to_numpy() / 60
    pv_shape = np.clip(np.sin((hours - 6) / 12 * np.pi), 0, None) * rng.uniform(0.3, 1.0, T)
    has_pv = rng.random(H) < 0.5
    has_pv[0] = True
    batt = np.where(rng.random(H) < 0.6, rng.uniform(1, 10, H), 0.0)
    fleet = Fleet(
        archetype=np.array(["x"] * H),
        pv_kwp=np.where(has_pv, rng.uniform(1, 6, H), 0.0),
        batt_kwh=batt,
        batt_kw=np.where(batt > 0, rng.uniform(0.5, 4, H), 0.0),
        gen_kw=np.where(rng.random(H) < 0.5, rng.uniform(0.5, 3, H), 0.0),
        batt_eff_rt=rng.uniform(0.7, 1.0, H),
        batt_min_soc=rng.uniform(0.0, 0.5, H),
        batt_init_soc=rng.uniform(0.0, 1.0, H),
        grid_charge_soc=rng.uniform(0.0, 1.0, H),
    )
    inp = SimInputs(
        times=times,
        dt_h=0.25,
        pv_per_kwp=pv_shape,
        crit_kw=rng.uniform(0, 0.6, (H, T)),
        nonc_kw=rng.uniform(0, 1.5, (H, T)) * (rng.random((H, T)) < 0.7),
        grid_on=rng.random(T) > outage_frac,
        comm_on=rng.random(T) < comm_frac,
        connected=rng.random((H, T)) < conn_frac,
        feeder_kw=np.full(T, feeder_kw),
    )
    return inp, fleet


system_args = st.fixed_dictionaries(
    {
        "seed": st.integers(0, 2**31 - 1),
        "H": st.integers(2, 7),
        "T": st.integers(4, 192),
        "loss": st.floats(0.0, 0.3),
        "feeder_kw": st.floats(0.0, 20.0),
        "comm_frac": st.sampled_from([0.0, 0.5, 1.0]),
        "conn_frac": st.sampled_from([0.5, 0.9, 1.0]),
        "outage_frac": st.floats(0.0, 1.0),
    }
)
