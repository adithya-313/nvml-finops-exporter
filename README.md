# NVIDIA GPU Telemetry & FinOps Pipeline

A real-time distributed pipeline tracking high-frequency NVIDIA GPU metrics, multi-variate statistical anomalies, clock desynchronization, and structural financial losses.

## 🚀 Instant Local Execution Manual

Follow these steps exactly in three separate terminal windows to demonstrate the live hardware pipeline:

### Step 1: Start the Go Telemetry Agent (Native Hardware Layer)
```powershell
cd telemetry-agent
go run main.go
```
Listens on port `:50051`. Queries native `nvml.dll` system calls.

### Step 2: Start the FinOps Analytics Engine (Machine Learning Layer)
```powershell
cd accountant
pip install -r requirements.txt
python engine.py
```
Maintains a sliding 4D vector history, computes Mahalanobis distance, and flags dynamic resource waste.

### Step 3: Launch the Operations Console (Visualization Layer)
```powershell
cd dashboard
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) to track streaming indicators and active alert states.
