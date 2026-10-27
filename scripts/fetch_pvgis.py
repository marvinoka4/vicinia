"""Fetch a PVGIS typical meteorological year (TMY) for a site preset.

Usage: python scripts/fetch_pvgis.py lagos [--out data/pvgis]

Data source: PVGIS, European Commission Joint Research Centre,
https://re.jrc.ec.europa.eu/pvg_tools/. PVGIS data may be used freely with
acknowledgement of the source; see the PVGIS terms of use. The fetched file
is cached with an attribution header file next to it.

The default run does not need PVGIS. To use the TMY in a scenario, set:

    solar:
      source: pvgis
      pvgis_csv: data/pvgis/lagos_tmy.csv
"""

import argparse
import sys
import urllib.request
from datetime import date, timezone, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from vicinia.solar import SITES  # noqa: E402

API = "https://re.jrc.ec.europa.eu/api/v5_3/tmy"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("site", choices=sorted(SITES))
    ap.add_argument("--out", default="data/pvgis")
    a = ap.parse_args()
    s = SITES[a.site]
    url = f"{API}?lat={s.lat}&lon={s.lon}&outputformat=csv"
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            body = resp.read().decode()
    except Exception as e:  # network blocked or API down
        print(f"could not fetch {url}: {e}", file=sys.stderr)
        return 1
    csv = out / f"{a.site}_tmy.csv"
    csv.write_text(body)
    (out / f"{a.site}_tmy.ATTRIBUTION.txt").write_text(
        f"Source: PVGIS (c) European Union, 2001-{date.today().year}, Joint Research Centre.\n"
        f"Request: {url}\n"
        f"Retrieved: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
    )
    print(f"wrote {csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
