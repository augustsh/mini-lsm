// Copyright 2026 preemptive-lsm authors
// Licensed under the Apache License, Version 2.0
// This file is part of the preemptive-lsm project.
// It is original work and not derived from mini-lsm.

use hdrhistogram::Histogram;
use serde::{Deserialize, Serialize};
use std::time::Duration;

/// One point in a latency/throughput time series.
#[derive(Debug, Serialize, Deserialize)]
pub struct TimeSeriesPoint {
    /// Seconds elapsed since the start of the benchmark (end of snapshot window).
    pub elapsed_secs: f64,
    /// Latencies in fractional microseconds (sub-µs resolution).
    pub p50_us: f64,
    pub p99_us: f64,
    pub p999_us: f64,
    /// Aggregate ops/sec across all threads in this window.
    pub throughput_ops: f64,
}

/// A serializable snapshot of one benchmark run's results.
#[derive(Debug, Serialize, Deserialize)]
pub struct BenchResult {
    pub strategy: String,
    pub workload: String,
    pub threads: usize,
    #[serde(default = "default_cores")]
    pub cores: usize,
    pub yield_interval: usize,
    pub operations: u64,
    pub throughput_ops: f64,
    /// Latencies in fractional microseconds (sub-µs resolution).
    pub p50_us: f64,
    pub p95_us: f64,
    pub p99_us: f64,
    pub p999_us: f64,
    pub max_us: f64,
    /// Per-window time series. Empty for results loaded from older JSON files.
    #[serde(default)]
    pub time_series: Vec<TimeSeriesPoint>,
}

fn default_cores() -> usize {
    1
}

pub struct LatencyRecorder {
    // Internally records in nanoseconds for sub-µs precision.
    histogram: Histogram<u64>,
    start: std::time::Instant,
    count: u64,
}

impl LatencyRecorder {
    pub fn new() -> Self {
        Self {
            // Range: 1 ns to 60 s, 3 significant figures (~0.1% error).
            histogram: Histogram::new_with_bounds(1, 60_000_000_000, 3).unwrap(),
            start: std::time::Instant::now(),
            count: 0,
        }
    }

    pub fn merge(&mut self, other: Self) {
        self.histogram.add(&other.histogram).ok();
        self.count += other.count;
    }

    pub fn record(&mut self, latency: Duration) {
        let nanos = latency.as_nanos().max(1) as u64;
        self.histogram.record(nanos).ok();
        self.count += 1;
    }

    pub fn count(&self) -> u64 {
        self.count
    }

    pub fn elapsed(&self) -> Duration {
        self.start.elapsed()
    }

    pub fn throughput(&self) -> f64 {
        let secs = self.elapsed().as_secs_f64();
        if secs > 0.0 { self.count as f64 / secs } else { 0.0 }
    }

    /// Convert a histogram value (nanoseconds) to fractional microseconds.
    fn ns_to_us(ns: u64) -> f64 {
        ns as f64 / 1000.0
    }

    pub fn to_snapshot(&self, elapsed_secs: f64, window_secs: f64) -> TimeSeriesPoint {
        TimeSeriesPoint {
            elapsed_secs,
            p50_us: Self::ns_to_us(self.histogram.value_at_quantile(0.50)),
            p99_us: Self::ns_to_us(self.histogram.value_at_quantile(0.99)),
            p999_us: Self::ns_to_us(self.histogram.value_at_quantile(0.999)),
            throughput_ops: if window_secs > 0.0 {
                self.count as f64 / window_secs
            } else {
                0.0
            },
        }
    }

    pub fn to_result(
        &self,
        strategy: &str,
        workload: &str,
        threads: usize,
        cores: usize,
        yield_interval: usize,
        time_series: Vec<TimeSeriesPoint>,
    ) -> BenchResult {
        BenchResult {
            strategy: strategy.to_string(),
            workload: workload.to_string(),
            threads,
            cores,
            yield_interval,
            operations: self.count,
            throughput_ops: self.throughput(),
            p50_us: Self::ns_to_us(self.histogram.value_at_quantile(0.50)),
            p95_us: Self::ns_to_us(self.histogram.value_at_quantile(0.95)),
            p99_us: Self::ns_to_us(self.histogram.value_at_quantile(0.99)),
            p999_us: Self::ns_to_us(self.histogram.value_at_quantile(0.999)),
            max_us: Self::ns_to_us(self.histogram.max()),
            time_series,
        }
    }

    pub fn print_percentiles(&self, label: &str) {
        println!("=== {} ===", label);
        println!("  Operations : {}", self.count);
        println!("  Throughput : {:.1} ops/sec", self.throughput());
        println!("  p50  : {:.2} µs", Self::ns_to_us(self.histogram.value_at_quantile(0.50)));
        println!("  p95  : {:.2} µs", Self::ns_to_us(self.histogram.value_at_quantile(0.95)));
        println!("  p99  : {:.2} µs", Self::ns_to_us(self.histogram.value_at_quantile(0.99)));
        println!("  p99.9: {:.2} µs", Self::ns_to_us(self.histogram.value_at_quantile(0.999)));
        println!("  max  : {:.2} µs", Self::ns_to_us(self.histogram.max()));
    }
}