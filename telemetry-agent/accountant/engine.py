import time
import statistics
import json
import asyncio
import aiohttp

PROMETHEUS_URL = "http://localhost:9090/api/v1/query"
RATE_KWH = 0.15

# Load Pricing
try:
    with open("pricing.json", "r") as f:
        pricing_db = json.load(f)["gpus"]
except FileNotFoundError:
    pricing_db = {"default": {"hourly_cost_usd": 1.00}}

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

async def fetch_metric(session, metric_name):
    async with session.get(f"{PROMETHEUS_URL}?query={metric_name}[5m]", timeout=5) as response:
        response.raise_for_status()
        data = await response.json()
        return data["data"]["result"]

async def main():
    print("Starting Async FinOps Engine...")
    
    # Use a single persistent session for connection pooling
    async with aiohttp.ClientSession() as session:
        while True:
            start_time = time.perf_counter()
            try:
                # Fire all 4 queries concurrently
                results = await asyncio.gather(
                    cb.call(fetch_metric, session, "gpu_power_draw_w"),
                    cb.call(fetch_metric, session, "gpu_utilization_percent"),
                    cb.call(fetch_metric, session, "gpu_memory_used_mb"),
                    cb.call(fetch_metric, session, "gpu_memory_total_mb"),
                    return_exceptions=False 
                )
                
                power_data, util_data, mem_used, mem_total = results

                print("="*70)
                print(f"  GPU FINOPS REPORT  ({time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())})")
                print("="*70)

                for p_target in power_data:
                    uuid = p_target["metric"].get("uuid", "unknown")
                    p_values = [float(val[1]) for val in p_target["values"]]
                    
                    if not p_values:
                        continue

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

                    latest_util = next((float(u["values"][-1][1]) for u in util_data if u["metric"].get("uuid") == uuid), 0)
                    latest_used = next((float(mu["values"][-1][1]) for mu in mem_used if mu["metric"].get("uuid") == uuid), 0)
                    latest_total = next((float(mt["values"][-1][1]) for mt in mem_total if mt["metric"].get("uuid") == uuid), 1)
                    
                    mem_ratio = latest_used / latest_total if latest_total > 0 else 0

                    if latest_util < 5 and latest_power > 50:
                        alerts.append("[WARNING: IDLE BURN DETECTED]")
                    if latest_util < 5 and mem_ratio > 0.90:
                        alerts.append("[CRITICAL: ZOMBIE PROCESS DETECTED - VRAM HOG]")

                    alert_str = " ".join(alerts)
                    print(f"[{uuid[:15]}...] Pwr: {latest_power:.1f}W | Rate: ${burn_rate:.2f}/hr | {alert_str}")

                execution_time = (time.perf_counter() - start_time) * 1000
                print(f"-> Async Loop Execution Time: {execution_time:.2f} ms")

            except Exception as e:
                print(f"Engine Error: {e}")
            
            # Simulated 1s accelerated load for benchmark comparison
            await asyncio.sleep(1) 

if __name__ == "__main__":
    asyncio.run(main())
