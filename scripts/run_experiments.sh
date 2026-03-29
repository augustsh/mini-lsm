

#!/usr/bin/env bash
# Copyright 2026 preemptive-lsm authors
# Licensed under the Apache License, Version 2.0
#
# Runs all experiments across a thread-count matrix (1, 2, 4 foreground threads)
# inside CPU-pinned Docker containers launched in parallel.
#
# CPU pinning (non-overlapping even cores):
#   1 thread  -> --cpuset-cpus=0
#   2 threads -> --cpuset-cpus=2,4
#   4 threads -> --cpuset-cpus=6,8,10,12
#
# Output files: results/docker/experiments_t{1,2,4}.json
# Usage:
#   ./scripts/run_experiments.sh

set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="mini-lsm-bench"
RESULTS_DIR="$(pwd)/results/docker"
INTERVALS=(100 500 1000 5000 10000)

mkdir -p "$RESULTS_DIR"

echo "=== Building Docker image ==="
docker build -t "$IMAGE" .

# Runs all experiments for a given thread count and CPU pin.
# Each invocation is meant to run in a background subshell.
run_one_thread_config() {
    local threads="$1"
    local cpuset="$2"
    local json_out="/results/experiments_t${threads}.json"
    # 5M keys @ 1 KB, 1 min per run, 5 runs averaged, 1 s snapshots
    # Memtable size (64 MB) is set via target_sst_size in bench/src/main.rs
    local common="--threads $threads --key-space 5000000 --value-size 1024 --duration-secs 60 --runs 5 --snapshot-secs 1"

    _bench() {
        local label="$1"; shift
        echo ""
        echo "=== [t=$threads] $label ==="
        docker run --rm --cpuset-cpus="$cpuset" \
            -v "$RESULTS_DIR:/results" \
            "$IMAGE" \
            $common "$@" --json-out "$json_out"
    }

    _experiment() {
        local exp_name="$1"
        local workload="$2"
        local distribution="$3"

        # Baseline: NoYield
        _bench "Exp-$exp_name  NoYield" \
            --strategy no-yield --workload "$workload" --distribution "$distribution"

        # UnconditionalYield sweep across all intervals
        for interval in "${INTERVALS[@]}"; do
            _bench "Exp-$exp_name  UnconditionalYield interval=$interval" \
                --strategy unconditional-yield --yield-interval "$interval" \
                --workload "$workload" --distribution "$distribution"
        done

        # ConditionalYield sweep across all intervals
        for interval in "${INTERVALS[@]}"; do
            _bench "Exp-$exp_name  ConditionalYield interval=$interval" \
                --strategy conditional-yield --yield-interval "$interval" \
                --workload "$workload" --distribution "$distribution"
        done
    }

    # ─── Experiment A: mixed (50/50 read/write, Zipfian) ──────────────
    _experiment A a zipfian

    # ─── Experiment B: read-heavy (95/5 read/write, Zipfian) ─────────────────
    _experiment B b zipfian

    # ─── Experiment C: write-heavy (5/95 read/write, uniform) ─────────────
    _experiment C c uniform

    # ─── Experiment D: stress (100% reads during compaction) ─────────────
    _experiment D d uniform

    echo ""
    echo "=== [t=$threads] All experiments complete ==="
}

# Launch all three thread configs in parallel with non-overlapping CPU pins.
echo "=== Launching parallel containers ==="
echo "    t=1  -> cpuset 0"
echo "    t=2  -> cpuset 2,4"
echo "    t=4  -> cpuset 6,8,10,12"
echo ""

run_one_thread_config 1 "0"           & PID1=$!
run_one_thread_config 2 "2,4"         & PID2=$!
run_one_thread_config 4 "6,8,10,12"   & PID4=$!

wait $PID1; STATUS1=$?
wait $PID2; STATUS2=$?
wait $PID4; STATUS4=$?

echo ""
echo "=== All experiments complete ==="
echo "    t=1  exit=$STATUS1  -> $RESULTS_DIR/experiments_t1.json"
echo "    t=2  exit=$STATUS2  -> $RESULTS_DIR/experiments_t2.json"
echo "    t=4  exit=$STATUS4  -> $RESULTS_DIR/experiments_t4.json"
echo ""
echo "Generate plots:"
echo "  python3 analysis/plot.py $RESULTS_DIR/experiments_t1.json $RESULTS_DIR/experiments_t2.json $RESULTS_DIR/experiments_t4.json --out $RESULTS_DIR/plots"