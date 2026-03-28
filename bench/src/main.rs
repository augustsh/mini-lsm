// Copyright 2026 preemptive-lsm authors
// Licensed under the Apache License, Version 2.0
// This file is part of the preemptive-lsm project.
// It is original work and not derived from mini-lsm.

mod metrics;
mod workloads;

use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::Result;
use clap::{Parser, ValueEnum};
use mini_lsm::compact::{CompactionOptions, LeveledCompactionOptions};
use mini_lsm::lsm_storage::{LsmStorageOptions, MiniLsm};
use tempfile::TempDir;

use metrics::LatencyRecorder;
use workloads::{Workload, is_read, random_key, random_value};

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

    /// Number of foreground threads.
    #[arg(long, default_value = "4")]
    threads: usize,

    /// Benchmark duration in seconds.
    #[arg(long, default_value = "30")]
    duration_secs: u64,

    /// Number of keys in the pre-loaded dataset.
    #[arg(long, default_value = "100000")]
    key_space: u64,

    /// Value size in bytes.
    #[arg(long, default_value = "256")]
    value_size: usize,
}

fn open_store(dir: &TempDir) -> Result<Arc<MiniLsm>> {
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
    };
    Ok(MiniLsm::open(dir.path(), opts)?)
}

fn preload(store: &Arc<MiniLsm>, key_space: u64, value_size: usize) -> Result<()> {
    use rand::SeedableRng;
    let mut rng = rand::rngs::SmallRng::seed_from_u64(42);
    eprintln!("Pre-loading {} keys...", key_space);
    for i in 0..key_space {
        let key = format!("key{:016}", i).into_bytes();
        let value = random_value(&mut rng, value_size);
        store.put(&key, &value)?;
    }
    eprintln!("Pre-load complete.");
    Ok(())
}

fn run_benchmark(args: &Args, store: Arc<MiniLsm>) -> Result<()> {
    let duration = Duration::from_secs(args.duration_secs);
    let key_space = args.key_space;
    let value_size = args.value_size;
    let workload = args.workload.clone();

    let mut handles = Vec::new();
    let recorder = Arc::new(std::sync::Mutex::new(LatencyRecorder::new()));

    for thread_id in 0..args.threads {
        let store = Arc::clone(&store);
        let workload = workload.clone();
        let recorder = Arc::clone(&recorder);

        let handle = std::thread::spawn(move || -> Result<()> {
            use rand::SeedableRng;
            let mut rng = rand::rngs::SmallRng::seed_from_u64(thread_id as u64 + 100);
            let deadline = Instant::now() + duration;

            while Instant::now() < deadline {
                let key = random_key(&mut rng, key_space);
                let op_start = Instant::now();

                if is_read(&workload, &mut rng) {
                    let _ = store.get(&key)?;
                } else {
                    let value = random_value(&mut rng, value_size);
                    store.put(&key, &value)?;
                }

                let latency = op_start.elapsed();
                recorder.lock().unwrap().record(latency);
            }
            Ok(())
        });
        handles.push(handle);
    }

    for handle in handles {
        handle.join().expect("thread panicked")?;
    }

    let label = format!(
        "strategy={:?} workload={:?} threads={}",
        args.strategy, args.workload, args.threads
    );
    recorder.lock().unwrap().print_percentiles(&label);
    Ok(())
}

fn main() -> Result<()> {
    let args = Args::parse();
    let dir = TempDir::new()?;
    let store = open_store(&dir)?;
    preload(&store, args.key_space, args.value_size)?;
    run_benchmark(&args, store)?;
    Ok(())
}
