"""Matplotlib figures for results/figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import metrics  # noqa: E402

COLORS = {"S0": "#8a8985", "S1": "#eb6834", "S2": "#2a78d6", "S2-local": "#1baf7a", "S2-pv-only": "#6250d6"}
LABELS = {
    "S0": "S0 islanded",
    "S1": "S1 greedy",
    "S2": "S2 critical-first",
    "S2-local": "S2 reserve only, no sharing",
    "S2-pv-only": "S2 without battery sharing",
}
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
OUTAGE = "#f1efe9"

plt.rcParams.update(
    {
        "figure.facecolor": "#fcfcfb",
        "axes.facecolor": "#fcfcfb",
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK2,
        "axes.titlecolor": INK,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "xtick.color": INK2,
        "ytick.color": INK2,
        "font.size": 9,
        "legend.frameon": False,
        "svg.hashsalt": "vicinia",
    }
)


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)
    return path


def coverage_by_site(df: pd.DataFrame, path: Path) -> Path:
    runs = ["S0", "S1", "S2"]
    sites = list(dict.fromkeys(df["scenario"]))
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    width = 0.26
    x = np.arange(len(sites))
    for i, run in enumerate(runs):
        vals = [float(df[(df.scenario == s) & (df.run == run)]["crit_coverage_outage_pct"].iloc[0]) for s in sites]
        worst = [float(df[(df.scenario == s) & (df.run == run)]["worst_household_crit_coverage_pct"].iloc[0]) for s in sites]
        xs = x + (i - 1) * width
        ax.bar(xs, vals, width - 0.03, color=COLORS[run], label=LABELS[run], zorder=2)
        ax.scatter(xs, worst, marker="_", s=180, color=INK, zorder=3, linewidths=2)
        for xx, v in zip(xs, vals):
            ax.text(xx, v + 1.5, f"{v:.0f}", ha="center", va="bottom", color=INK, fontsize=8)
    ax.scatter([], [], marker="_", s=180, color=INK, linewidths=2, label="worst-off household")
    ax.set_xticks(x, [s.replace("baseline_", "").title() for s in sites])
    ax.set_ylim(0, 110)
    ax.set_ylabel("critical load served during outages (%)")
    ax.set_title("Critical-load coverage during grid outages, one year, 50 households")
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    ax.grid(axis="x", visible=False)
    return _save(fig, path)


def fuel_by_site(df: pd.DataFrame, path: Path) -> Path:
    runs = ["S0", "S1", "S2"]
    sites = list(dict.fromkeys(df["scenario"]))
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    width = 0.26
    x = np.arange(len(sites))
    for i, run in enumerate(runs):
        sub = [df[(df.scenario == s) & (df.run == run)].iloc[0] for s in sites]
        vals = [r["fuel_l"] / 1000 for r in sub]
        xs = x + (i - 1) * width
        ax.bar(xs, vals, width - 0.03, color=COLORS[run], label=LABELS[run], zorder=2)
        for xx, r in zip(xs, sub):
            ax.text(xx, r["fuel_l"] / 1000 + 0.3, f"{r['co2_kg'] / 1000:.0f} t", ha="center", va="bottom", color=INK2, fontsize=7.5)
    ax.set_xticks(x, [s.replace("baseline_", "").title() for s in sites])
    ax.set_ylabel("generator fuel per year (thousand litres)")
    ax.set_title("Generator fuel use (labels: tonnes CO2)")
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    ax.grid(axis="x", visible=False)
    return _save(fig, path)


def household_coverage(results: dict, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    for run in ["S0", "S1", "S2"]:
        cov = np.sort(metrics.household_crit_coverage(results[run])) * 100
        ax.plot(np.arange(1, len(cov) + 1), cov, color=COLORS[run], lw=2, label=LABELS[run], drawstyle="steps-mid")
    ax.set_xlabel("households, sorted from worst to best served")
    ax.set_ylabel("critical coverage in outages (%)")
    ax.set_ylim(-3, 103)
    ax.set_title("Who is left behind: per-household critical coverage (Lagos)")
    ax.legend(loc="lower right")
    return _save(fig, path)


def _outage_spans(ax, times, grid_on):
    off = ~grid_on
    edges = np.flatnonzero(np.diff(np.concatenate([[0], off.astype(int), [0]])))
    for a, b in zip(edges[::2], edges[1::2]):
        ax.axvspan(times[a], times[min(b, len(times) - 1)], color=OUTAGE, lw=0, zorder=0)


def week_timeseries(results: dict, start: int, path: Path, title: str, steps: int | None = None) -> Path:
    r0 = results["S0"]
    inp = r0.inputs
    steps = steps or int(7 * 24 / inp.dt_h)
    sl = slice(start, min(start + steps, len(inp.times)))
    t = inp.times[sl].tz_localize(None)
    dt = inp.dt_h
    fig, axes = plt.subplots(3, 1, figsize=(8, 6.4), sharex=True)
    ax = axes[0]
    _outage_spans(ax, t, inp.grid_on[sl])
    ax.plot(t, r0.ts["pv_kwh"][sl] / dt, color="#eda100", lw=1.2, label="PV generation")
    ax.plot(t, r0.ts["crit_load_kwh"][sl] / dt, color=INK2, lw=1.2, label="critical load")
    ax.fill_between([], [], color=OUTAGE, label="grid outage")
    ax.set_ylabel("kW")
    ax.set_title(title)
    ax.legend(loc="upper right", ncol=3)
    ax = axes[1]
    _outage_spans(ax, t, inp.grid_on[sl])
    for run, ls in (("S1", "--"), ("S0", "-"), ("S2", "-")):
        ax.plot(t, results[run].ts["crit_unserved_kwh"][sl] / dt, color=COLORS[run], lw=1.4, ls=ls, label=LABELS[run])
    ax.set_ylabel("unserved critical kW")
    ax.legend(loc="upper right", ncol=3)
    ax = axes[2]
    _outage_spans(ax, t, inp.grid_on[sl])
    for run in ["S1", "S2"]:
        ax.plot(t, results[run].ts["shared_received_kwh"][sl] / dt, color=COLORS[run], lw=1.4, label=LABELS[run])
    ax.set_ylabel("energy shared, kW")
    ax.legend(loc="upper right", ncol=2)
    fig.autofmt_xdate()
    return _save(fig, path)


def stress_overview(df: pd.DataFrame, path: Path) -> Path:
    scen = list(dict.fromkeys(df["scenario"]))
    runs = ["S0", "S1", "S2"]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    width = 0.26
    x = np.arange(len(scen))
    for i, run in enumerate(runs):
        st = [float(df[(df.scenario == s) & (df.run == run) & (df.case == "stress")]["crit_coverage_outage_pct"].iloc[0]) for s in scen]
        ct = [float(df[(df.scenario == s) & (df.run == run) & (df.case == "control")]["crit_coverage_outage_pct"].iloc[0]) for s in scen]
        xs = x + (i - 1) * width
        ax.bar(xs, st, width - 0.03, color=COLORS[run], label=f"{LABELS[run]} (stressed)", zorder=2)
        ax.scatter(xs, ct, marker="o", s=22, facecolor="#fcfcfb", edgecolor=INK, zorder=3, linewidths=1.2)
        for xx, v in zip(xs, st):
            ax.text(xx, 2, f"{v:.0f}", ha="center", va="bottom", color="white", fontsize=7.5, zorder=4)
    ax.scatter([], [], marker="o", s=22, facecolor="#fcfcfb", edgecolor=INK, label="same window, no stress")
    ax.set_xticks(x, [s.replace("stress_", "").replace("_", " ") for s in scen])
    ax.set_ylim(0, 105)
    ax.set_ylabel("critical coverage in outages (%)")
    ax.set_title("Pressure tests: critical coverage during the stress window")
    ax.legend(ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    ax.grid(axis="x", visible=False)
    return _save(fig, path)


def blackout_detail(results: dict, window: slice, path: Path) -> Path:
    r0 = results["S0"]
    inp = r0.inputs
    pad = int(12 / inp.dt_h)
    sl = slice(max(0, window.start - pad), min(len(inp.times), window.stop + pad))
    t = inp.times[sl].tz_localize(None)
    fig, axes = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    ax = axes[0]
    _outage_spans(ax, t, inp.grid_on[sl])
    load = r0.ts["crit_load_kwh"][sl]
    for run in ["S0", "S1", "S2"]:
        served = 1 - results[run].ts["crit_unserved_kwh"][sl] / np.maximum(load, 1e-9)
        ax.plot(t, 100 * served, color=COLORS[run], lw=1.4, label=LABELS[run])
    ax.set_ylabel("critical load served (%)")
    ax.set_ylim(0, 103)
    ax.set_title("72-hour blackout: critical load served and stored energy")
    ax.legend(loc="lower left", ncol=3)
    ax = axes[1]
    _outage_spans(ax, t, inp.grid_on[sl])
    for run in ["S0", "S1", "S2"]:
        ax.plot(t, results[run].ts["soc_kwh"][sl], color=COLORS[run], lw=1.4, label=LABELS[run])
    ax.set_ylabel("battery energy stored, kWh")
    fig.autofmt_xdate()
    return _save(fig, path)


def sensitivity(df: pd.DataFrame, path: Path) -> Path:
    titles = {"feeder_kw": "feeder capacity (kW)", "loss_fraction": "distribution loss (fraction)", "reserve_soc": "S2 battery reserve (SoC)"}
    fig, axes = plt.subplots(1, 3, figsize=(9, 3), sharey=True)
    for ax, (param, label) in zip(axes, titles.items()):
        sub = df[df.parameter == param]
        ax.plot(sub["value"], sub["crit_coverage_outage_pct"], color=COLORS["S2"], lw=2, marker="o", ms=4, label="all sources")
        ax.plot(sub["value"], sub["crit_coverage_no_gen_pct"], color=COLORS["S2"], lw=2, ls="--", marker="o", ms=4, label="without generators")
        ax.set_xlabel(label)
        if param == "feeder_kw":
            ax.set_xscale("log")
            ax.set_xticks(sub["value"], [f"{v:g}" for v in sub["value"]])
            ax.minorticks_off()
    axes[0].set_ylabel("S2 critical coverage (%)")
    axes[0].set_title("Sensitivity of S2 (Lagos, one year)")
    axes[2].legend(loc="lower left")
    return _save(fig, path)
