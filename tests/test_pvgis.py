"""PVGIS TMY parser on a small fixture in the PVGIS CSV layout."""

from pathlib import Path

import numpy as np

from vicinia import solar

FIXTURE = """Latitude (decimal degrees):\t6.450
Longitude (decimal degrees):\t3.400
Elevation (m):\t20
months selected for TMY:
month,year
1,2010
time(UTC),T2m,RH,G(h),Gb(n),Gd(h),IR(h),WS10m,WD10m,SP
20100101:0700,25.0,80.0,0.0,0.0,0.0,380.0,2.0,200.0,101000
20100101:0800,26.0,78.0,120.0,200.0,60.0,380.0,2.0,200.0,101000
20100101:0900,27.0,75.0,350.0,500.0,110.0,380.0,2.0,200.0,101000
20100101:1000,28.0,70.0,560.0,650.0,150.0,380.0,2.0,200.0,101000

T2m: 2-m air temperature (degree Celsius)
"""


def test_parse_and_map(tmp_path: Path):
    p = tmp_path / "x.csv"
    p.write_text(FIXTURE)
    tmy = solar.load_pvgis_tmy(p)
    assert len(tmy) == 4
    # 09:00 UTC is 10:00 in Lagos.
    assert tmy.loc[(1, 1, 10), "ghi"] == 350.0
    times = solar.make_times("2026-01-01 08:00", 1, 60)[:4]
    poa, temp = solar.pvgis_poa(solar.SITES["lagos"], times, tmy)
    assert poa.shape == (4,) and (poa >= 0).all()
    assert np.isfinite(temp).all()
