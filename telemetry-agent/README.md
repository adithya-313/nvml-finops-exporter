# telemetry-agent

A lightweight Go agent that exposes NVIDIA GPU telemetry via an HTTP `/metrics` endpoint using NVML.

## Design

- **`internal/gpu/nvml.go`** – Wraps the NVIDIA Management Library (NVML) Go bindings.  The only public function, `CollectGpuMetrics`, returns a `SystemStatus` struct that is either `healthy` (with per-GPU metrics) or `degraded` (with an error message).
- **`main.go`** – HTTP server on `:8080`.  On startup it calls `CollectGpuMetrics` once; the result is served on every `GET /metrics` request.  If NVML cannot be initialised the server still boots and reports `degraded`.

## Usage

```bash
go build -o telemetry-agent .
./telemetry-agent &
curl -s http://localhost:8080/metrics | jq
```
