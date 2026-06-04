# telemetry-agent

A NATS-based telemetry and FinOps engine for NVIDIA GPU infrastructure. The stack consists of a Go agent that collects GPU metrics via NVML and publishes to NATS, and a Python FinOps engine that consumes the stream, runs scikit-learn Isolation Forest anomaly detection, and persists a Write-Ahead Log (WAL) to TimescaleDB.

## Architecture

### Go NATS Publisher (`main.go`)

- Collects GPU metrics every 1s via platform-split NVML backends (`internal/gpu/`).
- Serializes metrics as Protobuf `TelemetryResponse` and publishes to NATS subject `telemetry.gpu.metrics`.
- Runs a background `pollNTP()` goroutine that queries `time.google.com` via `github.com/beevik/ntp` every 60s; offset attached to every message.
- Multi-stage Dockerfile (`golang:alpine` → `alpine:latest`); compose stack on `finops_net`.

### Python FinOps Engine (`accountant/engine.py`)

- Asynchronous NATS subscriber using `nats-py`.
- Deserializes Protobuf messages; inserts raw telemetry into TimescaleDB hypertable `gpu_metrics` (async WAL via `psycopg2` + `ThreadPoolExecutor`).
- Maintains per-GPU rolling 300-tick feature-vector deques (`[util%, mem_ratio, temp°C, power_W]`).

## Core Features

- **Isolation Forest Anomaly Detection** — Replaces V2's Mahalanobis distance. A 50-sample calibration phase fits `sklearn.ensemble.IsolationForest(contamination=0.1, n_estimators=100)`. Prediction of `-1` triggers `[CRITICAL ANOMALY: ISOLATION FOREST DEVIATION]`. Model is refit every 50 ticks to adapt to drift.
- **NTP Time Drift Tracking** — Offset from `pollNTP()` is displayed on every loop iteration. An `|offset| > 50ms` fires `[CRITICAL TIME DRIFT]`.
- **WAL Persistence** — Every metric is inserted into TimescaleDB `gpu_metrics` hypertable for historical querying.
- **Wasted Spend Calculation** — Evaluates idle-burn (util < 5% and power > 50W) and zombie GPUs (util < 5% and memory ratio > 0.90); costs are looked up from `pricing.json`.

## Usage

```bash
docker compose up --build
```

Starts all four services: NATS, TimescaleDB, Go agent (publisher), and Python FinOps engine (subscriber + ML + WAL sink). The engine auto-retries on startup until NATS and TimescaleDB are ready.

## Performance

Latency reduced from **80 ms (V1 sync HTTP)** to **5–10 ms (V3 NATS + Isolation Forest)**. The I/O bottleneck was eliminated by NATS pub/sub; the primary time cost is now the Isolation Forest `score_samples` call on the 4D feature vector. Full benchmarks in `docs/BENCHMARKS.md`.

Proto stubs are compiled into `internal/pb/` (Go) and `accountant/pb/` (Python). Recompile with:

```bash
protoc --go_out=. --go_opt=paths=source_relative --go-grpc_out=. --go-grpc_opt=paths=source_relative -I proto proto/telemetry.proto
python -m grpc_tools.protoc -I ../proto --python_out=. --grpc_python_out=. ../proto/telemetry.proto
```
