// Copyright 2026 preemptive-lsm authors
// Licensed under the Apache License, Version 2.0
// This file is part of the preemptive-lsm project.
// It is original work and not derived from mini-lsm.

mod metrics;
mod workloads;

use std::collections::BTreeMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::Result;
use clap::{Parser, ValueEnum};
use mini_lsm::compact::{CompactionOptions, LeveledCompactionOptions};
use mini_lsm::lsm_storage::{LsmStorageOptions, MiniLsm};
use tempfile::TempDir;

use metrics::{BenchResult, LatencyRecorder, TimeSeriesPoint};
use workloads::{KeyDistribution, KeyGenerator, Workload, is_read, random_value};

// --- BEGIN PREEMPTIVE YIELD MODIFICATION ---
fn to_storage_strategy(
    s: &YieldStrategy,
    interval: usize,
) -> mini_lsm::preempt::YieldStrategy {
    match s {
        YieldStrategy::NoYield => mini_lsm::preempt::YieldStrategy::NoYield,
        YieldStrategy::UnconditionalYield => {
            mini_lsm::preempt::YieldStrategy::UnconditionalYield { interval }
        }
        YieldStrategy::ConditionalYield => {
            mini_lsm::preempt::YieldStrategy::ConditionalYield { interval }
        }
    }
}
// --- END PREEMPTIVE YIELD MODIFICATION ---

/// Yield strategy for the compaction thread.
#[derive(Debug, Clone, ValueEnum)]
pub enum YieldStrategy {
    /// Baseline: no yielding in the compaction loop.
    NoYield,
    /// Yield every N entries regardless of foreground pressure.
    UnconditionalYield,
    /// Yield every N entries only when the foreground flag is set.
    ConditionalYield,
}

#[derive(Parser, Debug)]
#[command(about = "Benchmark harness for preemptive-lsm compaction research")]
struct Args {
    /// Yield strategy to use.
    #[arg(long, default_value = "no-yield")]
    strategy: YieldStrategy,

    /// Yield interval (entries between yield checkpoints).
    #[arg(long, default_value = "1000")]
    yield_interval: usize,

    /// YCSB workload type.
    #[arg(long, default_value = "a")]
    workload: Workload,

    /// Key distribution (uniform or zipfian).
    #[arg(long, default_value = "uniform")]
    distribution: KeyDistribution,

    /// Number of foreground threads.
    #[arg(long, default_value = "1")]
    threads: usize,

    /// Benchmark duration in seconds.
    #[arg(long, default_value = "120")]
    duration_secs: u64,

    /// Number of keys in the pre-loaded dataset.
    #[arg(long, default_value = "1000000")]
    key_space: u64,

    /// Value size in bytes.
    #[arg(long, default_value = "1024")]
    value_size: usize,

    /// Number of benchmark repetitions to run (histograms are merged across runs).
    #[arg(long, default_value = "1")]
    runs: usize,

    /// How often (in seconds) to emit a time-series snapshot.
    #[arg(long, default_value = "1")]
    snapshot_secs: u64,

    /// Append results as a JSON record to this file (creates or extends a JSON array).
    #[arg(long)]
    json_out: Option<PathBuf>,
}

// --- BEGIN PREEMPTIVE YIELD MODIFICATION ---
fn open_store(
    dir: &TempDir,
    yield_strategy: mini_lsm::preempt::YieldStrategy,
) -> Result<Arc<MiniLsm>> {
// --- END PREEMPTIVE YIELD MODIFICATION ---
    let opts = LsmStorageOptions {
        block_size: 4096,
        target_sst_size: 2 << 20, // 2 MB
        num_memtable_limit: 3,
        compaction_options: CompactionOptions::Leveled(LeveledCompactionOptions {
            level0_file_num_compaction_trigger: 4,
            max_levels: 4,
            base_level_size_mb: 128,
            level_size_multiplier: 2,
        }),
        enable_wal: false,
        serializable: false,
        yield_strategy, // ADDED
    };
    Ok(MiniLsm::open(dir.path(), opts)?)
}

fn preload(store: &Arc<MiniLsm>, key_space: u64, value_size: usize) -> Result<()> {
    use rand::SeedableRng;
    let mut rng = rand::rngs::SmallRng::seed_from_u64(42);
    eprintln!("Pre-loading {} keys ({} bytes each)...", key_space, value_size);
    for i in 0..key_space {
        let key = format!("key{:016}", i).into_bytes();
        let value = random_value(&mut rng, value_size);
        store.put(&key, &value)?;
    }
    eprintln!("Pre-load complete.");
    Ok(())
}

fn run_benchmark(args: &Args, store: Arc<MiniLsm>) -> Result<BenchResult> {
    let duration = Duration::from_secs(args.duration_secs);
    let snapshot_secs = args.snapshot_secs;
    let key_space = args.key_space;
    let value_size = args.value_size;
    let workload = args.workload.clone();
    let distribution = args.distribution.clone();

    let mut merged = LatencyRecorder::new();
    let mut bucket_map: BTreeMap<u64, LatencyRecorder> = BTreeMap::new();
    let global_start = Instant::now();

    for run in 0..args.runs {
        let mut handles = Vec::new();

        for thread_id in 0..args.threads {
            let store = Arc::clone(&store);
            let workload = workload.clone();
            let distribution = distribution.clone();
            let seed = (run * args.threads + thread_id) as u64 + 100;

            let handle = std::thread::spawn(move || -> Result<(LatencyRecorder, Vec<(u64, LatencyRecorder)>)> {
                use rand::SeedableRng;
                let mut rng = rand::rngs::SmallRng::seed_from_u64(seed);
                let keygen = KeyGenerator::new(key_space, &distribution);
                let deadline = Instant::now() + duration;
                let mut aggregate = LatencyRecorder::new();
                let mut window = LatencyRecorder::new();
                let mut window_start = Instant::now();
                let mut snapshots: Vec<(u64, LatencyRecorder)> = Vec::new();

                while Instant::now() < deadline {
                    let key = keygen.next_key(&mut rng);
                    let op_start = Instant::now();

                    if is_read(&workload, &mut rng) {
                        let _ = store.get(&key)?;
                    } else {
                        let value = random_value(&mut rng, value_size);
                        store.put(&key, &value)?;
                    }

                    let latency = op_start.elapsed();
                    aggregate.record(latency);
                    window.record(latency);

                    if window_start.elapsed().as_secs() >= snapshot_secs {
                        let bucket = global_start.elapsed().as_secs() / snapshot_secs;
                        snapshots.push((bucket, std::mem::replace(&mut window, LatencyRecorder::new())));
                        window_start = Instant::now();
                    }
                }

                if window.count() > 0 {
                    let bucket = global_start.elapsed().as_secs() / snapshot_secs;
                    snapshots.push((bucket, window));
                }

                Ok((aggregate, snapshots))
            });
            handles.push(handle);
        }

        for handle in handles {
            let (rec, snaps) = handle.join().expect("thread panicked")?;
            merged.merge(rec);
            for (bucket, snap) in snaps {
                bucket_map
                    .entry(bucket)
                    .or_insert_with(LatencyRecorder::new)
                    .merge(snap);
            }
        }
    }

    let snapshot_secs_f64 = snapshot_secs as f64;
    let time_series: Vec<TimeSeriesPoint> = bucket_map
        .into_iter()
        .map(|(bucket, rec)| {
            rec.to_snapshot((bucket + 1) as f64 * snapshot_secs_f64, snapshot_secs_f64)
        })
        .collect();

    let label = format!(
        "strategy={:?} workload={:?} dist={:?} threads={} runs={}",
        args.strategy, args.workload, args.distribution, args.threads, args.runs
    );
    merged.print_percentiles(&label);
    Ok(merged.to_result(
        &format!("{:?}", args.strategy),
        &format!("{:?}", args.workload),
        args.threads,
        args.yield_interval,
        time_series,
    ))
}

fn append_json(path: &PathBuf, result: &BenchResult) -> Result<()> {
    let mut records: Vec<BenchResult> = if path.exists() {
        let data = std::fs::read_to_string(path)?;
        serde_json::from_str(&data)?
    } else {
        Vec::new()
    };
    records.push(serde_json::from_value(serde_json::to_value(result)?)?);
    let json = serde_json::to_string_pretty(&records)?;
    std::fs::write(path, json)?;
    eprintln!("Results appended to {}", path.display());
    Ok(())
}

fn main() -> Result<()> {
    let args = Args::parse();
    let dir = TempDir::new()?;
    // --- BEGIN PREEMPTIVE YIELD MODIFICATION ---
    let storage_strategy = to_storage_strategy(&args.strategy, args.yield_interval);
    let store = open_store(&dir, storage_strategy)?;
    // --- END PREEMPTIVE YIELD MODIFICATION ---
    preload(&store, args.key_space, args.value_size)?;
    let result = run_benchmark(&args, store)?;
    if let Some(ref path) = args.json_out {
        if let Some(parent) = path.parent() {
            if !parent.as_os_str().is_empty() {
                std::fs::create_dir_all(parent)?;
            }
        }
        append_json(path, &result)?;
    }
    Ok(())
}
