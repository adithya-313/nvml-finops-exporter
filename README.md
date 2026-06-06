# NVIDIA GPU Telemetry & FinOps Pipeline (v2.1-Enterprise)

A real-time, distributed gRPC telemetry pipeline tracking high-frequency NVIDIA GPU metrics, multi-variate statistical anomalies, clock desynchronization, and structural financial losses. Designed for scalable AI infrastructure.

## 🧠 System Architecture & Scalability

This pipeline uses a decoupled microservice architecture designed to scale across GPU clusters:
- **Stateless Extraction (Go Agent):** A lightweight daemon (`main.go`) deployed per-node. Queries `nvml` directly. Takes < 15MB RAM.
- **Asynchronous Aggregation (Python Engine):** A central ML brain using `grpc.aio` over HTTP/2 multiplexing to ingest thousands of concurrent node streams without thread-blocking.
- **Constant-Time Math:** Multi-variate Mahalanobis distance calculated via vectorized C-bindings in `NumPy` (`np.linalg.pinv`), preventing O(n^2) scaling bottlenecks.

## ⚡ Core Features
- **Mahalanobis Multi-Variate Anomaly Detection:** $D_M > 3.5$ triggers `[CRITICAL ANOMALY: MULTI-VARIATE DEVIATION]`.
- **Wasted Spend Calculation:** Dynamically tracks idle-burn and zombie GPUs, calculating pro-rated dollar-loss to the millisecond.
- **NTP Time Drift Tracking:** Detects host-clock desynchronization > 50ms.
- **Async Circuit Breaker:** Protects the gRPC stream with a 30s recovery timeout on failure.

## 📈 Validated Performance Profile (gRPC vs REST)
Latency was aggressively optimized by eliminating sequential HTTP JSON polling.
* **V1 Prototype (Sync HTTP/JSON):** `~80.00 ms` per loop.
* **V2 Enterprise (gRPC/Protobuf):** `~6.57 ms` per loop.
* **Result:** **91.8% Latency Reduction**.

---

## 🏭 Production Deployment (Docker / Cluster)
For standard cloud deployment, the pipeline is fully containerized.

```bash
# Build and deploy the Go hardware-extraction layer and Python brain
docker compose up -d --build

# View real-time aggregated logs
docker compose logs -f
```
(Note: Docker execution isolates the Go daemon from bare-metal Windows NVML drivers. For physical hardware validation, use the Local Development Mode below).

## 💻 Local Development & Diagnostic Mode
For local development or live hardware validation on a single node, bypass Docker and execute natively.

### 1. Start the Pipeline Natively (3 Terminals)
```powershell
# Terminal 1: Hardware Layer
cd telemetry-agent && go run main.go

# Terminal 2: ML Engine
cd accountant && python engine.py

# Terminal 3: UI
cd dashboard && npm run dev
```

### 2. Run a Hardware Stress Test
To validate the anomaly detection engine against physical silicon, launch the native CUDA load generator:

```powershell
python stress_test.py
```

### 3. FinOps Ledger Diagnostics
To test the financial waste accumulator without requiring a physical VRAM leak, trigger the diagnostic flag:

```powershell
python engine.py --mock-zombie
```
