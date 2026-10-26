"""Generated reports: results/REPORT.md and a self-contained results/report.html."""

from __future__ import annotations

import base64
import html as _html
from pathlib import Path

import pandas as pd

RUN_LABELS = {
    "S0": "S0 islanded",
    "S1": "S1 greedy",
    "S2": "S2 critical-first",
    "S2-local": "S2 reserve only (no sharing)",
    "S2-pv-only": "S2 without battery sharing",
    "pooled-ref": "Pooled PV + storage reference",
}

HEADLINE_COLS = [
    ("run", "Strategy", None),
    ("crit_coverage_outage_pct", "Critical coverage in outages (%)", "{:.1f}"),
    ("crit_coverage_no_gen_pct", "Of which without generator (%)", "{:.1f}"),
    ("worst_household_crit_coverage_pct", "Worst household (%)", "{:.1f}"),
    ("unserved_crit_kwh", "Unserved critical (kWh)", "{:,.0f}"),
    ("gen_runtime_h", "Generator hours", "{:,.0f}"),
    ("fuel_l", "Fuel (L)", "{:,.0f}"),
    ("co2_kg", "CO2 (t)", "k1000"),
    ("mean_household_cost_ngn", "Mean household cost (NGN)", "{:,.0f}"),
    ("shared_delivered_kwh", "Shared (kWh)", "{:,.0f}"),
    ("curtailment_avoided_kwh", "Curtailment avoided (kWh)", "{:,.0f}"),
    ("gini_benefit", "Gini of benefit", "{:.2f}"),
]

SITE_COLS = [
    ("scenario", "Site", None),
    ("run", "Strategy", None),
    ("crit_coverage_outage_pct", "Critical coverage (%)", "{:.1f}"),
    ("worst_household_crit_coverage_pct", "Worst household (%)", "{:.1f}"),
    ("fuel_l", "Fuel (L)", "{:,.0f}"),
    ("co2_kg", "CO2 (t)", "k1000"),
    ("curtailed_kwh", "PV curtailed (kWh)", "{:,.0f}"),
]

STRESS_COLS = [
    ("scenario", "Pressure test", None),
    ("run", "Strategy", None),
    ("stress_cov", "Critical coverage, stressed (%)", "{:.1f}"),
    ("control_cov", "Same window, no stress (%)", "{:.1f}"),
    ("stress_worst", "Worst household, stressed (%)", "{:.1f}"),
    ("stress_fuel", "Fuel, stressed (L)", "{:,.0f}"),
    ("stress_shared", "Shared, stressed (kWh)", "{:,.0f}"),
]


def _fmt(v, fmt):
    if fmt is None:
        return RUN_LABELS.get(v, str(v).replace("baseline_", "").replace("stress_", "").replace("_", " "))
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "n/a"
    if fmt == "k1000":
        return f"{v / 1000:,.1f}"
    return fmt.format(v)


def _rows(df: pd.DataFrame, cols) -> list[list[str]]:
    return [[_fmt(r.get(c), f) for c, _, f in cols] for _, r in df.iterrows()]


def md_table(df: pd.DataFrame, cols) -> str:
    head = "| " + " | ".join(h for _, h, _ in cols) + " |"
    sep = "|" + "|".join("---" if f is None else "---:" for _, _, f in cols) + "|"
    body = ["| " + " | ".join(r) + " |" for r in _rows(df, cols)]
    return "\n".join([head, sep, *body])


def html_table(df: pd.DataFrame, cols) -> str:
    th = "".join(f'<th class="{"l" if f is None else "r"}">{_html.escape(h)}</th>' for _, h, f in cols)
    trs = []
    for r in _rows(df, cols):
        tds = "".join(f'<td class="{"l" if f is None else "r"}">{_html.escape(v)}</td>' for v, (_, _, f) in zip(r, cols))
        trs.append(f"<tr>{tds}</tr>")
    return f'<div class="tw"><table><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'


def stress_pivot(stress: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (scen, run), g in stress[stress.run.isin(["S0", "S1", "S2"])].groupby(["scenario", "run"], sort=False):
        s = g[g.case == "stress"].iloc[0]
        c = g[g.case == "control"].iloc[0]
        rows.append(
            {
                "scenario": scen,
                "run": run,
                "stress_cov": s["crit_coverage_outage_pct"],
                "control_cov": c["crit_coverage_outage_pct"],
                "stress_worst": s["worst_household_crit_coverage_pct"],
                "stress_fuel": s["fuel_l"],
                "stress_shared": s["shared_delivered_kwh"],
            }
        )
    return pd.DataFrame(rows)


def _facts(base: pd.DataFrame, stress: pd.DataFrame, sens: pd.DataFrame, rt: pd.DataFrame, led: dict) -> dict:
    lag = base[base.scenario == "baseline_lagos"].set_index("run")
    f = {"lagos": lag}
    s0, s1, s2 = lag.loc["S0"], lag.loc["S1"], lag.loc["S2"]
    f["s0"], f["s1"], f["s2"] = s0, s1, s2
    f["fuel_cut_pct_s2"] = 100 * (1 - s2["fuel_l"] / s0["fuel_l"])
    f["fuel_cut_pct_s1"] = 100 * (1 - s1["fuel_l"] / s0["fuel_l"])
    f["runtime_s2"] = float(rt[rt.run == "S2"]["runtime_s"].iloc[0])
    f["runtime_max"] = float(rt["runtime_s"].max())
    f["days"] = float(rt["days"].iloc[0])
    return f


def _intro(base, stress, sens, rt, led, quick) -> list[str]:
    f = _facts(base, stress, sens, rt, led)
    s0, s1, s2, lag = f["s0"], f["s1"], f["s2"], f["lagos"]
    pooled = lag.loc["pooled-ref"]["crit_coverage_no_gen_pct"] if "pooled-ref" in lag.index else float("nan")
    lines = []
    if quick:
        lines.append("> Smoke run with shortened baselines (28 days). Numbers are not the published results.")
        lines.append("")
    lines += [
        "All inputs are synthetic (see docs/assumptions.md). These are model results, not field measurements.",
        "",
        "## Headline: Lagos, 50 households, one year",
        "",
        f"- Critical-load coverage during grid outages: S0 islanded {s0['crit_coverage_outage_pct']:.1f}%, "
        f"S1 greedy {s1['crit_coverage_outage_pct']:.1f}%, S2 critical-first {s2['crit_coverage_outage_pct']:.1f}%.",
        f"- Worst-off household's critical coverage: S0 {s0['worst_household_crit_coverage_pct']:.1f}%, "
        f"S1 {s1['worst_household_crit_coverage_pct']:.1f}%, S2 {s2['worst_household_crit_coverage_pct']:.1f}%.",
        f"- Generator fuel: S0 {s0['fuel_l']:,.0f} L, S1 {s1['fuel_l']:,.0f} L ({f['fuel_cut_pct_s1']:.1f}% less), "
        f"S2 {s2['fuel_l']:,.0f} L ({f['fuel_cut_pct_s2']:.1f}% less), "
        f"which is {s2['co2_avoided_kg'] / 1000:,.1f} t CO2 avoided per year with S2.",
        f"- Critical coverage from PV, batteries and sharing alone (no generator): S0 {s0['crit_coverage_no_gen_pct']:.1f}%, "
        f"S2 {s2['crit_coverage_no_gen_pct']:.1f}%, against {pooled:.1f}% for a lossless pooled reference with the same equipment.",
        f"- The S2 battery reserve without sharing (S2-local) gives {lag.loc['S2-local']['crit_coverage_outage_pct']:.1f}%, "
        f"and S2 without battery sharing gives {lag.loc['S2-pv-only']['crit_coverage_outage_pct']:.1f}%, so most of the S2 gain "
        "comes from routing stored energy to neighbours' critical loads.",
        f"- Settlement ledger for S2: {led['entries']:,} hash-chained entries, verify() = {led['verified']}, "
        f"altering one entry detected = {led['tamper_detected']}, largest daily netting imbalance = {led['daily_netting_max_abs_kobo']} kobo.",
        f"- Runtime for one simulated year ({f['days']:.0f} days, 15-minute steps, 50 households): "
        f"{f['runtime_max']:.1f} s or less per strategy on {rt['machine'].iloc[0]}.",
        "",
    ]
    return lines


def seed_summary(seeds: pd.DataFrame) -> pd.DataFrame:
    s0 = seeds[seeds.run == "S0"].set_index("seed")["fuel_l"]
    seeds = seeds.assign(fuel_cut_pct=[100 * (1 - r.fuel_l / s0[r.seed]) for r in seeds.itertuples()])
    rows = []
    for run, g in seeds.groupby("run", sort=False):
        row = {"run": run, "n": len(g)}
        for c in ("crit_coverage_outage_pct", "worst_household_crit_coverage_pct", "fuel_cut_pct"):
            row[c + "_mean"] = g[c].mean()
            row[c + "_min"] = g[c].min()
            row[c + "_max"] = g[c].max()
        rows.append(row)
    return pd.DataFrame(rows)


def _seed_rows(seeds: pd.DataFrame) -> pd.DataFrame:
    ss = seed_summary(seeds)
    rng = lambda r, c: f"{r[c + '_mean']:.1f} ({r[c + '_min']:.1f} to {r[c + '_max']:.1f})"  # noqa: E731
    return pd.DataFrame(
        {
            "run": ss["run"],
            "n": ss["n"],
            "cov": [rng(r, "crit_coverage_outage_pct") for _, r in ss.iterrows()],
            "worst": [rng(r, "worst_household_crit_coverage_pct") for _, r in ss.iterrows()],
            "fuel": [rng(r, "fuel_cut_pct") for _, r in ss.iterrows()],
        }
    )


SEED_COLS = [
    ("run", "Strategy", None),
    ("n", "Seeds", "{:d}"),
    ("cov", "Critical coverage, mean (min to max) %", "{}"),
    ("worst", "Worst household, mean (min to max) %", "{}"),
    ("fuel", "Fuel cut vs S0, mean (min to max) %", "{}"),
]


def write_report_md(out: Path, base, stress, sens, rt, led, quick, seeds=None) -> Path:
    lag = base[base.scenario == "baseline_lagos"]
    sp = stress_pivot(stress)
    lines = ["# vicinia results", ""]
    lines += _intro(base, stress, sens, rt, led, quick)
    lines += [
        "![Critical coverage by site](figures/coverage_by_site.png)",
        "",
        "## Strategy comparison, Lagos",
        "",
        md_table(lag, HEADLINE_COLS),
        "",
        "Gini of benefit is computed over per-household benefit relative to S0 "
        "(cost saving plus extra energy served valued at generator cost), clipped at zero. "
        "Mean household cost is grid plus fuel plus net settlement payments over the year. "
        "The pooled reference has no generators and no losses; compare it with the 'without generator' column.",
        "",
        "![Per-household coverage](figures/household_coverage_lagos.png)",
        "",
        "![One week in Lagos](figures/week_lagos.png)",
        "",
        "## By site",
        "",
        md_table(base[base.run.isin(["S0", "S1", "S2"])], SITE_COLS),
        "",
        "![Fuel by site](figures/fuel_by_site.png)",
        "",
        "## Pressure tests",
        "",
        "Each test is a 21-day run. Metrics cover only the stress window, and the control column is the same "
        "window with the stress event removed.",
        "",
        md_table(sp, STRESS_COLS),
        "",
        "![Pressure tests](figures/stress_tests.png)",
        "",
        "![72-hour blackout](figures/blackout_72h.png)",
        "",
    ]
    peak = stress[(stress.scenario == "stress_feeder_halved") & (stress.case == "control") & (stress.run == "S2")]
    if len(peak):
        lines += [
            f"Feeder note: peak transfer in the feeder test window without stress was {peak['peak_transfer_kw'].iloc[0]:.1f} kW, "
            "below the halved limit of 12.5 kW, so halving the feeder did not bind. The sensitivity sweep below shows where it does.",
            "",
        ]
    lines += [
        "## Sensitivity of S2 (Lagos)",
        "",
        md_table(
            sens,
            [
                ("parameter", "Parameter", None),
                ("value", "Value", "{:g}"),
                ("crit_coverage_outage_pct", "Critical coverage (%)", "{:.1f}"),
                ("crit_coverage_no_gen_pct", "Without generator (%)", "{:.1f}"),
                ("worst_household_crit_coverage_pct", "Worst household (%)", "{:.1f}"),
                ("fuel_l", "Fuel (L)", "{:,.0f}"),
                ("peak_transfer_kw", "Peak transfer (kW)", "{:.1f}"),
            ],
        ).replace("| feeder kw |", "| feeder_kw |").replace("| loss fraction |", "| loss_fraction |").replace("| reserve soc |", "| reserve_soc |"),
        "",
        "![Sensitivity](figures/sensitivity_lagos.png)",
        "",
        "## Seed-to-seed variation (Lagos)",
        "",
        "Each seed draws a new fleet, new load profiles, new weather and a new grid schedule.",
        "",
        md_table(_seed_rows(seeds), SEED_COLS) if seeds is not None else "Not run.",
        "",
        "## Runtime",
        "",
        md_table(
            rt,
            [("run", "Strategy", None), ("days", "Days", "{:.0f}"), ("households", "Households", "{:d}"),
             ("intervals", "Intervals", "{:,d}"), ("runtime_s", "Runtime (s)", "{:.2f}"), ("ledger_entries", "Ledger entries", "{:,d}")],
        ),
        "",
        "Generated by `make reproduce`. Do not edit by hand.",
        "",
    ]
    p = out / "REPORT.md"
    p.write_text("\n".join(lines))
    return p


CSS = """
:root{--bg:#fcfcfb;--card:#ffffff;--ink:#0b0b0b;--ink2:#52514e;--rule:#e4e3df;--accent:#2a78d6;--warn:#8a5a00}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#1a1a19;--card:#232322;--ink:#f0efec;--ink2:#c3c2b7;--rule:#3a3a38;--accent:#3987e5;--warn:#e0b050}}
:root[data-theme="dark"]{--bg:#1a1a19;--card:#232322;--ink:#f0efec;--ink2:#c3c2b7;--rule:#3a3a38;--accent:#3987e5;--warn:#e0b050}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1040px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:28px;margin:8px 0 4px}h2{font-size:20px;margin:36px 0 10px;padding-top:8px;border-top:1px solid var(--rule)}
p.lede{color:var(--ink2);margin:0 0 16px;max-width:760px}
.note{color:var(--warn);font-size:14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:16px 0}
.tile{background:var(--card);border:1px solid var(--rule);border-radius:10px;padding:14px 16px}
.tile .k{font-size:13px;color:var(--ink2)}.tile .v{font-size:26px;font-weight:650;margin:2px 0}.tile .s{font-size:13px;color:var(--ink2)}
ul.facts{padding-left:20px;max-width:860px}ul.facts li{margin:4px 0}
figure{margin:16px 0;background:#fcfcfb;border:1px solid var(--rule);border-radius:10px;padding:8px}
figure img{width:100%;height:auto;display:block}
figcaption{font-size:13px;color:#52514e;padding:4px 6px 0}
.tw{overflow-x:auto;border:1px solid var(--rule);border-radius:10px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th,td{padding:7px 10px;border-bottom:1px solid var(--rule);white-space:nowrap}
th{color:var(--ink2);font-weight:600;background:var(--card);position:sticky;top:0}
td.l,th.l{text-align:left}td.r,th.r{text-align:right}
tbody tr:last-child td{border-bottom:none}
code{font-size:13px}
footer{margin-top:40px;color:var(--ink2);font-size:13px}
"""


def _img(path: Path, caption: str) -> str:
    data = base64.b64encode(path.read_bytes()).decode()
    return (
        f'<figure><img alt="{_html.escape(caption)}" src="data:image/png;base64,{data}">'
        f"<figcaption>{_html.escape(caption)}</figcaption></figure>"
    )


def write_report_html(out: Path, base, stress, sens, rt, led, quick, seeds=None) -> Path:
    f = _facts(base, stress, sens, rt, led)
    s0, s1, s2, lag = f["s0"], f["s1"], f["s2"], f["lagos"]
    fig = out / "figures"
    intro = _intro(base, stress, sens, rt, led, quick)
    facts = [ln[2:] for ln in intro if ln.startswith("- ")]
    tiles = [
        ("Critical coverage in outages", f"{s2['crit_coverage_outage_pct']:.1f}%", f"S2, against {s0['crit_coverage_outage_pct']:.1f}% islanded"),
        ("Worst-off household", f"{s2['worst_household_crit_coverage_pct']:.1f}%", f"S2, against {s0['worst_household_crit_coverage_pct']:.1f}% islanded"),
        ("Generator fuel avoided", f"{s2['fuel_saved_l']:,.0f} L", f"{f['fuel_cut_pct_s2']:.1f}% of islanded use, {s2['co2_avoided_kg'] / 1000:,.1f} t CO2"),
        ("Ledger", f"{led['entries']:,}", "entries, chain verified" if led["verified"] else "entries, chain FAILED"),
    ]
    tiles_html = "".join(
        f'<div class="tile"><div class="k">{_html.escape(k)}</div><div class="v">{_html.escape(v)}</div><div class="s">{_html.escape(s)}</div></div>'
        for k, v, s in tiles
    )
    sp = stress_pivot(stress)
    body = f"""
<main>
<h1>vicinia</h1>
<p class="lede">Neighbourhood solar sharing for Nigerian estates during grid outages: simulation results for 50 households over one year, with three sharing strategies, five pressure tests and a hash-chained settlement ledger.</p>
{'<p class="note">Smoke run with shortened baselines. Numbers are not the published results.</p>' if quick else ''}
<p class="note">All inputs are synthetic (loads, fleet, grid schedule, weather factor). These are model results, not field measurements.</p>
<div class="tiles">{tiles_html}</div>
<h2>Headline: Lagos, 50 households, one year</h2>
<ul class="facts">{''.join(f'<li>{_html.escape(x)}</li>' for x in facts)}</ul>
{_img(fig / 'coverage_by_site.png', 'Share of critical load served during grid outages, by site and strategy. The black tick marks the worst-off household.')}
<h2>Strategy comparison, Lagos</h2>
{html_table(lag.reset_index(), HEADLINE_COLS)}
<p class="lede">The pooled reference has no generators and no losses; compare it with the "without generator" column. S2 reserve only and S2 without battery sharing are ablations that separate the effects of the battery reserve and of battery sharing.</p>
{_img(fig / 'household_coverage_lagos.png', 'Per-household critical coverage, sorted. Islanded operation leaves homes without storage or generators with nothing during outages.')}
{_img(fig / 'week_lagos.png', 'One week in Lagos. Shaded bands are grid outages.')}
<h2>By site</h2>
{html_table(base[base.run.isin(['S0', 'S1', 'S2'])], SITE_COLS)}
{_img(fig / 'fuel_by_site.png', 'Generator fuel per year by site and strategy.')}
<h2>Pressure tests</h2>
<p class="lede">Each test is a 21-day run. Metrics cover the stress window only; the control is the same window with the event removed.</p>
{html_table(sp, STRESS_COLS)}
{_img(fig / 'stress_tests.png', 'Critical coverage during each stress window. Hollow circles show the same window without the stress event.')}
{_img(fig / 'blackout_72h.png', 'The 72-hour blackout in detail: critical load served and total stored battery energy.')}
<h2>Seed-to-seed variation (Lagos)</h2>
<p class="lede">Each seed draws a new fleet, new load profiles, new weather and a new grid schedule.</p>
{html_table(_seed_rows(seeds), SEED_COLS) if seeds is not None else ''}
<h2>Sensitivity of S2</h2>
{_img(fig / 'sensitivity_lagos.png', 'One-at-a-time sensitivity of S2 critical coverage to feeder capacity, distribution losses and battery reserve.')}
<h2>Settlement ledger</h2>
<p class="lede">Every transfer in the Lagos S2 run is a ledger entry chained with SHA-256. verify() = {led['verified']}. After altering entry {led.get('tampered_index')} in a copy, verify() fails at entry {led.get('first_invalid_after_tamper')}. Head hash: <code>{_html.escape(str(led.get('head_hash', ''))[:16])}...</code></p>
<footer>Generated by <code>make reproduce</code> from fixed seeds. Source: github.com/marvinoka4/vicinia. Apache-2.0.</footer>
</main>
"""
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>vicinia results</title><style>{CSS}</style></head><body>{body}</body></html>"
    )
    p = out / "report.html"
    p.write_text(page)
    return p
