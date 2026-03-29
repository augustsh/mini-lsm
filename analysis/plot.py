# Copyright 2026 preemptive-lsm authors
# Licensed under the Apache License, Version 2.0
# This file is part of the preemptive-lsm project.
# It is original work and not derived from mini-lsm.
#
# Usage:
#   python analysis/plot.py results.json --out results/plots
#   python analysis/plot.py heavy.json write_heavy.json --out results/plots/combined

import argparse
import json
import pathlib
import sys

try:
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm
    import numpy as np
except ImportError:
    sys.exit("Install matplotlib and numpy: pip install matplotlib numpy")


# Tail-latency focused: skip p50 (uninformative), include max.
PERCENTILES       = ["p95_us", "p99_us", "p999_us", "max_us"]
PERCENTILE_LABELS = ["p95",    "p99",    "p99.9",   "max"]


def _strategy_colors(strategies):
    palette = cm.tab10(np.linspace(0, 1, max(len(strategies), 3)))
    return {s: palette[i] for i, s in enumerate(strategies)}


def _rolling_mean(ys, window=10):
    """Simple rolling mean; returns same-length array (partial windows at edges)."""
    arr = np.array(ys, dtype=float)
    out = np.full(len(arr), np.nan)
    cumsum = np.nancumsum(arr)
    for i in range(len(arr)):
        lo = max(0, i - window + 1)
        n = i - lo + 1
        out[i] = (cumsum[i] - (cumsum[lo - 1] if lo > 0 else 0)) / n
    return out


def load_results(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def _pct_diff_label(val, baseline):
    """Format a value with its % difference from baseline."""
    if baseline and baseline != 0:
        pct = (val - baseline) / baseline * 100
        sign = "+" if pct >= 0 else ""
        return f"{val:.1f}\n({sign}{pct:.1f}%)"
    return f"{val:.1f}"


# ---------------------------------------------------------------------------
# Per-workload bar chart (one figure per workload)
# Tight y-axis, shows % diff from NoYield baseline
# ---------------------------------------------------------------------------
def plot_latency_comparison(results: list[dict], out_dir: pathlib.Path) -> None:
    strategies = sorted({r["strategy"] for r in results})
    workloads  = sorted({r["workload"]  for r in results})
    colors     = _strategy_colors(strategies)

    for workload in workloads:
        fig, axes = plt.subplots(1, len(PERCENTILES), figsize=(16, 5), sharey=False)
        fig.suptitle(f"Latency — Workload {workload}", fontsize=14)

        for ax, pct, label in zip(axes, PERCENTILES, PERCENTILE_LABELS):
            values = []
            for strategy in strategies:
                matching = [r[pct] for r in results
                            if r["strategy"] == strategy and r["workload"] == workload]
                values.append(np.mean(matching) if matching else 0)

            # NoYield baseline for % diff labels
            baseline_val = None
            if "NoYield" in strategies:
                idx = strategies.index("NoYield")
                baseline_val = values[idx] if values[idx] else None

            bars = ax.bar(strategies, values, color=[colors[s] for s in strategies])
            ax.set_title(label)
            ax.set_ylabel("Latency (µs)")
            ax.set_xlabel("Strategy")
            for bar, v in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                        _pct_diff_label(v, baseline_val),
                        ha="center", va="bottom", fontsize=7)

            # Tight y-axis: don't start from 0
            if values and min(values) > 0:
                lo = min(values) * 0.85
                hi = max(values) * 1.15
                ax.set_ylim(lo, hi)

        plt.tight_layout()
        out_path = out_dir / f"latency_workload_{workload}.pdf"
        plt.savefig(out_path)
        print(f"Saved: {out_path}")
        plt.close()


# ---------------------------------------------------------------------------
# Combined workload bar chart (all workloads in one figure)
# ---------------------------------------------------------------------------
def plot_combined_workloads(results: list[dict], out_dir: pathlib.Path) -> None:
    workloads  = sorted({r["workload"]  for r in results})
    strategies = sorted({r["strategy"] for r in results})
    if len(workloads) < 2:
        return

    colors  = _strategy_colors(strategies)
    hatches = ["///", "...", "xxx", "---", "|||"]
    x       = np.arange(len(workloads))
    width   = 0.8 / len(strategies)

    fig, axes = plt.subplots(1, len(PERCENTILES), figsize=(18, 5), sharey=False)
    fig.suptitle("Latency across all workloads", fontsize=14)

    for ax, pct, label in zip(axes, PERCENTILES, PERCENTILE_LABELS):
        all_values = []
        for i, strategy in enumerate(strategies):
            values = []
            for workload in workloads:
                matching = [r[pct] for r in results
                            if r["strategy"] == strategy and r["workload"] == workload]
                values.append(np.mean(matching) if matching else 0)
            all_values.extend(values)

            offset = (i - len(strategies) / 2 + 0.5) * width
            bars = ax.bar(x + offset, values, width,
                          label=strategy,
                          color=colors[strategy],
                          hatch=hatches[i % len(hatches)],
                          edgecolor="white")
            for bar, v in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                        f"{v:.1f}", ha="center", va="bottom", fontsize=6, rotation=45)

        ax.set_title(label)
        ax.set_xticks(x)
        ax.set_xticklabels([f"Workload {w}" for w in workloads])
        ax.set_ylabel("Latency (µs)")
        ax.legend(fontsize=7)

    plt.tight_layout()
    out_path = out_dir / "latency_combined.pdf"
    plt.savefig(out_path)
    print(f"Saved: {out_path}")
    plt.close()


# ---------------------------------------------------------------------------
# Throughput bar chart
# ---------------------------------------------------------------------------
def plot_throughput(results: list[dict], out_dir: pathlib.Path) -> None:
    strategies = sorted({r["strategy"] for r in results})
    workloads  = sorted({r["workload"]  for r in results})

    fig, ax = plt.subplots(figsize=(10, 5))
    x     = np.arange(len(strategies))
    width = 0.8 / len(workloads)
    wcolors = cm.tab10(np.linspace(0, 1, max(len(workloads), 3)))

    for i, workload in enumerate(workloads):
        values = []
        for strategy in strategies:
            matching = [r["throughput_ops"] for r in results
                        if r["strategy"] == strategy and r["workload"] == workload]
            values.append(np.mean(matching) if matching else 0)
        offset = (i - len(workloads) / 2 + 0.5) * width
        bars = ax.bar(x + offset, values, width, label=f"Workload {workload}", color=wcolors[i])
        for bar, v in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    f"{v/1000:.1f}k", ha="center", va="bottom", fontsize=7)

    ax.set_xticks(x)
    ax.set_xticklabels(strategies)
    ax.set_ylabel("Throughput (ops/sec)")
    ax.set_title("Throughput by Strategy and Workload")
    ax.legend()
    plt.tight_layout()
    out_path = out_dir / "throughput.pdf"
    plt.savefig(out_path)
    print(f"Saved: {out_path}")
    plt.close()


# ---------------------------------------------------------------------------
# Thread-count sweep line chart
# ---------------------------------------------------------------------------
def plot_thread_sweep(results: list[dict], out_dir: pathlib.Path) -> None:
    thread_counts = sorted({r["threads"] for r in results})
    if len(thread_counts) < 2:
        return

    strategies = sorted({r["strategy"] for r in results})
    workloads  = sorted({r["workload"]  for r in results})
    colors     = _strategy_colors(strategies)
    markers    = ["o", "s", "^", "D", "v"]

    for workload in workloads:
        fig, axes = plt.subplots(1, len(PERCENTILES), figsize=(18, 5), sharey=False)
        fig.suptitle(f"Latency vs Thread Count — Workload {workload}", fontsize=14)

        for ax, pct, label in zip(axes, PERCENTILES, PERCENTILE_LABELS):
            for i, strategy in enumerate(strategies):
                ys = []
                for t in thread_counts:
                    matching = [r[pct] for r in results
                                if r["strategy"] == strategy
                                and r["workload"] == workload
                                and r["threads"] == t]
                    ys.append(np.mean(matching) if matching else float("nan"))
                ax.plot(thread_counts, ys, label=strategy,
                        color=colors[strategy],
                        marker=markers[i % len(markers)],
                        linewidth=1.5)
            ax.set_title(label)
            ax.set_xlabel("Foreground threads")
            ax.set_ylabel("Latency (µs)")
            ax.set_xticks(thread_counts)
            ax.legend(fontsize=7)

        plt.tight_layout()
        out_path = out_dir / f"thread_sweep_workload_{workload}.pdf"
        plt.savefig(out_path)
        print(f"Saved: {out_path}")
        plt.close()


# ---------------------------------------------------------------------------
# Yield-interval sweep: p99, p99.9, and throughput (not max — too noisy)
# ---------------------------------------------------------------------------
def plot_interval_sweep(results: list[dict], out_dir: pathlib.Path) -> None:
    yield_strategies = [s for s in sorted({r["strategy"] for r in results})
                        if s != "NoYield"]
    intervals = sorted({r["yield_interval"] for r in results
                        if r["strategy"] != "NoYield"})
    if len(intervals) < 2 or not yield_strategies:
        return

    workloads  = sorted({r["workload"] for r in results})
    scolors    = _strategy_colors(yield_strategies)
    markers    = ["o", "s", "^", "D", "v"]
    linestyles = ["-", "--", "-.", ":"]

    SWEEP_METRICS = [
        ("p99_us",         "p99 latency (µs)"),
        ("p999_us",        "p99.9 latency (µs)"),
        ("throughput_ops", "Throughput (ops/sec)"),
    ]

    for workload in workloads:
        fig, axes = plt.subplots(1, len(SWEEP_METRICS), figsize=(18, 5))
        fig.suptitle(f"Latency & Throughput vs Yield Interval — Workload {workload}",
                     fontsize=14)

        for ax, (field, ylabel) in zip(axes, SWEEP_METRICS):
            for i, strategy in enumerate(yield_strategies):
                strat_results = [r for r in results
                                 if r["strategy"] == strategy and r["workload"] == workload]
                if not strat_results:
                    continue
                xs = sorted({r["yield_interval"] for r in strat_results})
                ys = []
                for iv in xs:
                    matching = [r[field] for r in strat_results if r["yield_interval"] == iv]
                    ys.append(np.mean(matching) if matching else float("nan"))
                ax.plot(xs, ys, label=strategy,
                        color=scolors[strategy],
                        marker=markers[i % len(markers)],
                        linestyle=linestyles[i % len(linestyles)],
                        linewidth=1.5)

            # NoYield baseline as a dashed horizontal line
            baseline = [r[field] for r in results
                        if r["strategy"] == "NoYield" and r["workload"] == workload]
            if baseline:
                ax.axhline(np.mean(baseline), color="gray", linestyle="--",
                           linewidth=1.5, alpha=0.7, label="NoYield (baseline)")

            ax.set_xlabel("Yield interval (entries)")
            ax.set_ylabel(ylabel)
            ax.set_title(ylabel)
            ax.set_xscale("log")
            ax.legend(fontsize=7)

        plt.tight_layout()
        out_path = out_dir / f"interval_sweep_workload_{workload}.pdf"
        plt.savefig(out_path)
        print(f"Saved: {out_path}")
        plt.close()


# ---------------------------------------------------------------------------
# Time-series: scatter points + rolling average trendline, log-scale latency
# ---------------------------------------------------------------------------
ROLLING_WINDOW = 10  # seconds (at 1s snapshot resolution)

def plot_time_series(results: list[dict], out_dir: pathlib.Path) -> None:
    ts_results = [r for r in results if r.get("time_series")]
    if not ts_results:
        return

    strategies = sorted({r["strategy"] for r in ts_results})
    workloads  = sorted({r["workload"]  for r in ts_results})
    colors     = _strategy_colors(strategies)

    TS_METRICS = [
        ("p99_us",         "p99 latency (µs)",      True),   # (field, label, log_scale)
        ("p999_us",        "p99.9 latency (µs)",     True),
        ("throughput_ops", "Throughput (ops/sec)",    False),
    ]

    for workload in workloads:
        fig, axes = plt.subplots(len(TS_METRICS), 1, figsize=(14, 4 * len(TS_METRICS)),
                                 sharex=True)
        fig.suptitle(f"Time Series — Workload {workload}", fontsize=14, y=1.01)

        for ax, (field, ylabel, use_log) in zip(axes, TS_METRICS):
            for strategy in strategies:
                matching = [r for r in ts_results
                            if r["strategy"] == strategy and r["workload"] == workload]
                if not matching:
                    continue
                ts = matching[0]["time_series"]
                if not ts:
                    continue
                xs = np.array([pt["elapsed_secs"] for pt in ts])
                ys = np.array([pt[field] for pt in ts])
                color = colors[strategy]

                # Translucent scatter for raw data points
                ax.scatter(xs, ys, color=color, alpha=0.12, s=6, linewidths=0)

                # Bold rolling-average trendline
                trend = _rolling_mean(ys, ROLLING_WINDOW)
                ax.plot(xs, trend, color=color, linewidth=2, label=strategy)

            ax.set_ylabel(ylabel)
            if use_log:
                ax.set_yscale("log")
            ax.legend(fontsize=8, loc="upper right")
            ax.grid(True, alpha=0.3)

        axes[-1].set_xlabel("Elapsed (s)")
        plt.tight_layout()
        out_path = out_dir / f"time_series_workload_{workload}.pdf"
        plt.savefig(out_path)
        print(f"Saved: {out_path}")
        plt.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot benchmark results from one or more JSON files."
    )
    parser.add_argument(
        "inputs", nargs="+", metavar="results.json",
        help="One or more benchmark result JSON files (merged automatically)",
    )
    parser.add_argument(
        "--out", default="analysis/output", metavar="dir",
        help="Output directory for plots (default: analysis/output)",
    )
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for path in args.inputs:
        batch = load_results(path)
        results.extend(batch)
        print(f"Loaded {len(batch)} run(s) from {path}")

    plot_latency_comparison(results, out_dir)
    plot_throughput(results, out_dir)
    plot_combined_workloads(results, out_dir)
    plot_thread_sweep(results, out_dir)
    plot_interval_sweep(results, out_dir)
    plot_time_series(results, out_dir)


if __name__ == "__main__":
    main()