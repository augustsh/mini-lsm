// Copyright 2026 preemptive-lsm authors
// Licensed under the Apache License, Version 2.0
// This file is part of the preemptive-lsm project.
// It is original work and not derived from mini-lsm.

use hdrhistogram::Histogram;
use std::time::{Duration, Instant};

pub struct LatencyRecorder {
    histogram: Histogram<u64>,
    start: Instant,
    count: u64,
}

impl LatencyRecorder {
    pub fn new() -> Self {
        Self {
            // Values in microseconds, range 1us to 60s
            histogram: Histogram::new_with_bounds(1, 60_000_000, 3).unwrap(),
            start: Instant::now(),
            count: 0,
        }
    }

    pub fn record(&mut self, latency: Duration) {
        let micros = latency.as_micros().max(1) as u64;
        self.histogram.record(micros).ok();
        self.count += 1;
    }

    pub fn elapsed(&self) -> Duration {
        self.start.elapsed()
    }

    pub fn throughput(&self) -> f64 {
        let secs = self.elapsed().as_secs_f64();
        if secs > 0.0 {
            self.count as f64 / secs
        } else {
            0.0
        }
    }

    pub fn print_percentiles(&self, label: &str) {
        println!("=== {} ===", label);
        println!("  Operations : {}", self.count);
        println!("  Throughput : {:.1} ops/sec", self.throughput());
        println!(
            "  p50  : {} µs",
            self.histogram.value_at_quantile(0.50)
        );
        println!(
            "  p95  : {} µs",
            self.histogram.value_at_quantile(0.95)
        );
        println!(
            "  p99  : {} µs",
            self.histogram.value_at_quantile(0.99)
        );
        println!(
            "  p99.9: {} µs",
            self.histogram.value_at_quantile(0.999)
        );
        println!(
            "  max  : {} µs",
            self.histogram.max()
        );
    }
}