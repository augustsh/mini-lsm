FROM rust:latest AS builder
WORKDIR /app
COPY . .
RUN cargo build --release -p bench

FROM debian:bookworm-slim
COPY --from=builder /app/target/release/bench /usr/local/bin/bench
ENTRYPOINT ["bench"]
