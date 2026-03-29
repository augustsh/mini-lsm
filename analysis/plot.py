# Copyright 2026 preemptive-lsm authors
# Licensed under the Apache License, Version 2.0
# This file is part of the preemptive-lsm project.
# It is original work and not derived from mini-lsm.
#
# Usage:
#   python analysis/plot.py results/docker/experiments_t1.json results/docker/experiments_t2.json results/docker/experiments_t4.json --out results/plots

import argparse
import json
import pathlib
import sys

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm
    import numpy as np
except ImportError:
    sys.exit("Install matplotlib and numpy: pip install matplotlib numpy")


# ── constants ──────────────────────────────────────────────────────────────────

TAIL_METRICS = [
    ("p99_us",   "p99 latency (us)"),
    ("p999_us",  "p99.9 latency (us)"),
]
THROUGHPUT_METRIC = ("throughput_ops", "Throughput (ops/s)")

STRATEGY_STYLE = {
    "NoYield":            {"color": "#2c3e50", "marker": "o"},
    "UnconditionalYield": {"color": "#e74c3c", "marker": "s"},
    "ConditionalYield":   {"color": "#2980b9", "marker": "^"},
}
ROLLING_WINDOW = 10


# ── helpers ────────────────────────────────────────────────────────────────────

def load_results(paths: list[str]) -> list[dict]:
    results = []
    for p in paths:
        with open(p) as f:
            batch = json.load(f)
        results.extend(batch)
        print(f"Loaded {len(batch)} record(s) from {p}")
    return results


def _style(strategy):
    return STRATEGY_STYLE.get(strategy, {"color": "gray", "marker": "x"})


def _unique_sorted(results, key):
    return sorted({r[key] for r in results})


def _filter(results, **kwargs):
    out = results
    for k, v in kwargs.items():
        out = [r for r in out if r.get(k) == v]
    return out


def _mean_field(records, field):
    vals = [r[field] for r in records if field in r]
    return np.mean(vals) if vals else float("nan")


def _best_interval(results, strategy, workload, threads, metric="p999_us", minimize=True):
    """Find the yield interval that gives the best (lowest/highest) metric value."""
    candidates = _filter(results, strategy=strategy, workload=workload, threads=threads)
    if not candidates:
        return None, float("nan")
    intervals = _unique_sorted(candidates, "yield_interval")
    best_iv, best_val = None, float("inf") if minimize else float("-inf")
    for iv in intervals:
        val = _mean_field(_filter(candidates, yield_interval=iv), metric)
        if minimize and val < best_val:
            best_iv, best_val = iv, val
        elif not minimize and val > best_val:
            best_iv, best_val = iv, val
    return best_iv, best_val


def _rolling_mean(ys, window=ROLLING_WINDOW):
    arr = np.array(ys, dtype=float)
    out = np.full(len(arr), np.nan)
    cumsum = np.nancumsum(arr)
    for i in range(len(arr)):
        lo = max(0, i - window + 1)
        n = i - lo + 1
        out[i] = (cumsum[i] - (cumsum[lo - 1] if lo > 0 else 0)) / n
    return out


# ── plot 1: interval sweep grid ───────────────────────────────────────────────
# Per workload: rows = thread counts, cols = (p99, p99.9, throughput)
# Lines for each yield strategy; NoYield as horizontal baseline.

def plot_interval_sweep_grid(results, out_dir):
    workloads = _unique_sorted(results, "workload")
    thread_counts = _unique_sorted(results, "threads")
    yield_strats = [s for s in _unique_sorted(results, "strategy") if s != "NoYield"]
    metrics = TAIL_METRICS + [THROUGHPUT_METRIC]
    markers_cycle = ["o", "s", "^", "D", "v"]
    linestyles = ["-", "--", "-.", ":"]

    for wl in workloads:
        nrows, ncols = len(thread_counts), len(metrics)
        fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 4 * nrows),
                                  squeeze=False)
        fig.suptitle(f"Yield Interval Sweep — Workload {wl}", fontsize=15, y=1.01)

        for ri, tc in enumerate(thread_counts):
            for ci, (field, ylabel) in enumerate(metrics):
                ax = axes[ri][ci]

                for si, strat in enumerate(yield_strats):
                    recs = _filter(results, strategy=strat, workload=wl, threads=tc)
                    if not recs:
                        continue
                    ivs = sorted({r["yield_interval"] for r in recs})
                    ys = [_mean_field(_filter(recs, yield_interval=iv), field) for iv in ivs]
                    style = _style(strat)
                    ax.plot(ivs, ys, label=strat,
                            color=style["color"], marker=style["marker"],
                            linestyle=linestyles[si % len(linestyles)],
                            linewidth=1.5, markersize=5)

                # NoYield baseline
                baseline_recs = _filter(results, strategy="NoYield", workload=wl, threads=tc)
                if baseline_recs:
                    bv = _mean_field(baseline_recs, field)
                    ax.axhline(bv, color=_style("NoYield")["color"],
                               linestyle="--", linewidth=1.5, alpha=0.6,
                               label="NoYield")

                ax.set_xscale("log")
                ax.set_ylabel(ylabel)
                if ri == nrows - 1:
                    ax.set_xlabel("Yield interval (entries)")
                if ri == 0:
                    ax.set_title(ylabel)
                if ci == 0:
                    # Place row label in figure coords to the left of the subplot row
                    bbox = ax.get_position()
                    fig.text(0.01, (bbox.y0 + bbox.y1) / 2, f"t={tc}",
                             ha="center", va="center", fontsize=13,
                             fontweight="bold", rotation=90)
                if ri == 0 and ci == ncols - 1:
                    ax.legend(fontsize=7, loc="best")
                ax.grid(True, alpha=0.3)

        plt.tight_layout(rect=[0.03, 0, 1, 0.97])
        path = out_dir / f"interval_sweep_workload_{wl}.pdf"
        plt.savefig(path, bbox_inches="tight")
        print(f"Saved: {path}")
        plt.close()


# ── plot 2: thread scaling ────────────────────────────────────────────────────
# Per workload: x = thread count, y = metric.
# Lines: NoYield, best ConditionalYield, best UnconditionalYield.
# "Best" = interval that minimizes p99.9 (or maximizes throughput).

def plot_thread_scaling(results, out_dir):
    workloads = _unique_sorted(results, "workload")
    thread_counts = _unique_sorted(results, "threads")
    strategies = _unique_sorted(results, "strategy")
    metrics = TAIL_METRICS + [THROUGHPUT_METRIC]

    for wl in workloads:
        fig, axes = plt.subplots(1, len(metrics), figsize=(5 * len(metrics), 4.5),
                                  squeeze=False)
        fig.suptitle(f"Thread Scaling — Workload {wl}", fontsize=14)

        for ci, (field, ylabel) in enumerate(metrics):
            ax = axes[0][ci]
            minimize = field != "throughput_ops"

            for strat in strategies:
                style = _style(strat)
                ys = []
                labels = []
                for tc in thread_counts:
                    if strat == "NoYield":
                        recs = _filter(results, strategy=strat, workload=wl, threads=tc)
                        ys.append(_mean_field(recs, field))
                        labels.append("")
                    else:
                        best_iv, best_val = _best_interval(
                            results, strat, wl, tc, field, minimize)
                        ys.append(best_val)
                        labels.append(f"iv={best_iv}")

                lbl = strat if strat == "NoYield" else f"{strat} (best iv)"
                ax.plot(thread_counts, ys, label=lbl,
                        color=style["color"], marker=style["marker"],
                        linewidth=2, markersize=7)

                # Annotate best interval on each point
                if strat != "NoYield":
                    for xi, (tc, y, lab) in enumerate(zip(thread_counts, ys, labels)):
                        if lab:
                            ax.annotate(lab, (tc, y), textcoords="offset points",
                                        xytext=(5, 5), fontsize=6, color=style["color"])

            ax.set_xlabel("Foreground threads")
            ax.set_ylabel(ylabel)
            ax.set_title(ylabel)
            ax.set_xticks(thread_counts)
            ax.legend(fontsize=7)
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        path = out_dir / f"thread_scaling_workload_{wl}.pdf"
        plt.savefig(path, bbox_inches="tight")
        print(f"Saved: {path}")
        plt.close()


# ── plot 3: summary bar chart ─────────────────────────────────────────────────
# One figure: grouped bars showing % improvement in p99.9 over NoYield
# for the best interval of each yield strategy, across workloads and thread counts.

def plot_summary_improvement(results, out_dir):
    workloads = _unique_sorted(results, "workload")
    thread_counts = _unique_sorted(results, "threads")
    yield_strats = [s for s in _unique_sorted(results, "strategy") if s != "NoYield"]

    # Build groups: each group is (workload, threads)
    groups = [(wl, tc) for wl in workloads for tc in thread_counts]
    group_labels = [f"{wl}/t={tc}" for wl, tc in groups]

    x = np.arange(len(groups))
    width = 0.8 / max(len(yield_strats), 1)

    fig, ax = plt.subplots(figsize=(max(12, len(groups) * 1.2), 5))

    for si, strat in enumerate(yield_strats):
        style = _style(strat)
        improvements = []
        for wl, tc in groups:
            baseline = _mean_field(
                _filter(results, strategy="NoYield", workload=wl, threads=tc), "p999_us")
            _, best_val = _best_interval(results, strat, wl, tc, "p999_us", minimize=True)
            if baseline and baseline > 0 and not np.isnan(best_val):
                pct = (best_val - baseline) / baseline * 100
            else:
                pct = 0
            improvements.append(pct)

        offset = (si - len(yield_strats) / 2 + 0.5) * width
        bars = ax.bar(x + offset, improvements, width, label=strat,
                      color=style["color"], alpha=0.85)
        for bar, pct in zip(bars, improvements):
            va = "bottom" if pct >= 0 else "top"
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    f"{pct:+.1f}%", ha="center", va=va, fontsize=6)

    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(group_labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("p99.9 change vs NoYield (%)")
    ax.set_title("Best-Interval p99.9 Improvement over NoYield")
    ax.legend(fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)

    plt.tight_layout()
    path = out_dir / "summary_p999_improvement.pdf"
    plt.savefig(path, bbox_inches="tight")
    print(f"Saved: {path}")
    plt.close()


# ── plot 4: throughput cost summary ───────────────────────────────────────────
# Same layout as summary_improvement but for throughput (positive = better).

def plot_throughput_cost(results, out_dir):
    workloads = _unique_sorted(results, "workload")
    thread_counts = _unique_sorted(results, "threads")
    yield_strats = [s for s in _unique_sorted(results, "strategy") if s != "NoYield"]

    groups = [(wl, tc) for wl in workloads for tc in thread_counts]
    group_labels = [f"{wl}/t={tc}" for wl, tc in groups]

    x = np.arange(len(groups))
    width = 0.8 / max(len(yield_strats), 1)

    fig, ax = plt.subplots(figsize=(max(12, len(groups) * 1.2), 5))

    for si, strat in enumerate(yield_strats):
        style = _style(strat)
        changes = []
        for wl, tc in groups:
            baseline = _mean_field(
                _filter(results, strategy="NoYield", workload=wl, threads=tc),
                "throughput_ops")
            # Use the same interval that was best for p99.9
            best_iv, _ = _best_interval(results, strat, wl, tc, "p999_us", minimize=True)
            if best_iv is not None:
                recs = _filter(results, strategy=strat, workload=wl,
                               threads=tc, yield_interval=best_iv)
                val = _mean_field(recs, "throughput_ops")
            else:
                val = float("nan")
            if baseline and baseline > 0 and not np.isnan(val):
                pct = (val - baseline) / baseline * 100
            else:
                pct = 0
            changes.append(pct)

        offset = (si - len(yield_strats) / 2 + 0.5) * width
        bars = ax.bar(x + offset, changes, width, label=strat,
                      color=style["color"], alpha=0.85)
        for bar, pct in zip(bars, changes):
            va = "bottom" if pct >= 0 else "top"
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    f"{pct:+.1f}%", ha="center", va=va, fontsize=6)

    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(group_labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Throughput change vs NoYield (%)")
    ax.set_title("Throughput Cost at Best p99.9 Interval")
    ax.legend(fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)

    plt.tight_layout()
    path = out_dir / "summary_throughput_cost.pdf"
    plt.savefig(path, bbox_inches="tight")
    print(f"Saved: {path}")
    plt.close()


# ── plot 5: time series ───────────────────────────────────────────────────────
# Per (workload, thread_count): p99.9 and throughput over time.
# Shows NoYield + ConditionalYield at the median interval.

def plot_time_series(results, out_dir):
    ts_results = [r for r in results if r.get("time_series")]
    if not ts_results:
        return

    workloads = _unique_sorted(ts_results, "workload")
    thread_counts = _unique_sorted(ts_results, "threads")
    yield_strats = [s for s in _unique_sorted(ts_results, "strategy") if s != "NoYield"]

    # Pick the median interval for yield strategies
    all_intervals = _unique_sorted(ts_results, "yield_interval")
    mid_interval = all_intervals[len(all_intervals) // 2] if all_intervals else 1000

    TS_METRICS = [
        ("p999_us",        "p99.9 latency (us)", True),
        ("throughput_ops", "Throughput (ops/s)",  False),
    ]

    for wl in workloads:
        for tc in thread_counts:
            fig, axes = plt.subplots(len(TS_METRICS), 1,
                                      figsize=(12, 3.5 * len(TS_METRICS)),
                                      sharex=True)
            fig.suptitle(f"Time Series — Workload {wl}, t={tc}", fontsize=14, y=1.01)

            # Strategies to plot: NoYield + each yield strat at median interval
            to_plot = []
            no_yield = _filter(ts_results, strategy="NoYield", workload=wl, threads=tc)
            if no_yield:
                to_plot.append(("NoYield", no_yield[0]))
            for strat in yield_strats:
                recs = _filter(ts_results, strategy=strat, workload=wl,
                               threads=tc, yield_interval=mid_interval)
                if recs:
                    to_plot.append((f"{strat} iv={mid_interval}", recs[0]))

            for ax, (field, ylabel, use_log) in zip(axes, TS_METRICS):
                for label, rec in to_plot:
                    ts = rec.get("time_series", [])
                    if not ts:
                        continue
                    # Determine base strategy name for coloring
                    base_strat = rec["strategy"]
                    style = _style(base_strat)
                    xs = np.array([pt["elapsed_secs"] for pt in ts])
                    ys = np.array([pt[field] for pt in ts])

                    ax.scatter(xs, ys, color=style["color"], alpha=0.10, s=5,
                               linewidths=0)
                    trend = _rolling_mean(ys)
                    ax.plot(xs, trend, color=style["color"], linewidth=2, label=label)

                ax.set_ylabel(ylabel)
                if use_log:
                    ax.set_yscale("log")
                ax.legend(fontsize=7, loc="upper right")
                ax.grid(True, alpha=0.3)

            axes[-1].set_xlabel("Elapsed (s)")
            plt.tight_layout()
            path = out_dir / f"time_series_{wl}_t{tc}.pdf"
            plt.savefig(path, bbox_inches="tight")
            print(f"Saved: {path}")
            plt.close()


# ── entry point ────────────────────────────────────────────────────────────────

def main():
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

    results = load_results(args.inputs)
    print(f"Total: {len(results)} records")
    print(f"  Strategies: {_unique_sorted(results, 'strategy')}")
    print(f"  Workloads:  {_unique_sorted(results, 'workload')}")
    print(f"  Threads:    {_unique_sorted(results, 'threads')}")
    print()

    plot_interval_sweep_grid(results, out_dir)
    plot_thread_scaling(results, out_dir)
    plot_summary_improvement(results, out_dir)
    plot_throughput_cost(results, out_dir)
    plot_time_series(results, out_dir)


if __name__ == "__main__":
    main()
