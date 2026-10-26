# vicinia: neighbourhood solar sharing that keeps critical loads on during Nigerian grid outages

## Primary track

RESILIENT

## Problem

Many Nigerian electricity feeders supply 4 to 16 hours a day, and national
grid collapses can cut supply for a day or more. In the same estate, homes
with rooftop solar and batteries often waste midday surplus because they
cannot export it, while neighbours without solar run small petrol
generators for lights, fans, a fridge, phone charging and sometimes medical
devices. Those generators are expensive (petrol averaged about 1,596 NGN per
litre in May 2026 according to the National Bureau of Statistics), noisy,
polluting and a source of CO2.

The question this project answers with evidence: if neighbours share
energy locally during outages, critical loads first, how much does
critical-load coverage improve, how much generator fuel and CO2 is avoided,
and does the scheme degrade safely when things go wrong?

## Solution

vicinia is an open-source simulation and settlement engine for a
neighbourhood sharing scheme. During grid outages, surplus from solar homes
is routed over a shared feeder to neighbours. Every transfer is recorded on
a hash-chained ledger and settled at a price between the grid tariff and
the cost of generator power, so buyers pay less than running their own
generator and sellers earn from energy they would otherwise waste.

Three strategies are compared on the same simulated neighbourhood:

- S0 islanded: each home uses only its own PV, battery and generator.
- S1 greedy: PV surplus goes to whole household deficits in arrival order.
- S2 critical-first: PV surplus goes pro-rata to critical loads before any
  non-critical load. Batteries keep a reserve for their owner's critical
  load and offer energy above it to neighbours' critical deficits.

If communication fails, no transfers can be coordinated or settled, and
every home falls back to islanded operation.

## Technical implementation

- Python 3.11, numpy, pandas, pvlib, PyYAML, matplotlib; pytest and
  hypothesis for tests. All open source, versions pinned.
- 15-minute timestep, up to a year, vectorised over households.
- Solar: pvlib clear-sky irradiance for Lagos, Abuja or Kano on a tilted
  plane, times a seeded stochastic sky factor for cloud, rainy-season
  overcast and harmattan dust. An optional PVGIS TMY fetcher is included
  but was not used for the results because the API was not reachable from
  the build environment.
- Households: four synthetic archetypes (solar plus battery, inverter
  battery only, grid only, and a home with a medical device), with loads
  split into critical and non-critical and optional petrol generators with
  a linear fuel curve.
- Grid: NERC supply-hour bands (A 20 h to E 4 h, as reported in the press)
  plus random load-shedding blocks, feeder faults and multi-day collapses.
- Network: a shared feeder transfer limit (25 kW) and 5% distribution
  losses. Pairwise transfers are derived from the allocation so that every
  ledger entry is a real sender-to-receiver flow.
- Ledger: each entry holds interval, sender, receiver, kWh sent, kWh
  received after losses, price and amount in integer kobo. Each hash is
  SHA-256 of the previous hash plus the entry. `verify()` recomputes the
  chain; netting is per day and per household.
- Tests: 44 tests. Hypothesis generates random neighbourhoods and checks
  per-household energy balance, sent minus losses equals received every
  interval, battery state of charge within bounds and consistent with the
  flows, feeder limit respected, no household receiving more than its
  deficit, ledger matching the physical flows, netting to zero, tamper
  detection for any altered field, and deterministic results for a fixed
  seed.
- `make reproduce` regenerates every CSV, figure, `results/REPORT.md` and
  the HTML report from fixed seeds in about 7.5 minutes.

## Evidence

All inputs are synthetic and every assumption is documented with its
source in `docs/assumptions.md`. These are model results, not field
measurements.

Lagos, 50 households, one year, Band C feeder (grid on about 51% of the
time):

| Strategy | Critical coverage in outages | Worst-off household | Generator fuel (L/yr) | CO2 (t/yr) |
|---|---:|---:|---:|---:|
| S0 islanded | 68.4% | 0.0% | 25,684 | 58.3 |
| S1 greedy | 76.2% | 15.7% | 22,396 | 50.8 |
| S2 critical-first | 98.1% | 93.8% | 18,053 | 41.0 |

- S2 avoids 7,631 L of petrol and 17.3 t of CO2 a year for 50 homes, a
  29.7% cut. Across five random seeds (new fleet, loads, weather and grid
  each time) the fuel cut ranges from 23.6% to 32.9% and S2 critical
  coverage from 98.1% to 99.0%.
- Excluding generators, S2 meets 96.3% of critical load during outages from
  PV, batteries and sharing alone, against 42.2% islanded.
- Ablations show where the gain comes from: the S2 battery reserve without
  sharing gives 68.8%, and S2 without battery sharing gives 76.9%.
- No household ends the year worse off than islanded under S1 or S2. This
  needed a separate price for battery-sourced energy (1,200 NGN/kWh against
  600 NGN/kWh for PV surplus); with one 600 NGN/kWh price, 3 solar-battery
  donors were worse off. The price sweep is published.
- Pressure tests, critical coverage during the stress window for S0 / S1 /
  S2: 72-hour blackout 71.4 / 78.3 / 93.3%; harmattan week at 40%
  irradiance 71.2 / 78.7 / 98.0%; largest contributor drops out 72.7 /
  82.0 / 98.3%; feeder halved 72.3 / 83.9 / 99.5%; 48-hour communication
  loss 71.4 / 71.4 / 72.0%, with no transfers or ledger entries, which is
  the intended fallback to islanded operation. Sharing never did worse
  than islanded. Halving the feeder had no effect because peak transfers
  stayed below the halved limit.
- Ledger for the Lagos S2 year: 786,978 entries, chain verifies, an altered
  entry is detected, daily netting balances to 0 kobo.
- Runtime for one simulated year of 50 households: 2.7 s (S0), 4.5 s (S1),
  10.4 s (S2).

Figures:

- Critical coverage by site: https://github.com/marvinoka4/vicinia/blob/main/results/figures/coverage_by_site.png
- Pressure tests: https://github.com/marvinoka4/vicinia/blob/main/results/figures/stress_tests.png
- 72-hour blackout detail: https://github.com/marvinoka4/vicinia/blob/main/results/figures/blackout_72h.png
- Per-household coverage: https://github.com/marvinoka4/vicinia/blob/main/results/figures/household_coverage_lagos.png
- Sensitivity: https://github.com/marvinoka4/vicinia/blob/main/results/figures/sensitivity_lagos.png
- Full results: https://github.com/marvinoka4/vicinia/blob/main/results/REPORT.md

Main limitations: synthetic loads and fleet, no field validation, an
energy-only electrical model (no power flow), and the assumption that
inverters can form a safe island during outages. See `docs/limitations.md`.

## Source code

https://github.com/marvinoka4/vicinia

## Licence

Apache-2.0

## Demo

`results/report.html` is a self-contained static report (no server or
network needed) generated by `make reproduce`. Screenshots are in
`docs/img/`. To run it yourself:

```bash
git clone https://github.com/marvinoka4/vicinia && cd vicinia
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
vicinia compare --scenario scenarios/baseline_lagos.yaml
```

## What was built during HACK4EARTH

Everything in the repository was built from scratch in late October 2026
during HACK4EARTH 2.0: the simulation engine, the solar, load and grid
models, the three strategies, the settlement ledger, the tests, the
pressure tests, the reproduce pipeline, the report and the documentation.
Only the idea existed before the hackathon. The git history shows the build.

## Team

Marvin Okafor (solo)
