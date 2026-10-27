# Assumptions and data sources

vicinia is a model. Every input in the default runs is either synthetic or a
documented parameter. Nothing in `results/` is measured data from real
households, feeders or generators. This file lists each assumption, the value
used, and where it comes from. Values marked **assumption** are judgement calls
made for this project and should be replaced with survey or metered data
before any real deployment decision.

## Time and space

| Item | Value | Basis |
|---|---|---|
| Timestep | 15 minutes | Design choice. Fine enough for load-shedding blocks and PV ramps. |
| Simulation length | 365 days (baselines), 21 days (pressure tests) | Design choice. |
| Time zone | Africa/Lagos (UTC+1, no daylight saving) | Fact. |
| Sites | Lagos (6.45 N, 3.40 E, 41 m), Abuja (9.06 N, 7.49 E, 476 m), Kano (12.00 N, 8.52 E, 488 m) | City-centre coordinates; altitudes approximate. |

## Solar resource

| Item | Value | Basis |
|---|---|---|
| Clear-sky irradiance | pvlib Ineichen model with the pvlib Linke turbidity climatology | pvlib (BSD-3-Clause licence), Holmgren et al., "pvlib python", JOSS 2018. Linke turbidity climatology from Remund et al. (2003) as bundled with pvlib. |
| Array orientation | Facing south, tilt = max(10 degrees, latitude) | **Assumption.** Common rule of thumb for fixed rooftop arrays near the equator. |
| Sky factor | Seeded stochastic multiplier on clear-sky plane-of-array irradiance: day-level AR(1) around a monthly mean, intra-day AR(1) noise that grows on cloudier days, and harmattan dust attenuation in the dry season | **Assumption.** Monthly means in `src/vicinia/solar.py` were tuned by hand so that annual specific yield is about 1,280 kWh/kWp (Lagos), 1,370 (Abuja) and 1,480 (Kano). These sit at or below the range usually quoted for these cities, so PV output is if anything conservative. Not validated against measured data. |
| Performance ratio | 0.80 | **Assumption.** Covers inverter, wiring, soiling and mismatch losses. |
| Temperature derate | -0.4 % per degree C above 25 C cell temperature, cell = 28 C air + 0.03 C per W/m2 | **Assumption.** Typical crystalline silicon coefficient and a simple linear cell temperature model. |
| Harmattan / cloudy week stress | Irradiance multiplied by 0.4 for 7 days | **Assumption** for the pressure test. |
| PVGIS TMY (optional) | `scripts/fetch_pvgis.py` downloads a typical meteorological year from the PVGIS API and saves it with an attribution file | Source: PVGIS, European Commission Joint Research Centre, https://re.jrc.ec.europa.eu/pvg_tools/. Free to use with acknowledgement. The PVGIS API could not be reached from the build environment, so the default runs do not use it. The parser is tested against a fixture in the PVGIS CSV layout, not against a live download. |

## Households

The fleet is drawn from four archetypes. Sizes are drawn uniformly within
each range with a fixed seed. All values are **assumptions** meant to resemble
a mixed-income estate, not survey results.

| Archetype | Share of homes | PV (kWp) | Battery (kWh) | Battery power (kW) | Critical load (kWh/day) | Non-critical load (kWh/day) | Generator |
|---|---|---|---|---|---|---|---|
| solar_battery | 30% | 3.0 to 6.0 | 5 to 15 (lithium iron phosphate) | 3 to 5 | 2.5 to 3.5 | 6 to 10 | 2.8 kW petrol set in 50% of homes |
| battery_only (inverter and battery, no PV) | 10% | 0 | 2.4 to 4.8 (lead-acid) | 1.0 to 1.5 | 1.8 to 2.6 | 3.5 to 6 | 1.6 kW petrol set in 60% of homes |
| grid_only | 56% | 0 | 0 | 0 | 1.2 to 2.2 | 2 to 4.5 | 1.2 kW petrol set in 70% of homes |
| medical | 4% | 0 | 0 | 0 | 1.2 to 2.0 plus a 0.12 kW device running 24 h | 1.5 to 3 | 1.2 kW petrol set in 50% of homes |

Battery parameters (**assumptions**, typical manufacturer guidance):

| Chemistry | Round-trip efficiency | Minimum state of charge |
|---|---|---|
| Lithium iron phosphate (solar_battery) | 90% | 20% |
| Lead-acid (battery_only) | 80% | 50% |

All batteries start at 80% state of charge and charge from the grid, when it
is on, up to 70% state of charge. The gap to 100% leaves room for solar
charging. **Assumption** about typical inverter settings.

### Load profiles

Profiles are built from hourly shape templates in `src/vicinia/loads.py`,
scaled to each home's daily energy, then perturbed with seeded noise
(day-to-day lognormal sigma 0.15, interval noise sigma 0.2 on critical and 0.4
on non-critical load) and shifted by up to one hour per household.

- **Critical**: lighting (evening and early morning), fans (higher at night),
  refrigerator (constant 0.06 kW average), phone charging, and for the medical
  archetype a continuous 0.12 kW device such as an oxygen concentrator.
- **Non-critical**: television and entertainment, ironing and washing, water
  pumping, night-time air conditioning, kitchen appliances.

The split between critical and non-critical is a design choice of this model.
It mirrors how backup systems are commonly wired in Nigerian homes (an
"essential loads" circuit on the inverter), but no survey was used.

## Grid availability

| Item | Value | Basis |
|---|---|---|
| Supply-hour bands | A 20 h, B 16 h, C 12 h, D 8 h, E 4 h minimum per day | NERC Service-Based Tariff bands as reported in the press: ICIR, "How customers can seek compensation over poor power supply, NERC", https://www.icirnigeria.org/how-customers-can-seek-compensation-over-poor-power-supply-nerc/ ; ThisDay, "The Electricity Tariff Hike: Facts and Myths", 16 April 2024. The primary NERC order could not be accessed from the build environment, so the hours are treated as documented assumptions. |
| Baseline band | C (12 h minimum), daily hours drawn as 12 h +/- 2 h (normal) | **Assumption.** Many feeders deliver less than their band minimum. |
| Load shedding | Daily off-hours split into 1 to 3 blocks at random times | **Assumption.** |
| Feeder faults | Poisson, 2 per week, 1 to 6 h each | **Assumption.** |
| National grid collapses | Poisson, 6 per year, 12 to 48 h each | **Assumption** informed by the frequent grid collapses reported in Nigerian media in 2024. Not a measured rate. |
| Resulting grid availability | About 51% of intervals in the Lagos baseline | Model output. |

## Sharing network

| Item | Value | Basis |
|---|---|---|
| Shared feeder transfer limit | 25 kW (sent side) | **Assumption** for a small estate network. |
| Distribution losses | 5% of energy sent | **Assumption**, parameter. Sensitivity run at 0%, 10% and 20%. |
| S2 battery reserve | 30% state of charge, held for the household's own critical load | Parameter. The first version used 50%. The sensitivity sweep (`results/sensitivity_lagos_S2.csv`) showed that a higher reserve lowers community critical coverage and leaves more donor households worse off, including in the 72-hour blackout test, so the default was lowered to 30%. Results for 20% to 80% are published. For lead-acid batteries the reserve cannot go below their 50% minimum. |
| S2 order of battery use | A home's battery serves its own critical load, then its own non-critical load down to the reserve; only energy still above the reserve is offered to neighbours' critical deficits | Design choice: a household is unlikely to accept its battery powering neighbours while its own loads are off. |
| When sharing happens | Only during grid outages and only when communication is up | Design choice. The settlement price is above the grid tariff, so no rational buyer would buy from a neighbour while the grid is on. |
| Arrival order (S1) | Random permutation per interval, seeded | Design choice to model "first come, first served" without bias toward low household indices. |

## Prices and settlement

| Item | Value | Basis |
|---|---|---|
| Grid tariff | 209.50 NGN/kWh | Band A tariff from July 2024 as reported by Arise News, https://www.arise.tv/power-distribution-companies-raise-tariffs-for-band-a-customers-from-n206-80-kwh-to-n209-5-kwh/ . Bands B to E pay less; using Band A overstates grid cost for a Band C feeder. It only affects the cost metric. |
| Petrol price | 1,596 NGN/L (NBS average, May 2026) | Affects only NGN figures, not coverage or fuel volume. National Bureau of Statistics average for May 2026 as reported by Legit.ng, https://www.legit.ng/business-economy/energy/1716120-nbs-reports-petrol-price-climbs-5531-n1596litre-2026/ . Prices moved fast in 2026 (about 1,035 NGN/L in January). |
| Settlement price, PV surplus | 600 NGN/kWh | **Assumption.** Must lie between the grid tariff and the generator cost per kWh; the scenario loader rejects values outside that range. The buyer pays for energy delivered, so the seller bears distribution losses. |
| Settlement price, battery energy | 1,200 NGN/kWh | Parameter. Battery energy has an opportunity cost for the donor. With a single 600 NGN/kWh price, 3 of 50 households (all solar-battery donors) ended the Lagos year (seed 42) worse off than islanded; at 1,200 NGN/kWh none did. The price sweep is published in `results/sensitivity_lagos_S2.csv`. With other seeds and in the pressure tests some donors are still worse off; see `results/robustness_S2.csv`. |
| Money unit in ledger | Integer kobo | Design choice so that netting is exact. |

## Generators and emissions

| Item | Value | Basis |
|---|---|---|
| Fuel curve | litres per hour = 0.25 x rated kW + 0.35 x output kW | Linear fuel curve of the form used in HOMER (fuel curve intercept and slope). Coefficients are an **assumption** for small petrol sets: at 40% load the curve gives about 0.98 L/kWh, at full load 0.60 L/kWh. |
| Generator cost per kWh (for price bounds and benefit) | about 1,556 NGN/kWh at 40% load | Derived from the two rows above. |
| Start threshold | A generator starts only if the remaining deficit is at least 0.1 kW | **Assumption.** People do not start a set for a phone charger. |
| Generator policy | Runs for any remaining deficit (critical and non-critical) | **Assumption** about behaviour. |
| CO2 per litre of petrol | 2.27 kg/L | IPCC 2006 Guidelines for National Greenhouse Gas Inventories, Vol. 2, Ch. 1: default CO2 emission factor for motor gasoline 69,300 kg/TJ (Table 1.4) and net calorific value 44.3 TJ/Gg (Table 1.2), with an assumed density of 0.74 kg/L. Only CO2 is counted; CH4, N2O, CO and particulates are not. |

## Software and licences

All dependencies are open source: numpy (BSD-3), pandas (BSD-3), pvlib (BSD-3),
PyYAML (MIT), matplotlib (matplotlib licence, BSD-style), pytest (MIT),
hypothesis (MPL-2.0). vicinia itself is Apache-2.0. No paid or proprietary
data or software is used.
