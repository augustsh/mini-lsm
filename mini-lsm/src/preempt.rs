// Copyright 2026 preemptive-lsm authors
// Licensed under the Apache License, Version 2.0
// This file is part of the preemptive-lsm project.
// It is original work and not derived from mini-lsm.

use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};

/// How the compaction loop decides whether to yield at a checkpoint.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum YieldStrategy {
    /// Baseline: never yield inside the merge loop.
    NoYield,
    /// Yield every `interval` entries regardless of foreground pressure.
    UnconditionalYield { interval: usize },
    /// Yield every `interval` entries, but only when at least one foreground
    /// operation is in-flight.
    ConditionalYield { interval: usize },
}

/// Shared state for cooperative preemption between the compaction thread
/// and foreground operations. Always accessed through `Arc<YieldState>`.
pub struct YieldState {
    /// Number of foreground operations currently in-flight.
    /// Written by foreground threads via `enter`/`exit`, read by compaction.
    fg_ops_in_flight: AtomicUsize,
    pub strategy: YieldStrategy,
}

impl YieldState {
    pub fn new(strategy: YieldStrategy) -> Arc<Self> {
        if let YieldStrategy::UnconditionalYield { interval }
            | YieldStrategy::ConditionalYield { interval } = strategy
        {
            assert!(interval > 0, "yield interval must be > 0");
        }
        Arc::new(Self {
            fg_ops_in_flight: AtomicUsize::new(0),
            strategy,
        })
    }

    /// Called at the start of every foreground operation.
    #[inline]
    pub fn enter(&self) {
        self.fg_ops_in_flight.fetch_add(1, Ordering::Relaxed);
    }

    /// Called at the end of every foreground operation (must match every `enter`).
    #[inline]
    pub fn exit(&self) {
        self.fg_ops_in_flight.fetch_sub(1, Ordering::Relaxed);
    }

    /// Returns the initial value to pass to `maybe_yield`.
    /// For `NoYield`, returns `usize::MAX` so the countdown effectively never fires.
    #[inline]
    pub fn initial_countdown(&self) -> usize {
        match self.strategy {
            YieldStrategy::NoYield => usize::MAX,
            YieldStrategy::UnconditionalYield { interval }
            | YieldStrategy::ConditionalYield { interval } => interval,
        }
    }

    /// Called from the compaction loop on every entry.
    /// `countdown` must be initialized with `initial_countdown()`.
    /// Uses a decrement instead of modulo division — avoids a 64-bit division per entry.
    #[inline]
    pub fn maybe_yield(&self, countdown: &mut usize) {
        *countdown = countdown.wrapping_sub(1);
        if *countdown != 0 {
            return;
        }
        match self.strategy {
            YieldStrategy::NoYield => {
                *countdown = usize::MAX; // reset; effectively never fires
            }
            YieldStrategy::UnconditionalYield { interval } => {
                *countdown = interval;
                std::thread::yield_now();
            }
            YieldStrategy::ConditionalYield { interval } => {
                *countdown = interval;
                if self.fg_ops_in_flight.load(Ordering::Relaxed) > 0 {
                    std::thread::yield_now();
                }
            }
        }
    }
}