# preemptive-lsm

This repository is a **derivative work** of [mini-lsm](https://github.com/skyzh/mini-lsm)
by [Alex Chi Z](https://github.com/skyzh), licensed under the Apache License, Version 2.0.

Only the **Week 2 reference solution** (`mini-lsm/`) has been extracted and modified for
research purposes. All other course infrastructure (starter code, MVCC variant, tutorial
book, CI configs) has been removed.

## Research Goal

Study whether software-simulated **preemptive yielding** in background compaction reduces
tail latency for foreground read/write operations in an LSM-tree storage engine.

We insert cooperative yield points into the compaction merge loop so the compaction thread
periodically checks whether foreground work is pending and, if so, yields execution.

## Repository Structure

```
preemptive-lsm/
├── CLAUDE.md              # Project instructions for AI-assisted development
├── LICENSE                # Original Apache 2.0 license from mini-lsm (preserved)
├── README.md              # This file
├── mini-lsm/             # Week 2 solution extracted from skyzh/mini-lsm
│   └── src/
│       ├── compact.rs     # PRIMARY MODIFICATION TARGET
│       ├── lsm_storage.rs # May need minor changes for yield signaling
│       └── ...
├── bench/                 # Benchmark harness (original work)
│   └── src/
│       ├── main.rs        # CLI entry point
│       ├── workloads.rs   # YCSB-style workload generators
│       └── metrics.rs     # HDR histogram latency recorder
└── analysis/              # Plotting and analysis scripts (original work)
    └── plot.py
```

## Modifications to mini-lsm

All modifications follow the annotation rules in `CLAUDE.md`:

- Every modified file carries a `// MODIFIED by ...` header.
- Non-trivial changes are wrapped in `// --- BEGIN/END PREEMPTIVE YIELD MODIFICATION ---` blocks.

Planned changes:
- **`compact.rs`** — insert yield checkpoints inside the SST merge loop
- **`lsm_storage.rs`** — add shared `Arc<AtomicBool>` yield flag; set/clear in `get()`/`put()`

## Yield Strategies

| Strategy | Description |
|---|---|
| `NoYield` | Baseline — no modification to compaction loop |
| `UnconditionalYield` | Yield every N entries regardless of foreground pressure |
| `ConditionalYield` | Yield every N entries only when the foreground flag is set |

## Running the Benchmark

```bash
# Build
cargo build --release --bin bench

# Baseline (no yielding), Workload A, 4 threads, 30 seconds
cargo run --release --bin bench -- --strategy no-yield --workload a --threads 4 --duration-secs 30

# Conditional yield, Workload B
cargo run --release --bin bench -- --strategy conditional-yield --workload b --threads 4
```

## Running Tests

```bash
cargo test -p mini-lsm
```

## License

This derivative work is distributed under the **Apache License, Version 2.0** — see [LICENSE](LICENSE).

Original work copyright © 2022–2025 Alex Chi Z. Original source: https://github.com/skyzh/mini-lsm