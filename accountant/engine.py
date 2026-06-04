import os
import time
import json
import asyncio
import sys
from collections import deque
from typing import Dict, Any

import numpy as np
from scipy.spatial.distance import mahalanobis

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pb"))
import telemetry_pb2
import telemetry_pb2_grpc

# ---------------------------------------------------------------------------
# Pricing configuration with graceful degradation
# ---------------------------------------------------------------------------
DEFAULT_HOURLY_COST_USD: float = 1.00
RATE_KWH: float = 0.15

_pricing_json_path: str = os.path.join(os.path.dirname(__file__), "pricing.json")

try:
    with open(_pricing_json_path, "r", encoding="utf-8") as _f:
        _raw: Any = json.load(_f)
        if not isinstance(_raw, dict):
            raise ValueError("pricing.json schema invalid: expected flat dict")
        pricing_db: Dict[str, float] = _raw
except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError) as _exc:
    print(f"[WARN] pricing.json load failed ({_exc}); defaulting to ${DEFAULT_HOURLY_COST_USD:.2f}/hr")
    pricing_db = {"DEFAULT": DEFAULT_HOURLY_COST_USD}

# ---------------------------------------------------------------------------
# Alert thresholds — authoritative constants
# ---------------------------------------------------------------------------
MAHALANOBIS_CRITICAL_THRESHOLD: float = 3.5
IDLE_BURN_UTIL_CEIL: float = 5.0       # percent
IDLE_BURN_POWER_FLOOR: float = 50.0    # watts
ZOMBIE_UTIL_CEIL: float = 5.0          # percent
ZOMBIE_VRAM_RATIO_FLOOR: float = 0.85
HIGH_TEMP_CEIL: float = 78.0           # degrees Celsius
NTP_DRIFT_CEIL_MS: float = 50.0        # milliseconds

# ---------------------------------------------------------------------------
# Per-GPU sliding feature-vector history
# maxlen=300 ≈ 5 min @ 1 sample/s
# ---------------------------------------------------------------------------
CALIBRATION_SAMPLES: int = 50

gpu_history: Dict[str, deque] = {}

# ---------------------------------------------------------------------------
# Cumulative waste ledger (in-memory, persistent across ticks)
# ---------------------------------------------------------------------------
total_wasted_usd: float = 0.0

# ---------------------------------------------------------------------------
# Diagnostic presentation toggle
# ---------------------------------------------------------------------------
MOCK_ZOMBIE_MODE: bool = "--mock-zombie" in sys.argv


# ---------------------------------------------------------------------------
# Async Circuit Breaker
# ---------------------------------------------------------------------------
class AsyncCircuitBreaker:
    """Three-state circuit breaker wrapping async callables."""

    def __init__(self) -> None:
        self.state: str = "CLOSED"
        self.failures: int = 0
        self.threshold: int = 3
        self.last_failure_time: float = 0.0
        self.recovery_timeout: int = 30

    async def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF-OPEN"
                print("[CIRCUIT BREAKER: HALF-OPEN] Attempting recovery...")
            else:
                raise Exception("Circuit Breaker is OPEN. Halting requests.")
        try:
            result = await func(*args, **kwargs)
            if self.state == "HALF-OPEN":
                self.state = "CLOSED"
                self.failures = 0
                print("[CIRCUIT BREAKER: CLOSED] System recovered.")
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.threshold:
                self.state = "OPEN"
                print(f"[CIRCUIT BREAKER: TRIPPED TO OPEN] Failures exceeded {self.threshold}.")
            raise e


cb: AsyncCircuitBreaker = AsyncCircuitBreaker()


async def fetch_metrics(stub: telemetry_pb2_grpc.GpuTelemetryStub):
    """Single RPC call with a hard 2-second deadline."""
    return await stub.GetMetrics(telemetry_pb2.TelemetryRequest(), timeout=2.0)


# ---------------------------------------------------------------------------
# Main telemetry loop
# ---------------------------------------------------------------------------
async def main() -> None:
    global total_wasted_usd

    print("Starting gRPC FinOps Engine (Mahalanobis)...")

    if MOCK_ZOMBIE_MODE:
        print("\033[93m" + "=" * 70)
        print("[DIAGNOSTIC MODE ACTIVE: FORCING ZOMBIE GPU STATE FOR LEDGER DEMONSTRATION]")
        print("=" * 70 + "\033[0m")

    # Track wall-clock between ticks for pro-rated billing
    last_tick_time: float = time.perf_counter()

    async with grpc.aio.insecure_channel("localhost:50051") as channel:
        stub = telemetry_pb2_grpc.GpuTelemetryStub(channel)

        while True:
            tick_start: float = time.perf_counter()
            elapsed_since_last_tick: float = tick_start - last_tick_time
            last_tick_time = tick_start

            try:
                response = await cb.call(fetch_metrics, stub)

                print("=" * 70)
                print(f"  GPU FINOPS REPORT  ({time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())})")
                print("=" * 70)

                for gpu in response.gpus:
                    uuid: str = gpu.uuid

                    # --mock-zombie override: force zombie GPU metrics for demo
                    if MOCK_ZOMBIE_MODE:
                        gpu.utilization_percent = 2.0
                        gpu.memory_used_mb = int(gpu.memory_total_mb * 0.95)

                    mem_ratio: float = (
                        gpu.memory_used_mb / gpu.memory_total_mb
                        if gpu.memory_total_mb > 0
                        else 0.0
                    )
                    feature_vector: list[float] = [
                        gpu.utilization_percent,
                        mem_ratio,
                        gpu.temperature_c,
                        gpu.power_draw_w,
                    ]

                    # ----- sliding window bookkeeping -----
                    if uuid not in gpu_history:
                        gpu_history[uuid] = deque(maxlen=300)
                    gpu_history[uuid].append(feature_vector)

                    # ----- pricing lookup (substring matching) -----
                    gpu_name_lower: str = gpu.name.lower()
                    burn_rate: float = DEFAULT_HOURLY_COST_USD
                    for _key, _rate in pricing_db.items():
                        if _key.lower() in gpu_name_lower:
                            burn_rate = _rate
                            break

                    # ----- alert evaluation (all thresholds, every tick) -----
                    alerts: list[str] = []
                    d_m_display: str = "N/A"

                    latest_util: float = gpu.utilization_percent
                    latest_power: float = gpu.power_draw_w
                    latest_temp: float = gpu.temperature_c

                    # --- Mahalanobis anomaly detection ---
                    n: int = len(gpu_history[uuid])
                    if n < CALIBRATION_SAMPLES:
                        alerts.append(
                            f"[CALIBRATING: Gathering Baseline Data... ({n}/{CALIBRATION_SAMPLES})]"
                        )
                    else:
                        arr: np.ndarray = np.array(gpu_history[uuid])
                        mean_vec: np.ndarray = np.mean(arr, axis=0)
                        cov: np.ndarray = np.cov(arr, rowvar=False)
                        cov_pinv: np.ndarray = np.linalg.pinv(cov)
                        x: np.ndarray = np.array(feature_vector)
                        d_m: float = float(mahalanobis(x, mean_vec, cov_pinv))
                        d_m_display = f"{d_m:.2f}"

                        if d_m > MAHALANOBIS_CRITICAL_THRESHOLD:
                            alerts.append(
                                f"[CRITICAL ANOMALY: MULTI-VARIATE DEVIATION (D_M={d_m:.2f})]"
                            )

                    # --- Idle-burn condition ---
                    is_idle_burn: bool = (
                        latest_util < IDLE_BURN_UTIL_CEIL
                        and latest_power > IDLE_BURN_POWER_FLOOR
                    )
                    if is_idle_burn:
                        alerts.append("[ALERT: IDLE-BURN CONDITION]")

                    # --- Zombie GPU detection ---
                    is_zombie: bool = (
                        latest_util < ZOMBIE_UTIL_CEIL
                        and mem_ratio > ZOMBIE_VRAM_RATIO_FLOOR
                    )
                    if is_zombie:
                        alerts.append("[ALERT: ZOMBIE GPU DETECTED]")

                    # --- High temperature warning ---
                    if latest_temp > HIGH_TEMP_CEIL:
                        alerts.append("[ALERT: HIGH TEMPERATURE WARNING]")

                    # ----- cumulative waste accounting -----
                    if is_idle_burn or is_zombie:
                        # Pro-rate the hourly cost to the exact elapsed interval
                        tick_cost_usd: float = burn_rate * (elapsed_since_last_tick / 3600.0)
                        total_wasted_usd += tick_cost_usd

                    # ----- console output -----
                    alert_str: str = " | ".join(alerts) if alerts else "OK"
                    print(
                        f"[{uuid[:15]}...] "
                        f"Pwr: {latest_power:.1f}W | "
                        f"Util: {latest_util:.0f}% | "
                        f"Temp: {latest_temp:.0f}C | "
                        f"Mem Ratio: {mem_ratio:.2f} | "
                        f"Rate: ${burn_rate:.2f}/hr | "
                        f"Accumulated Waste: ${total_wasted_usd:.6f} | "
                        f"[D_M={d_m_display}]"
                    )
                    if alerts:
                        for a in alerts:
                            print(f"  >> {a}")

                # ----- NTP time drift evaluation -----
                ntp_offset: float = response.ntp_offset_ms
                if abs(ntp_offset) > NTP_DRIFT_CEIL_MS:
                    print(
                        f"[CRITICAL TIME DRIFT] Host clock desynchronized by "
                        f"{ntp_offset}ms. Time-series math hazard."
                    )

                loop_time_ms: float = (time.perf_counter() - tick_start) * 1000
                print(
                    f"-> V2 Loop Execution Time (gRPC + Mahalanobis): "
                    f"{loop_time_ms:.2f} ms  |  NTP offset: {ntp_offset} ms"
                )

            except Exception as e:
                print(f"Engine Error: {e}")

            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
