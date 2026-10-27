# vicinia: neighbourhood solar sharing that keeps critical loads on during Nigerian grid outages

In a simulated Lagos neighbourhood of 50 homes over one year, sharing solar
and battery energy critical loads first raised critical-load coverage
during grid outages from 68.4% to 98.1% and cut generator petrol use by
29.7% (23.6% to 32.9% across five seeds). These results come from a
tested, reproducible simulation with synthetic inputs, not field
measurements.

## Primary track

RESILIENT

## Problem

Many Nigerian electricity feeders supply 4 to 16 hours a day, and national
grid collapses can cut supply for a day or more. In the same estate, homes
with rooftop solar and batteries often waste midday surplus because they
cannot export it, while neighbours without solar run small petrol
generators for lights, fans, a fridge, phone charging and sometimes medical
devices. Those generators are expensive (petrol at 1,596 NGN per litre,
NBS average, May 2026), noisy, polluting and a source of CO2.

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

## Where this fits

NERC's [Net Billing Regulations 2026](https://www.dlapiperafrica.com/en/nigeria/insights/2026/nerc_net_billing_regulations_2026), issued on 3 June 2026, let
grid-connected solar systems of 50 kWp to 1.5 MWp sell surplus to the
distribution company while the grid is up. Typical home rooftop systems
fall below that size, and vicinia targets the other case: small
residential systems sharing with neighbours while the grid is down, so the
two are complementary. Low-voltage DC mesh grids that share power between
solar home systems are already being deployed in Nigeria, for example by
[Okra Solar under the DARES programme](https://www.okrasolar.com/blog/dares-is-out-mesh-grids-are-in). vicinia's allocation and
settlement layer does not depend on a particular hardware design and could
in principle run on such a physical layer; this has not been tested.

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
- Tests: 50 tests. Hypothesis generates random neighbourhoods and checks
  per-household energy balance, sent minus losses equals received every
  interval, battery state of charge within bounds and consistent with the
  flows, feeder limit respected, no household receiving more than its
  deficit, ledger matching the physical flows, netting to zero, tamper
  detection for any altered field, and deterministic results for a fixed
  seed.
- `make reproduce` regenerates every CSV, figure, `results/REPORT.md` and
  the HTML report from fixed seeds in about 10 minutes.

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
- Lagos is the headline case. Abuja and Kano runs, with the same fleet,
  loads and grid schedule, give near-identical results because shortfalls
  fall mostly at night, so battery capacity and outage timing dominate
  irradiance.
- Costs use petrol at 1,596 NGN/L (NBS average, May 2026). The fuel price
  affects only NGN figures, not coverage or fuel volume.
- Pressure tests, critical coverage during the stress window for S0 / S1 /
  S2 (seed 42): 72-hour blackout 67.6 / 74.0 / 94.1%; harmattan week at
  40% irradiance 69.8 / 71.3 / 96.7%; largest contributor drops out 68.9 /
  74.8 / 97.4%; feeder halved 68.9 / 75.0 / 97.1%; 48-hour communication
  loss 71.1 / 71.1 / 71.6%, with no transfers or ledger entries, which is
  the intended fallback to islanded operation. On critical coverage,
  sharing never did worse than islanded. Halving the feeder had no effect
  because peak transfers stayed below the halved limit.

### How the defaults were chosen

The S2 battery reserve (30%) and the
two-tier settlement price (600 NGN/kWh for PV surplus, 1,200 NGN/kWh for
battery energy) were set after a sensitivity sweep on the Lagos baseline,
not before it. The sweep produced a result in its own right: with one flat
price, battery donors subsidise their neighbours, because they sell stored
energy at 600 NGN/kWh and later serve less of their own load or refill it
with petrol at about 1,556 NGN/kWh. Coverage and fuel do not depend on
price; only who gains does.

| S2 setting (Lagos, seed 42, one year) | Critical coverage | Worst-off household | Households worse off than S0 |
|---|---:|---:|---:|
| Original: 50% reserve, flat 600 NGN/kWh | 95.3% | 82.7% | 11 |
| Chosen: 30% reserve, two-tier price | 98.1% | 93.8% | 0 |

Sweep figures: https://github.com/marvinoka4/vicinia/blob/main/results/figures/defaults_sweep_lagos.png
and https://github.com/marvinoka4/vicinia/blob/main/results/figures/sensitivity_lagos.png

### Robustness

The chosen defaults were then run, without retuning, on five seeds for the
Lagos year and for every pressure test:

| Scenario | S2 critical coverage | S2 worst-off household | Households worse off than S0, per seed |
|---|---:|---:|---:|
| Lagos baseline, full year | 98.1 to 99.0% | 92.0 to 94.7% | 0, 0, 0, 4, 0 |
| 72-hour blackout | 94.1 to 97.5% | 69.4 to 87.0% | 3, 4, 4, 10, 3 |
| Harmattan week | 96.7 to 99.7% | 88.5 to 98.4% | 3, 3, 0, 4, 0 |
| Contributor drops out | 97.4 to 100.0% | 90.4 to 100.0% | 1, 1, 1, 0, 0 |
| Feeder halved | 97.1 to 99.9% | 90.2 to 99.7% | 1, 0, 0, 2, 0 |
| Communication loss | 71.6 to 83.6% | 0.0% | 3, 17, 15, 15, 0 |

Some households are left worse off than islanded, and all of them are
solar-battery donors. On the full year one seed in five leaves 4 donors
worse off, all generator owners who refill their own load with petrol that
costs more per kWh than they earn. Over the short stress windows up to 10
donors are worse off, and up to 17 during communication loss. Window
counts do not value energy left in batteries at the end, so they overstate
the loss somewhat; they are reported as measured. Two-tier pricing reduces
the subsidy from donors but does not remove it in every case.

### Ledger, runtime and figures

- Ledger for the Lagos S2 year: 786,978 entries, chain verifies, an altered
  entry is detected, daily netting balances to 0 kobo.
- Runtime for one simulated year of 50 households: 2.2 s (S0), 4.8 s (S1),
  12.6 s (S2).

Figures:

- Interactive report: https://marvinoka4.github.io/vicinia/
- Critical coverage, Lagos: https://github.com/marvinoka4/vicinia/blob/main/results/figures/coverage_lagos.png
- Pressure tests: https://github.com/marvinoka4/vicinia/blob/main/results/figures/stress_tests.png
- 72-hour blackout detail: https://github.com/marvinoka4/vicinia/blob/main/results/figures/blackout_72h.png
- Per-household coverage: https://github.com/marvinoka4/vicinia/blob/main/results/figures/household_coverage_lagos.png
- Sensitivity: https://github.com/marvinoka4/vicinia/blob/main/results/figures/sensitivity_lagos.png
- Full results: https://github.com/marvinoka4/vicinia/blob/main/results/REPORT.md

Main limitations: synthetic loads and fleet, no field validation, an
energy-only electrical model (no power flow), and the assumption that
inverters can form a safe island during outages. 

A real deployment needs things this model does not cover: inverters able to form and hold a safe island during outages, anti-islanding protection so nothing back-feeds the grid when supply returns, protection coordination on the shared feeder, and metering and communications for every home. The cost of that hardware is not included in the economics.
See `docs/limitations.md`.

## Source code

https://github.com/marvinoka4/vicinia

## Licence

Apache-2.0

## Demo

Report: https://marvinoka4.github.io/vicinia/

The page is `results/report.html`, a self-contained static report (no
server or network needed) generated by `make reproduce` and deployed to
GitHub Pages on every push to main. Screenshots are in
https://github.com/marvinoka4/vicinia/tree/main/docs/img . To run it
yourself:

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
