# NVIDIA GPU Telemetry & FinOps Pipeline (v2.1-Enterprise)

A real-time, distributed gRPC telemetry pipeline tracking high-frequency NVIDIA GPU metrics, multi-variate statistical anomalies, clock desynchronization, and structural financial losses.

## 🧠 System Architecture

- **Go gRPC Telemetry Agent (`main.go`):** Exposes a `GpuTelemetry` service on port `:50051`. Backed by native `nvml.dll` system calls to extract microsecond-level hardware state directly from the silicon. Includes a background `pollNTP()` goroutine syncing with `time.google.com`.
- **Python FinOps Engine (`accountant/engine.py`):** An asynchronous `grpc.aio` client that continuously streams metrics. Evaluates hardware states against dynamic financial threshold rules.
- **React Operations Dashboard (`dashboard/`):** A Vite-based UI mapping 4D telemetry vectors into visual states and real-time accumulating financial losses.

## ⚡ Core Features

- **Mahalanobis Multi-Variate Anomaly Detection:** Computes distance across 4 dimensions simultaneously (Utilization, Memory, Temp, Power). Inverts the covariance matrix via `np.linalg.pinv` to prevent singular matrix crashes during data flatlines. $D_M > 3.5$ triggers `[CRITICAL ANOMALY: MULTI-VARIATE DEVIATION]`.
- **Wasted Spend Calculation:** Dynamically tracks idle-burn (Util < 5% & Power > 50W) and zombie GPUs (Util < 5% & VRAM > 0.85). Calculates exact dollar-loss pro-rated to the millisecond.
- **NTP Time Drift Tracking:** Detects host-clock desynchronization. Drift > 50ms fires `[CRITICAL TIME DRIFT]`.
- **Async Circuit Breaker:** Protects the gRPC stream. Three failures trigger an OPEN circuit for a 30s recovery timeout.

## 📈 Validated Performance Profile
Latency was aggressively optimized by eliminating sequential HTTP JSON polling and migrating to HTTP/2 gRPC.
* **V1 Prototype (Sync HTTP):** `~80.00 ms` per loop.
* **V2 Enterprise (gRPC + Mahalanobis ML):** `~6.57 ms` per loop.
* **Result:** **91.8% Latency Reduction** with significantly higher mathematical complexity.

---

## 🚀 Live Interview Execution Manual

To demonstrate the live hardware pipeline tracking actual silicon metrics, run these three commands in **three separate native terminal windows** (Do not use Docker for the live hardware demo).

### Step 1: Start the Extract Layer (Go)
```powershell
cd telemetry-agent
go run main.go
```

### Step 2: Start the Analytics Brain (Python)
```powershell
cd accountant
python engine.py
```

### Step 3: Launch the Operations UI (React)
```powershell
cd dashboard
npm run dev
```

⚠️ **Note: Why Native Execution instead of Docker?**
During local demonstrations, running the Go Agent in Docker isolates it behind the WSL2 VM boundary, preventing access to the physical NVIDIA driver. Native execution allows the Go code to hook directly into Windows `nvml.dll`, enabling live stress-testing of the actual local GPU. (For production, the standard `docker compose up --build` deployment remains the designated cloud strategy).

### 🔥 How to Trigger a Live Anomaly (Stress Test)
To prove the Machine Learning engine works, open a 4th terminal and execute the native CUDA load generator:
```powershell
python stress_test.py
```
Watch the Operations Dashboard immediately flag the massive power/utilization spike and cross the Mahalanobis threshold.

### 💸 How to Demonstrate the Financial Waste Ledger
To prove the pro-rated financial waste accumulator works, you can force the engine into a "Zombie GPU" state (stranded memory, idle compute) using the diagnostic flag:
```powershell
python engine.py --mock-zombie
```
Watch the `Accumulated Waste` strictly increment micro-dollar fractions on every telemetry tick.
