# telemetry-agent

A gRPC-based telemetry and FinOps engine for NVIDIA GPU infrastructure. The stack consists of a Go gRPC server that collects GPU metrics via NVML, and a Python asynchronous FinOps engine that performs multi-variate anomaly detection, NTP time drift tracking, circuit breaker resilience, and wasted-spend calculations.

## Architecture

### Go gRPC Telemetry Agent (`main.go`)

- Exposes a `GpuTelemetry` gRPC service (defined in `proto/telemetry.proto`) on port `:50051`.
- Backed by platform-split NVML backends in `internal/gpu/`:
  - `nvml_windows.go` — NVML syscall loader (Windows).
  - `nvml_linux.go` — `nvidia-smi` parser with mock-data fallback when no GPU is available.
- Runs a background `pollNTP()` goroutine that queries `time.google.com` via `github.com/beevik/ntp` every 60s; the offset is attached to every `TelemetryResponse`.
- Multi-stage Dockerfile (`golang:alpine` → `alpine:latest`); compose stack on `finops_net`.

### Python Async FinOps Engine (`accountant/engine.py`)

- Asynchronous gRPC client using `grpc.aio` that continuously streams metrics from the agent.
- Maintains per-GPU rolling feature-vector deques (`[util%, mem_ratio, temp°C, power_W]`) for anomaly detection.

## Core Features

- **Mahalanobis Multi-Variate Anomaly Detection** — Computes distance across 4 dimensions simultaneously. A calibration phase gathers 50 baseline samples; the covariance matrix is inverted via `np.linalg.pinv` for numerical stability. D_M > 3.5 triggers a `[CRITICAL ANOMALY: MULTI-VARIATE DEVIATION]` alert.
- **NTP Time Drift Tracking** — Offset from `pollNTP()` is displayed on every loop iteration. An `|offset| > 50ms` fires `[CRITICAL TIME DRIFT]`.
- **Async Circuit Breaker** — Wraps gRPC calls: 3 consecutive failures open the circuit for a 30s recovery timeout, then transitions to half-open for retry.
- **Wasted Spend Calculation** — Evaluates idle-burn (util < 5% and power > 50W) and zombie GPUs (util < 5% and memory ratio > 0.90); costs are looked up from `pricing.json`.

## Performance

Latency reduced from **80 ms (V1 sync HTTP)** to **6.57 ms (V2 gRPC + Mahalanobis)** — a 91.8% improvement. The I/O bottleneck from sequential Prometheus range queries was eliminated by gRPC's efficient binary transport; the remaining time is dominated by `np.linalg.pinv` of the 4D covariance matrix. Full benchmarks in `docs/BENCHMARKS.md`.

## Usage

### Start the agent (Docker)

```bash
docker compose up --build
```

### Run the FinOps engine (separate terminal, from repo root)

```bash
cd ../accountant
pip install -r requirements.txt
python engine.py
```

Proto stubs are compiled into `internal/pb/` (Go) and `accountant/pb/` (Python). Recompile with:

```bash
protoc --go_out=. --go_opt=paths=source_relative --go-grpc_out=. --go-grpc_opt=paths=source_relative -I proto proto/telemetry.proto
python -m grpc_tools.protoc -I ../proto --python_out=. --grpc_python_out=. ../proto/telemetry.proto
```
