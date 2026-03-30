

#!/usr/bin/env bash
# Copyright 2026 preemptive-lsm authors
# Licensed under the Apache License, Version 2.0
#
# Runs all experiments across a full matrix of:
#   - Foreground threads: 1, 2, 4
#   - Allocated CPU cores: 1, 2, 4
#
# The 3 core allocations run in parallel (non-overlapping pinned cores).
# Within each core allocation, thread counts are run sequentially.
#
# CPU pinning (non-overlapping even cores for parallel execution):
#   1 core  -> --cpuset-cpus=0
#   2 cores -> --cpuset-cpus=2,4
#   4 cores -> --cpuset-cpus=6,8,10,12
#
# Output files: results/docker/experiments_c{1,2,4}.json
#   Each file contains results for all 3 thread counts (1, 2, 4).
#
# Usage:
#   ./scripts/run_experiments.sh

set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="mini-lsm-bench"
RESULTS_DIR="$(pwd)/results/docker"
INTERVALS=(100 500 1000 5000 10000)
THREAD_COUNTS=(1 2 4)

mkdir -p "$RESULTS_DIR"

echo "=== Building Docker image ==="
docker build -t "$IMAGE" .

# Runs all experiments for a given core allocation.
# Iterates over all thread counts (1, 2, 4) sequentially.
# Each invocation is meant to run in a background subshell.
run_one_core_config() {
    local cores="$1"
    local cpuset="$2"
    local json_out="/results/experiments_c${cores}.json"

    for threads in "${THREAD_COUNTS[@]}"; do
        # 5M keys @ 1 KB, 1 min per run, 5 runs averaged, 1 s snapshots
        # Memtable size (64 MB) is set via target_sst_size in bench/src/main.rs
        local common="--threads $threads --cores $cores --key-space 5000000 --value-size 1024 --duration-secs 60 --runs 3 --snapshot-secs 1"

        _bench() {
            local label="$1"; shift
            echo ""
            echo "=== [c=$cores, t=$threads] $label ==="
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

            # ConditionalYield sweep across all intervals
            for interval in "${INTERVALS[@]}"; do
                _bench "Exp-$exp_name  ConditionalYield interval=$interval" \
                    --strategy conditional-yield --yield-interval "$interval" \
                    --workload "$workload" --distribution "$distribution"
            done
        }

        echo ""
        echo "=== [c=$cores] Starting thread count t=$threads ==="

        # ─── Experiment A: mixed (50/50 read/write, Zipfian) ──────────────
        _experiment A a zipfian

        # ─── Experiment B: read-heavy (95/5 read/write, Zipfian) ─────────────────
        _experiment B b zipfian

        # ─── Experiment C: write-heavy (5/95 read/write, uniform) ─────────────
        _experiment C c uniform

        # ─── Experiment D: stress (100% reads during compaction) ─────────────
        _experiment D d uniform

        echo ""
        echo "=== [c=$cores, t=$threads] Complete ==="
    done

    echo ""
    echo "=== [c=$cores] All thread counts complete ==="
}

# Launch all three core configs in parallel with non-overlapping CPU pins.
echo "=== Launching parallel containers (3 core configs × 3 thread counts × 4 workloads) ==="
echo "    c=1  -> cpuset 0"
echo "    c=2  -> cpuset 2,4"
echo "    c=4  -> cpuset 6,8,10,12"
echo ""

run_one_core_config 1 "0"           & PID_C1=$!
run_one_core_config 2 "2,4"         & PID_C2=$!
run_one_core_config 4 "6,8,10,12"   & PID_C4=$!

wait $PID_C1; STATUS_C1=$?
wait $PID_C2; STATUS_C2=$?
wait $PID_C4; STATUS_C4=$?

echo ""
echo "=== All experiments complete ==="
echo "    c=1  exit=$STATUS_C1  -> $RESULTS_DIR/experiments_c1.json"
echo "    c=2  exit=$STATUS_C2  -> $RESULTS_DIR/experiments_c2.json"
echo "    c=4  exit=$STATUS_C4  -> $RESULTS_DIR/experiments_c4.json"
echo ""
echo "Generate plots:"
echo "  python3 analysis/plot.py $RESULTS_DIR/experiments_c1.json $RESULTS_DIR/experiments_c2.json $RESULTS_DIR/experiments_c4.json --out $RESULTS_DIR/plots"
