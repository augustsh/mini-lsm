# mini-lsm

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

## Modifications to mini-lsm

- Every modified file carries a `// MODIFIED by ...` header.
- Non-trivial changes are wrapped in `// --- BEGIN/END PREEMPTIVE YIELD MODIFICATION ---` blocks.

## Yield Strategies

| Strategy | Description |
|---|---|
| `NoYield` | Baseline — no modification to compaction loop |
| `UnconditionalYield` | Yield every N entries regardless of foreground pressure |
| `ConditionalYield` | Yield every N entries only when the foreground flag is set |

## Running the Benchmark

Requires Rust toolchain (https://www.rust-lang.org/tools/install).

### Running individual strategies
```bash
# Build
cargo build --release --bin bench

# Baseline (no yielding), Workload A, 4 threads, 30 seconds
cargo run --release --bin bench -- --strategy no-yield --workload a --threads 4 --duration-secs 30

# Conditional yield, Workload B
cargo run --release --bin bench -- --strategy conditional-yield --workload b --threads 4
```

### Run the full suite of strategies and workloads
This requires Docker to be  installed and the daemon running.
In its current configuration, the script requires 7+ CPU cores to run the different strategies in parallel.
The full test suite takes several hours to complete.
```bash
./scripts/run_experiments.sh
```

## Running Tests

```bash
cargo test -p mini-lsm
```

## License

This derivative work is distributed under the **Apache License, Version 2.0** — see [LICENSE](LICENSE).

Original work copyright © 2022–2025 Alex Chi Z. Original source: https://github.com/skyzh/mini-lsm