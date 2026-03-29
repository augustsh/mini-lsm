

#!/usr/bin/env bash
# Copyright 2026 preemptive-lsm authors
# Licensed under the Apache License, Version 2.0
#
# Runs all three experiments inside a CPU-constrained Docker container.
# Usage:
#   ./scripts/run_experiments.sh          # default: --cpus=2
#   CPUS=1 ./scripts/run_experiments.sh   # override CPU limit

set -euo pipefail
cd "$(dirname "$0")/.."

CPUS="${CPUS:-2}"
IMAGE="mini-lsm-bench"
RESULTS_DIR="$(pwd)/results/docker"

mkdir -p "$RESULTS_DIR"

echo "=== Building Docker image ==="
docker build -t "$IMAGE" .

# Common parameters: 1 fg thread, 1M keys @ 1KB, 1 min per run, 5 runs averaged, 1s snapshots
COMMON="--threads 1 --key-space 1000000 --value-size 1024 --duration-secs 60 --runs 5 --snapshot-secs 1"
INTERVALS=(100 500 1000 5000 10000)

run_bench() {
    local label="$1"; shift
    echo ""
    echo "=== $label ==="
    docker run --rm --cpus="$CPUS" \
        -v "$RESULTS_DIR:/results" \
        "$IMAGE" \
        $COMMON "$@" --json-out "/results/experiments.json"
}

run_experiment() {
    local exp_name="$1"
    local workload="$2"
    local distribution="$3"

    # Baseline: NoYield
    run_bench "Exp-$exp_name  NoYield" \
        --strategy no-yield --workload "$workload" --distribution "$distribution"

    # ConditionalYield sweep across all intervals
    for interval in "${INTERVALS[@]}"; do
        run_bench "Exp-$exp_name  ConditionalYield interval=$interval" \
            --strategy conditional-yield --yield-interval "$interval" \
            --workload "$workload" --distribution "$distribution"
    done
}

# ─── Experiment A: stress (100% reads during compaction) ──────────────
run_experiment A d uniform

# ─── Experiment B: mixed (50/50 read/write, Zipfian) ─────────────────
run_experiment B a zipfian

# ─── Experiment C: read-heavy (95/5 read/write, Zipfian) ─────────────
run_experiment C b zipfian

echo ""
echo "=== All experiments complete ==="
echo "Results: $RESULTS_DIR/experiments.json"
echo ""
echo "Generate plots:"
echo "  python3 analysis/plot.py $RESULTS_DIR/experiments.json --out $RESULTS_DIR/plots"