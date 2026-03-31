// Copyright 2026 August S.H.
// Licensed under the Apache License, Version 2.0
// This file is part of the preemptive-lsm project.
// It is original work and not derived from mini-lsm.

use rand::Rng;
use rand_distr::{Distribution, Zipf};

/// YCSB-style workload type.
#[derive(Debug, Clone, clap::ValueEnum)]
pub enum Workload {
    /// Workload A: 50% reads, 50% writes.
    A,
    /// Workload B: 95% reads, 5% writes.
    B,
    /// Workload C: 5% reads, 95% writes (write-heavy).
    C,
    /// Workload D: 100% reads (stress test — measure read latency during compaction).
    D,
}

/// Key distribution for selecting which key to access.
#[derive(Debug, Clone, clap::ValueEnum)]
pub enum KeyDistribution {
    /// Each key equally likely.
    Uniform,
    /// YCSB-standard scrambled Zipfian (s = 0.99). A few keys are very hot,
    /// most are cold — realistic for real-world workloads.
    Zipfian,
}

/// Returns `true` if the next operation should be a read, given the workload.
pub fn is_read(workload: &Workload, rng: &mut impl Rng) -> bool {
    let read_pct: f64 = match workload {
        Workload::A => 0.50,
        Workload::B => 0.95,
        Workload::C => 0.05,
        Workload::D => 1.00,
    };
    rng.random::<f64>() < read_pct
}

/// Pre-built key generator that avoids re-constructing the Zipf distribution
/// on every call.
pub struct KeyGenerator {
    key_space: u64,
    zipf: Option<Zipf<f64>>,
}

impl KeyGenerator {
    pub fn new(key_space: u64, distribution: &KeyDistribution) -> Self {
        let zipf = match distribution {
            KeyDistribution::Uniform => None,
            KeyDistribution::Zipfian => {
                // s = 0.99 is the YCSB default exponent.
                Some(Zipf::new(key_space as f64, 0.99).unwrap())
            }
        };
        Self { key_space, zipf }
    }

    /// Generate a random key formatted as "key{n:016}".
    pub fn next_key(&self, rng: &mut impl Rng) -> Vec<u8> {
        let n: u64 = match &self.zipf {
            None => rng.random_range(0..self.key_space),
            Some(zipf) => {
                // Zipf::sample returns f64 in [1, key_space].
                let rank = zipf.sample(rng) as u64;
                // FNV-style scramble so hot keys aren't all at the start of the keyspace.
                rank.wrapping_mul(2654435761) % self.key_space
            }
        };
        format!("key{:016}", n).into_bytes()
    }
}

/// Generate a fixed-size random value payload.
pub fn random_value(rng: &mut impl Rng, size: usize) -> Vec<u8> {
    (0..size).map(|_| rng.random::<u8>()).collect()
}