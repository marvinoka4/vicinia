# Limitations

These are the main reasons not to read the results as a forecast for a real
estate. They are listed roughly in order of how much they could change the
headline numbers.

## Data

- **Synthetic loads.** Household load profiles are built from hand-made
  shape templates and noise. They have not been compared with smart meter
  data from Nigerian homes. Real critical loads may be larger (for example
  freezers, water pumps that families treat as essential) or more variable.
- **Synthetic fleet.** The mix of solar homes, battery homes and generator
  owners, and their equipment sizes, are assumptions. Generator ownership
  and battery sizes in particular drive the fuel and coverage numbers.
- **Synthetic weather.** The default solar input is clear-sky irradiance
  times a stochastic sky factor tuned to plausible annual yields. It is not
  a measured weather year, and it applies one factor to all homes, which
  ignores local shading and roof orientation. The PVGIS fetcher exists but
  was not used for the published results because the API was not reachable
  from the build environment.
- **Grid schedule.** Band hours are taken from press reports of the NERC
  Service-Based Tariff, not from the primary order, and the fault and grid
  collapse rates are assumptions, not fitted to feeder logs.
- **No field validation.** Nothing in this repository has been tested on
  real hardware or real households.

## Electrical model

- **Energy only, no power flow.** The feeder is a single transfer limit in
  kW with a flat percentage loss. There is no voltage, phase balance,
  reactive power, protection, or line-by-line network model. A real estate
  network would need an engineering study and a utility or regulator
  agreement before any sharing.
- **Islanded microgrid assumed feasible.** Sharing during a grid outage
  needs grid-forming inverters and anti-islanding arrangements so that no
  energy flows back into a dead utility line. The model assumes this exists.
- **Simplified batteries.** Constant round-trip efficiency, a fixed power
  limit, no degradation, no temperature effects, no lead-acid rate effects.
- **Simplified generators.** A linear fuel curve, no start-up fuel, no
  minimum run time, no maintenance cost. Only CO2 is counted; local air
  pollution and noise, which matter a great deal for health, are not.

## Behaviour and economics

- **Fixed behaviour.** Households do not change consumption in response to
  outages, prices or the knowledge that neighbours can supply them.
- **Simple strategies.** S2 is a rule-based policy with myopic decisions in
  each 15-minute interval. It does not use forecasts. A forecast-aware
  scheduler might do better, and the pooled reference is not a proven upper
  bound.
- **One flat settlement price.** No time-of-use pricing, no auction, no
  credit risk, no payment failures. Cost figures exclude equipment capital
  cost.
- **Benefit metric.** The fairness Gini values extra served energy at the
  generator cost per kWh for every household, including those that do not own
  a generator. That is a simplification.
- **Regulation.** Peer-to-peer electricity trading in Nigeria sits within a
  regulatory framework (NERC and, since the Electricity Act 2023, state
  regulators) that this project does not analyse.

## Ledger

- The ledger is a hash chain held by one party. It makes tampering
  detectable, but it is not a distributed consensus system and does not
  prevent a single operator from rewriting the whole chain. Publishing the
  head hash regularly (for example to all members) would be needed for that.
- Meter data are assumed correct. Metering error and meter tampering are not
  modelled.

## Results in this repository

- Seed variation is covered by five seeds for the Lagos baseline and each
  pressure test (`results/robustness_S2.csv`, `results/seed_variation_lagos.csv`).
  Five seeds show the spread but are not a full uncertainty analysis.
- Over short pressure-test windows, the benefit metric does not value the
  energy left in batteries at the end of the window, which can make
  donors look worse off than they would over a longer period.
- Runtimes depend on the machine and are reported for information only.
