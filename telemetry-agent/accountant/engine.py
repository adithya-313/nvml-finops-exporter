"""
accountant/engine.py – FinOps burn-rate calculator with statistical alerts

Queries Prometheus for the last 5 minutes of GPU power and utilization
data, computes hourly cost estimates, detects idle-burn conditions, and
flags statistical anomalies (power spikes) using Z-score analysis.
"""

import json
import math
import os
import statistics
import time

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Electricity cost in US dollars per kilowatt-hour.
RATE_KWH = 0.15

# Prometheus server URL (default port when deployed via docker-compose).
PROMETHEUS_URL = "http://localhost:9090"

# Scrape window: how many minutes of history to fetch for statistics.
WINDOW_MINUTES = 5

# Path to the static pricing database.
PRICING_FILE = os.path.join(os.path.dirname(__file__), "pricing.json")

# ---------------------------------------------------------------------------
# Pricing injection – load the static cost database
# ---------------------------------------------------------------------------

def load_pricing():
    """
    Read pricing.json and return two lookup helpers:
      - pricing_data : raw dict (keys = GPU UUIDs + "default")
      - lookup_cost(uuid) -> float
      - lookup_model(uuid) -> str
    """
    try:
        with open(PRICING_FILE, "r", encoding="utf-8") as file_handle:
            pricing_data = json.load(file_handle).get("gpus", {})
    except (FileNotFoundError, json.JSONDecodeError) as load_error:
        print(f"[WARN] Could not load {PRICING_FILE}: {load_error}")
        pricing_data = {"default": {"model": "Unknown GPU", "hourly_cost_usd": 1.00}}

    def lookup_cost(gpu_uuid: str) -> float:
        """Return the hourly cost for *gpu_uuid*, falling back to default."""
        entry = pricing_data.get(gpu_uuid, pricing_data.get("default", {}))
        return float(entry.get("hourly_cost_usd", 1.00))

    def lookup_model(gpu_uuid: str) -> str:
        """Return the GPU model name, falling back to default."""
        entry = pricing_data.get(gpu_uuid, pricing_data.get("default", {}))
        return str(entry.get("model", "Unknown GPU"))

    return pricing_data, lookup_cost, lookup_model


PRICING_DATA, LOOKUP_COST, LOOKUP_MODEL = load_pricing()


# ---------------------------------------------------------------------------
# Circuit Breaker – protects downstream (Prometheus) from cascading failures
#
# State machine:
#   CLOSED  ──(failure_count >= threshold)──▶  OPEN
#   OPEN    ──(recovery_timeout elapsed)───▶  HALF_OPEN
#   HALF_OPEN ──(probe succeeds)──────────▶  CLOSED
#   HALF_OPEN ──(probe fails)─────────────▶  OPEN  (timer reset)
#
# Exponential backoff when OPEN:
#   wait = recovery_timeout * (2 ** failure_count)  capped at 300 s
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """
    Implements the circuit-breaker pattern so that repeated Prometheus
    failures do not hammer the network stack.  The breaker transitions
    between CLOSED, OPEN, and HALF_OPEN based on consecutive failures.
    """

    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 30):
        self.state = "CLOSED"            # Initial state: normal operation.
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout  # seconds before HALF_OPEN
        self.last_failure_time = 0.0

    # ------------------------------------------------------------------
    # Backoff calculator
    # ------------------------------------------------------------------

    def backoff_seconds(self) -> float:
        """
        Exponential backoff: doubles the base recovery_timeout for
        each failure beyond the threshold, capped at 5 minutes.
            wait = recovery_timeout * (2 ** excess_failures)
        """
        excess = max(0, self.failure_count - self.failure_threshold + 1)
        wait = self.recovery_timeout * (2 ** excess)
        return min(wait, 300.0)

    # ------------------------------------------------------------------
    # Core guard method
    # ------------------------------------------------------------------

    def call(self, func, *args, **kwargs):
        """
        Execute *func* through the breaker.

        Returns (result, error_string).  *error_string* is None on
        success; on failure it contains the reason the call was
        blocked or the exception message.
        """
        now = time.time()

        # ── OPEN state ──────────────────────────────────────────────
        # Reject requests immediately unless the recovery timeout has
        # elapsed, in which case transition to HALF_OPEN for a probe.
        if self.state == "OPEN":
            elapsed_since_failure = now - self.last_failure_time
            if elapsed_since_failure < self.recovery_timeout:
                backoff = self.backoff_seconds()
                message = (
                    f"[CIRCUIT BREAKER: TRIPPED TO OPEN] "
                    f"retry in {backoff:.0f}s "
                    f"(failure_count={self.failure_count})"
                )
                return None, message
            # Timeout elapsed – allow one probe (HALF_OPEN).
            self.state = "HALF_OPEN"
            print(f"[CIRCUIT BREAKER: HALF_OPEN] "
                  f"allowing probe request after {elapsed_since_failure:.0f}s")

        # ── CLOSED / HALF_OPEN ── execute the wrapped function ─────
        try:
            result = func(*args, **kwargs)
        except requests.exceptions.RequestException as call_error:
            self.failure_count += 1
            self.last_failure_time = time.time()

            # Trip to OPEN if we cross the threshold.
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                print(f"[CIRCUIT BREAKER: TRIPPED TO OPEN] "
                      f"{self.failure_count} consecutive failures")

            return None, str(call_error)

        # Success resets the breaker.
        if self.state == "HALF_OPEN":
            print("[CIRCUIT BREAKER: CLOSED] probe succeeded, breaker reset")
        self.state = "CLOSED"
        self.failure_count = 0
        return result, None


# Global circuit-breaker instance shared by all fetch helpers.
BREAKER = CircuitBreaker(failure_threshold=3, recovery_timeout=30)


# ---------------------------------------------------------------------------
# Wasted-spend tracker
#
# When a GPU's utilisation drops to 0 % we record the time; if it
# stays idle for more than 10 minutes (600 s) we compute the cost
# of the wasted (paid-for but unused) capacity.
# ---------------------------------------------------------------------------

# Map GPU UUID → timestamp when utilisation first hit 0 %.
_idle_start_time: dict = {}


def update_wasted_tracker(gpu_uuid: str, utilization_pct: float):
    """
    Maintain the idle-start clock for *gpu_uuid*.
    Call this once per report cycle for each GPU.
    """
    if utilization_pct == 0.0:
        # GPU is idle – start the clock if not already running.
        if gpu_uuid not in _idle_start_time:
            _idle_start_time[gpu_uuid] = time.time()
    else:
        # GPU is active – clear the idle marker.
        _idle_start_time.pop(gpu_uuid, None)


def compute_wasted_spend(gpu_uuid: str) -> dict:
    """
    If the GPU has been idle for more than 10 minutes, calculate the
    dollar amount wasted.

    Returns {"wasted_spend": float, "idle_seconds": int} or None.
    """
    start_ts = _idle_start_time.get(gpu_uuid)
    if start_ts is None:
        return None

    elapsed = time.time() - start_ts
    if elapsed < 600:  # Less than 10 minutes – not yet billable.
        return {"wasted_spend": 0.0, "idle_seconds": int(elapsed)}

    hourly_cost = LOOKUP_COST(gpu_uuid)
    wasted = hourly_cost * (elapsed / 3600.0)
    return {"wasted_spend": wasted, "idle_seconds": int(elapsed)}


# ---------------------------------------------------------------------------
# Prometheus query helpers
# ---------------------------------------------------------------------------

def _do_fetch_range_vector(metric_name: str):
    """
    Raw HTTP call (no circuit breaker) – used internally by
    fetch_range_vector which routes through the breaker.
    """
    endpoint = f"{PROMETHEUS_URL}/api/v1/query"
    query_string = f"{metric_name}[{WINDOW_MINUTES}m]"
    params = {"query": query_string}

    http_response = requests.get(endpoint, params=params, timeout=10)
    http_response.raise_for_status()
    return http_response.json()


def fetch_range_vector(metric_name: str):
    """
    Fetch a range vector through the circuit breaker.

    Returns the parsed { uuid: [ (ts, val), ... ] } dict on success,
    or an empty dict when the breaker is open or the call fails.
    """
    body, error = BREAKER.call(_do_fetch_range_vector, metric_name)
    if error is not None:
        print(f"[FETCH] {error}")
        return {}

    data_section = body.get("data", {})
    result_list = data_section.get("result", [])

    series_by_uuid = {}
    for element in result_list:
        labels = element.get("metric", {})
        gpu_uuid = labels.get("uuid", "unknown")
        raw_values = element.get("values", [])

        parsed = []
        for pair in raw_values:
            if len(pair) >= 2:
                parsed.append((float(pair[0]), float(pair[1])))

        parsed.reverse()
        series_by_uuid[gpu_uuid] = parsed

    return series_by_uuid


def _do_fetch_scalar(metric_name: str):
    """Raw instant-vector fetch (used through the breaker)."""
    endpoint = f"{PROMETHEUS_URL}/api/v1/query"
    params = {"query": metric_name}
    http_response = requests.get(endpoint, params=params, timeout=10)
    http_response.raise_for_status()
    return http_response.json()


def fetch_scalar(metric_name: str):
    """
    Fetch a single latest value per GPU through the circuit breaker.
    """
    body, error = BREAKER.call(_do_fetch_scalar, metric_name)
    if error is not None:
        return {}

    data_section = body.get("data", {})
    result_list = data_section.get("result", {})

    latest = {}
    for element in result_list:
        labels = element.get("metric", {})
        gpu_uuid = labels.get("uuid", "unknown")
        value_pair = element.get("value", [])
        if len(value_pair) >= 2:
            latest[gpu_uuid] = float(value_pair[1])

    return latest


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------

def compute_statistics(power_values: list):
    """Mean, stdev, and Z-score for the most recent power value."""
    if len(power_values) < 2:
        return {
            "mean": power_values[-1] if power_values else 0.0,
            "stdev": 0.0001,
            "z_score": 0.0,
        }

    mean = statistics.mean(power_values)
    try:
        stdev = statistics.stdev(power_values)
    except statistics.StatisticsError:
        stdev = 0.0001

    if stdev == 0.0:
        stdev = 0.0001

    z_score = (power_values[-1] - mean) / stdev

    return {"mean": mean, "stdev": stdev, "z_score": z_score}


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------

def compute_burn_rate(power_watts: float) -> float:
    """Hourly electricity cost: (watts / 1000) * rate_per_kwh."""
    kilowatts = power_watts / 1000.0
    return kilowatts * RATE_KWH


# ---------------------------------------------------------------------------
# Alert detection
# ---------------------------------------------------------------------------

def check_idle_burn(utilization_pct: float, power_watts: float) -> str:
    """Flag when the GPU is barely utilised but drawing significant power."""
    if utilization_pct < 5.0 and power_watts > 50.0:
        return "[WARNING: IDLE BURN DETECTED]"
    return ""


def check_power_anomaly(z_score: float) -> str:
    """Flag when the latest power draw is a statistical outlier (|Z| > 2)."""
    if abs(z_score) > 2.0:
        direction = "SPIKE" if z_score > 0 else "DIP"
        return f"[ANOMALY: POWER {direction}]"
    return ""


def check_zombie(utilization_pct: float, mem_used_mb: float, mem_total_mb: float) -> str:
    """
    Flag when a GPU is near-idle (< 5% util) but has nearly all of its
    VRAM allocated (> 90%).  This is a strong indicator of a leaked /
    abandoned process that never released its memory.
    """
    if mem_total_mb <= 0:
        return ""
    mem_ratio = mem_used_mb / mem_total_mb
    if utilization_pct < 5.0 and mem_ratio > 0.90:
        return "[CRITICAL: ZOMBIE PROCESS DETECTED - VRAM HOG]"
    return ""


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(power_series, util_latest, mem_series):
    """
    Print a formatted table with per-GPU pricing, burn rates,
    wasted-spend, zombie detection, and Z-score alerts.
    """
    print("\n" + "=" * 88)
    print(f"  GPU FINOPS REPORT  ({time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())})")
    print("=" * 88)

    if not power_series:
        print("  No GPU metrics received from Prometheus.")
        print("  Verify that the agent and prometheus services are running.")
        return

    header = (
        f"  {'GPU UUID':<26s} {'Power':>6s} {'Util':>5s} "
        f"{'Model':<32s} {'Burn $/hr':>10s}  Alerts"
    )
    print(header)
    print("  " + "-" * 88)

    total_power = 0.0
    total_burn = 0.0

    for gpu_uuid in sorted(power_series.keys()):
        points = power_series[gpu_uuid]
        if not points:
            continue

        power_only = [val for (_, val) in points]
        latest_power = power_only[0]
        stats = compute_statistics(power_only)
        latest_util = util_latest.get(gpu_uuid, 0.0)

        # ── Pricing ────────────────────────────────────────────────
        gpu_model = LOOKUP_MODEL(gpu_uuid)
        hourly_instance_cost = LOOKUP_COST(gpu_uuid)

        # ── Wasted-spend tracker ───────────────────────────────────
        update_wasted_tracker(gpu_uuid, latest_util)
        waste_info = compute_wasted_spend(gpu_uuid)

        # ── Memory for zombie detection ────────────────────────────
        mem_points = mem_series.get(gpu_uuid, [])
        latest_mem_used = 0.0
        latest_mem_total = 1.0
        if mem_points:
            latest_mem_used = mem_points[0][1]
        mem_total_points = fetch_range_vector("gpu_memory_total_mb").get(gpu_uuid, [])
        if mem_total_points:
            latest_mem_total = mem_total_points[0][1]

        # ── Build alert strings ────────────────────────────────────
        idle_alert = check_idle_burn(latest_util, latest_power)
        anomaly_alert = check_power_anomaly(stats["z_score"])
        zombie_alert = check_zombie(latest_util, latest_mem_used, latest_mem_total)

        alerts = []
        if idle_alert:
            alerts.append(idle_alert)
        if anomaly_alert:
            alerts.append(anomaly_alert)
        if zombie_alert:
            alerts.append(zombie_alert)
        if waste_info and waste_info["wasted_spend"] > 0:
            alerts.append(f"[WASTE: ${waste_info['wasted_spend']:.4f}]")

        alert_text = "  ".join(alerts) if alerts else ""

        hourly_cost = compute_burn_rate(latest_power)

        # Add instance cost to total burn for the FinOps view.
        total_power += latest_power
        total_burn += hourly_cost + hourly_instance_cost

        short_uuid = gpu_uuid[:24] if len(gpu_uuid) > 24 else gpu_uuid
        short_model = gpu_model[:30] if len(gpu_model) > 30 else gpu_model

        print(
            f"  {short_uuid:<26s} {latest_power:>6.1f} "
            f"{latest_util:>4.0f}% "
            f"{short_model:<32s} "
            f"${hourly_cost:<7.4f}  {alert_text}"
        )

    print("  " + "-" * 88)
    total_burn_rate = compute_burn_rate(total_power)
    print(f"  {'TOTAL':<26s} {total_power:>6.1f} {'':>5s} "
          f"{'':<32s} ${total_burn_rate:<7.4f}")
    print("=" * 88)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    """Run one iteration of the accountant engine."""
    print(f"accountant engine — querying Prometheus at {PROMETHEUS_URL}")
    print(f"  Electricity rate    : ${RATE_KWH}/kWh")
    print(f"  Analysis window     : {WINDOW_MINUTES} minutes")
    print(f"  Circuit Breaker     : threshold={BREAKER.failure_threshold}, "
          f"recovery={BREAKER.recovery_timeout}s")
    print(f"  Pricing entries     : {len(PRICING_DATA)} GPU profiles loaded")
    print()

    power_series = fetch_range_vector("gpu_power_draw_w")
    util_series = fetch_range_vector("gpu_utilization_percent")
    mem_series = fetch_range_vector("gpu_memory_used_mb")

    util_latest = {}
    for uuid_key, points in util_series.items():
        if points:
            util_latest[uuid_key] = points[0][1]

    print_report(power_series, util_latest, mem_series)

    # Print any active circuit-breaker state at the end.
    if BREAKER.state != "CLOSED":
        print(f"\n  [CIRCUIT BREAKER STATE: {BREAKER.state}]")


if __name__ == "__main__":
    main()
