// Copyright 2026 preemptive-lsm authors
// Licensed under the Apache License, Version 2.0
// This file is part of the preemptive-lsm project.
// It is original work and not derived from mini-lsm.

use rand::Rng;

/// YCSB-style workload type.
#[derive(Debug, Clone, clap::ValueEnum)]
pub enum Workload {
    /// Workload A: 50% reads, 50% writes.
    A,
    /// Workload B: 95% reads, 5% writes.
    B,
}

/// Returns `true` if the next operation should be a read, given the workload.
pub fn is_read(workload: &Workload, rng: &mut impl Rng) -> bool {
    let read_pct: f64 = match workload {
        Workload::A => 0.50,
        Workload::B => 0.95,
    };
    rng.random::<f64>() < read_pct
}

/// Generate a random key in the form "key{n}" where n is in [0, key_space).
pub fn random_key(rng: &mut impl Rng, key_space: u64) -> Vec<u8> {
    let n: u64 = rng.random_range(0..key_space);
    format!("key{:016}", n).into_bytes()
}

/// Generate a fixed-size value payload.
pub fn random_value(rng: &mut impl Rng, size: usize) -> Vec<u8> {
    (0..size).map(|_| rng.random::<u8>()).collect()
}
