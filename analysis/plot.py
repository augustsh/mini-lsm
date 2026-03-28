# Copyright 2026 preemptive-lsm authors
# Licensed under the Apache License, Version 2.0
# This file is part of the preemptive-lsm project.
# It is original work and not derived from mini-lsm.
#
# Usage:
#   python analysis/plot.py results.json
#
# Expected JSON format (list of run objects):
# [
#   {
#     "strategy": "NoYield",
#     "workload": "A",
#     "threads": 4,
#     "p50_us": 120,
#     "p95_us": 450,
#     "p99_us": 1200,
#     "p999_us": 8000,
#     "throughput_ops": 45000
#   },
#   ...
# ]

import sys
import json
import pathlib

try:
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm
    import numpy as np
except ImportError:
    sys.exit("Install matplotlib and numpy: pip install matplotlib numpy")


PERCENTILES = ["p50_us", "p95_us", "p99_us", "p999_us"]
PERCENTILE_LABELS = ["p50", "p95", "p99", "p99.9"]


def load_results(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def plot_latency_comparison(results: list[dict], out_dir: pathlib.Path) -> None:
    strategies = sorted({r["strategy"] for r in results})
    workloads = sorted({r["workload"] for r in results})

    for workload in workloads:
        fig, axes = plt.subplots(1, len(PERCENTILES), figsize=(16, 5), sharey=False)
        fig.suptitle(f"Latency — Workload {workload}", fontsize=14)

        for ax, pct, label in zip(axes, PERCENTILES, PERCENTILE_LABELS):
            values = []
            for strategy in strategies:
                matching = [
                    r[pct]
                    for r in results
                    if r["strategy"] == strategy and r["workload"] == workload
                ]
                values.append(np.mean(matching) if matching else 0)

            colors = cm.tab10(np.linspace(0, 1, len(strategies)))
            bars = ax.bar(strategies, values, color=colors)
            ax.set_title(label)
            ax.set_ylabel("Latency (µs)")
            ax.set_xlabel("Strategy")
            for bar, v in zip(bars, values):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height(),
                    f"{v:.0f}",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )

        plt.tight_layout()
        out_path = out_dir / f"latency_workload_{workload}.png"
        plt.savefig(out_path, dpi=150)
        print(f"Saved: {out_path}")
        plt.close()


def plot_throughput(results: list[dict], out_dir: pathlib.Path) -> None:
    strategies = sorted({r["strategy"] for r in results})
    workloads = sorted({r["workload"] for r in results})

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(strategies))
    width = 0.8 / len(workloads)
    colors = cm.tab10(np.linspace(0, 1, len(workloads)))

    for i, workload in enumerate(workloads):
        values = []
        for strategy in strategies:
            matching = [
                r["throughput_ops"]
                for r in results
                if r["strategy"] == strategy and r["workload"] == workload
            ]
            values.append(np.mean(matching) if matching else 0)
        offset = (i - len(workloads) / 2 + 0.5) * width
        bars = ax.bar(x + offset, values, width, label=f"Workload {workload}", color=colors[i])
        for bar, v in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{v/1000:.1f}k",
                ha="center",
                va="bottom",
                fontsize=7,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(strategies)
    ax.set_ylabel("Throughput (ops/sec)")
    ax.set_title("Throughput by Strategy and Workload")
    ax.legend()
    plt.tight_layout()
    out_path = out_dir / "throughput.png"
    plt.savefig(out_path, dpi=150)
    print(f"Saved: {out_path}")
    plt.close()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(f"Usage: python {sys.argv[0]} <results.json> [output_dir]")

    results_path = sys.argv[1]
    out_dir = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "analysis/output")
    out_dir.mkdir(parents=True, exist_ok=True)

    results = load_results(results_path)
    print(f"Loaded {len(results)} run(s) from {results_path}")

    plot_latency_comparison(results, out_dir)
    plot_throughput(results, out_dir)


if __name__ == "__main__":
    main()