import time
import statistics
import requests
import json

PROMETHEUS_URL = "http://localhost:9090/api/v1/query"
RATE_KWH = 0.15

# Load Pricing
try:
    with open("pricing.json", "r") as f:
        pricing_db = json.load(f)["gpus"]
except FileNotFoundError:
    pricing_db = {"default": {"hourly_cost_usd": 1.00}}

class CircuitBreaker:
    def __init__(self):
        self.state = "CLOSED"
        self.failures = 0
        self.threshold = 3
        self.last_failure_time = 0
        self.recovery_timeout = 30 

    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF-OPEN"
                print("[CIRCUIT BREAKER: HALF-OPEN] Attempting recovery...")
            else:
                raise Exception("Circuit Breaker is OPEN. Halting requests.")
        try:
            result = func(*args, **kwargs)
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

cb = CircuitBreaker()

def fetch_metric(metric_name):
    # Fetch 5-minute rolling window
    response = requests.get(f"{PROMETHEUS_URL}?query={metric_name}[5m]", timeout=5)
    response.raise_for_status()
    return response.json()["data"]["result"]

print("Starting FinOps Engine...")

while True:
    try:
        power_data = cb.call(fetch_metric, "gpu_power_draw_w")
        util_data = cb.call(fetch_metric, "gpu_utilization_percent")
        mem_used = cb.call(fetch_metric, "gpu_memory_used_mb")
        mem_total = cb.call(fetch_metric, "gpu_memory_total_mb")

        print("="*60)
        print(f"  GPU FINOPS REPORT  ({time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())})")
        print("="*60)

        for p_target in power_data:
            uuid = p_target["metric"].get("uuid", "unknown")
            # Extract power values (index 1 in the [timestamp, value] pair)
            p_values = [float(val[1]) for val in p_target["values"]]
            
            if not p_values:
                continue

            latest_power = p_values[-1]
            mean_power = statistics.mean(p_values)
            stdev = statistics.stdev(p_values) if len(p_values) > 1 else 0.0001
            stdev = stdev if stdev > 0 else 0.0001 
            z_score = (latest_power - mean_power) / stdev

            # Cost Mapping
            cost_profile = pricing_db.get(uuid, pricing_db["default"])
            burn_rate = cost_profile["hourly_cost_usd"]

            alerts = []
            if abs(z_score) > 2.0:
                alerts.append(f"[ANOMALY: Z-SCORE {z_score:+.2f}]")

            # Match corresponding utilization and memory
            latest_util = 0
            for u_target in util_data:
                if u_target["metric"].get("uuid") == uuid:
                    latest_util = float(u_target["values"][-1][1])
            
            mem_ratio = 0
            latest_used = 0
            latest_total = 1
            for mu in mem_used:
                if mu["metric"].get("uuid") == uuid:
                    latest_used = float(mu["values"][-1][1])
            for mt in mem_total:
                if mt["metric"].get("uuid") == uuid:
                    latest_total = float(mt["values"][-1][1])
            
            mem_ratio = latest_used / latest_total if latest_total > 0 else 0

            # Heuristics
            if latest_util < 5 and latest_power > 50:
                alerts.append("[WARNING: IDLE BURN DETECTED]")
            if latest_util < 5 and mem_ratio > 0.90:
                alerts.append("[CRITICAL: ZOMBIE PROCESS DETECTED - VRAM HOG]")

            alert_str = " ".join(alerts)
            print(f"[{uuid[:15]}...] Pwr: {latest_power:.1f}W | Mean: {mean_power:.1f}W | Rate: ${burn_rate:.2f}/hr | {alert_str}")

    except Exception as e:
        print(f"Engine Error: {e}")
    
    time.sleep(10)
