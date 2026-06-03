import os
import time
import statistics
import json
import asyncio
import sys
from collections import deque

import grpc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pb"))
import telemetry_pb2
import telemetry_pb2_grpc

RATE_KWH = 0.15

# Load Pricing
try:
    with open(os.path.join(os.path.dirname(__file__), "pricing.json"), "r") as f:
        pricing_db = json.load(f)["gpus"]
except FileNotFoundError:
    pricing_db = {"default": {"hourly_cost_usd": 1.00}}

# GPU history: uuid -> deque of power values (maxlen=300 = 5min @ 1s)
gpu_history: dict = {}

class AsyncCircuitBreaker:
    def __init__(self):
        self.state = "CLOSED"
        self.failures = 0
        self.threshold = 3
        self.last_failure_time = 0
        self.recovery_timeout = 30

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

cb = AsyncCircuitBreaker()

async def fetch_metrics(stub):
    return await stub.GetMetrics(telemetry_pb2.TelemetryRequest(), timeout=2.0)

async def main():
    print("Starting gRPC FinOps Engine...")

    async with grpc.aio.insecure_channel("localhost:50051") as channel:
        stub = telemetry_pb2_grpc.GpuTelemetryStub(channel)
        while True:
            start_time = time.perf_counter()
            try:
                response = await cb.call(fetch_metrics, stub)

                print("=" * 70)
                print(f"  GPU FINOPS REPORT  ({time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())})")
                print("=" * 70)

                for gpu in response.gpus:
                    uuid = gpu.uuid

                    # Maintain rolling deque for power stats
                    if uuid not in gpu_history:
                        gpu_history[uuid] = deque(maxlen=300)
                    gpu_history[uuid].append(gpu.power_draw_w)

                    p_values = list(gpu_history[uuid])
                    latest_power = p_values[-1]
                    mean_power = statistics.mean(p_values)
                    stdev = statistics.stdev(p_values) if len(p_values) > 1 else 0.0001
                    stdev = stdev if stdev > 0 else 0.0001
                    z_score = (latest_power - mean_power) / stdev

                    cost_profile = pricing_db.get(uuid, pricing_db["default"])
                    burn_rate = cost_profile["hourly_cost_usd"]

                    alerts = []
                    if abs(z_score) > 2.0:
                        alerts.append(f"[ANOMALY: Z-SCORE {z_score:+.2f}]")

                    latest_util = gpu.utilization_percent
                    mem_ratio = gpu.memory_used_mb / gpu.memory_total_mb if gpu.memory_total_mb > 0 else 0

                    if latest_util < 5 and latest_power > 50:
                        alerts.append("[WARNING: IDLE BURN DETECTED]")
                    if latest_util < 5 and mem_ratio > 0.90:
                        alerts.append("[CRITICAL: ZOMBIE PROCESS DETECTED - VRAM HOG]")

                    alert_str = " ".join(alerts)
                    print(f"[{uuid[:15]}...] Pwr: {latest_power:.1f}W | Util: {latest_util:.0f}% | Mem: {gpu.memory_used_mb:.0f}/{gpu.memory_total_mb:.0f} MiB | Rate: ${burn_rate:.2f}/hr | {alert_str}")

                ntp_offset = response.ntp_offset_ms
                if abs(ntp_offset) > 50:
                    print(f"[CRITICAL TIME DRIFT] Host clock desynchronized by {ntp_offset}ms. Time-series math hazard.")

                execution_time = (time.perf_counter() - start_time) * 1000
                print(f"-> gRPC Loop Execution Time: {execution_time:.2f} ms  |  NTP offset: {ntp_offset} ms")

            except Exception as e:
                print(f"Engine Error: {e}")

            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
