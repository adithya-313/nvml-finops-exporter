"""
accountant/engine.py – FinOps burn-rate calculator with statistical alerts

Queries Prometheus for the last 5 minutes of GPU power and utilization
data, computes hourly cost estimates, detects idle-burn conditions, and
flags statistical anomalies (power spikes) using Z-score analysis.
"""

import time
import statistics
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

# ---------------------------------------------------------------------------
# Prometheus query helpers
# ---------------------------------------------------------------------------

def fetch_range_vector(metric_name: str):
    """
    Query Prometheus for a range vector of *metric_name* over the
    last WINDOW_MINUTES.

    PromQL example:  gpu_power_draw_w[5m]

    The response "resultType" will be "matrix".  Each element in the
    "result" array has:

        {
          "metric": { "uuid": "GPU-...", ... },
          "values": [
            [ <unix_timestamp>, "<string_value>" ],   ← newest
            [ <unix_timestamp>, "<string_value>" ],   ← oldest
            ...
          ]
        }

    NOTE: *values* is ordered newest-first (Prometheus default).
    We reverse it below so the caller gets chronological order.

    Returns a dict:  { uuid: [ (timestamp, float_value), ... ], ... }
    """
    endpoint = f"{PROMETHEUS_URL}/api/v1/query"
    query_string = f"{metric_name}[{WINDOW_MINUTES}m]"
    params = {"query": query_string}

    try:
        http_response = requests.get(endpoint, params=params, timeout=10)
        http_response.raise_for_status()
    except requests.exceptions.RequestException as request_error:
        print(f"[ERROR] Could not reach Prometheus: {request_error}")
        return {}

    body = http_response.json()

    # Navigate the nested JSON: body -> data -> result
    data_section = body.get("data", {})
    result_list = data_section.get("result", [])

    series_by_uuid = {}

    for element in result_list:
        labels = element.get("metric", {})
        gpu_uuid = labels.get("uuid", "unknown")

        # "values" is a list of [timestamp, value_string] pairs,
        # returned newest-first by Prometheus.
        raw_values = element.get("values", [])

        # Convert each pair to (timestamp, float) and reverse so
        # the list goes from oldest to newest (chronological).
        parsed = []
        for pair in raw_values:
            if len(pair) >= 2:
                ts = float(pair[0])
                val = float(pair[1])
                parsed.append((ts, val))

        # Reverse from newest-first to chronological order.
        parsed.reverse()
        series_by_uuid[gpu_uuid] = parsed

    return series_by_uuid


def fetch_scalar(metric_name: str):
    """
    Fetch the single most-recent value of *metric_name* (instant vector).

    Returns a dict:  { uuid: latest_float_value, ... }
    """
    endpoint = f"{PROMETHEUS_URL}/api/v1/query"
    params = {"query": metric_name}

    try:
        http_response = requests.get(endpoint, params=params, timeout=10)
        http_response.raise_for_status()
    except requests.exceptions.RequestException as request_error:
        print(f"[ERROR] Could not reach Prometheus: {request_error}")
        return {}

    body = http_response.json()
    data_section = body.get("data", {})
    result_list = data_section.get("result", [])

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
    """
    Given a list of power readings (floats), calculate:
      - mean         (average power over the window)
      - stdev        (population standard deviation)
      - z_score      ((latest_power - mean) / stdev)

    Safeguard: if there is only one data point or stdev == 0, set
    stdev to 0.0001 so we never divide by zero.
    """
    if len(power_values) < 2:
        # Not enough data points for a meaningful stdev.
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

    latest_power = power_values[-1]
    z_score = (latest_power - mean) / stdev

    return {
        "mean": mean,
        "stdev": stdev,
        "z_score": z_score,
    }


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------

def compute_burn_rate(power_watts: float) -> float:
    """
    Hourly electricity cost:  (watts / 1000) * rate_per_kwh
    """
    kilowatts = power_watts / 1000.0
    return kilowatts * RATE_KWH


# ---------------------------------------------------------------------------
# Alert detection
# ---------------------------------------------------------------------------

def check_idle_burn(utilization_pct: float, power_watts: float):
    """
    Flag a warning if the GPU is barely utilised but still drawing
    significant power — a sign that the card is stuck in a high-
    power P-state when it should have idled down.
    """
    if utilization_pct < 5.0 and power_watts > 50.0:
        return "[WARNING: IDLE BURN DETECTED]"
    return ""


def check_power_anomaly(z_score: float):
    """
    Flag an anomaly when the absolute Z-score exceeds 2.0 (roughly
    95th percentile under a normal distribution).
    """
    if abs(z_score) > 2.0:
        direction = "SPIKE" if z_score > 0 else "DIP"
        return f"[ANOMALY: POWER {direction}]"
    return ""


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(power_series, util_latest):
    """
    Print a formatted table with per-GPU statistics, burn rates,
    and any triggered alerts.
    """
    print("\n" + "=" * 72)
    print(f"  GPU FINOPS REPORT  ({time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())})")
    print("=" * 72)

    if not power_series:
        print("  No GPU metrics received from Prometheus.")
        print("  Verify that the agent and prometheus services are running.")
        return

    # Column header
    print(f"  {'GPU UUID':<28s} {'Latest':>7s} {'Mean':>7s} {'Z-Score':>8s} "
          f"{'Burn $/hr':>10s}  Alerts")
    print("  " + "-" * 72)

    total_power = 0.0
    total_burn = 0.0

    # Iterate over each GPU uuid that has power data.
    for gpu_uuid in sorted(power_series.keys()):
        points = power_series[gpu_uuid]
        if not points:
            continue

        # Extract just the power values (ignore timestamps for stats).
        power_only = [val for (_, val) in points]
        latest_power = power_only[-1]
        stats = compute_statistics(power_only)

        # Get the latest utilization for idle-burn detection.
        latest_util = util_latest.get(gpu_uuid, 0.0)

        # Build alert strings.
        idle_alert = check_idle_burn(latest_util, latest_power)
        anomaly_alert = check_power_anomaly(stats["z_score"])

        alerts = []
        if idle_alert:
            alerts.append(idle_alert)
        if anomaly_alert:
            alerts.append(anomaly_alert)
        alert_text = "  ".join(alerts) if alerts else ""

        hourly_cost = compute_burn_rate(latest_power)
        total_power += latest_power
        total_burn += hourly_cost

        short_uuid = gpu_uuid[:24] if len(gpu_uuid) > 24 else gpu_uuid

        print(f"  {short_uuid:<28s} {latest_power:>7.1f} "
              f"{stats['mean']:>7.1f} {stats['z_score']:>+7.2f} "
              f"${hourly_cost:<7.4f}  {alert_text}")

    print("  " + "-" * 72)
    total_burn_rate = compute_burn_rate(total_power)
    print(f"  {'TOTAL':<28s} {total_power:>7.1f} {'':>7s} {'':>8s} "
          f"${total_burn_rate:<7.4f}")
    print("=" * 72)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    """
    Run one iteration of the accountant engine: fetch data, compute
    stats, print report, and exit.  (The calling shell or scheduler
    is responsible for looping if needed.)
    """
    print(f"accountant engine — querying Prometheus at {PROMETHEUS_URL}")
    print(f"  Electricity rate : ${RATE_KWH}/kWh")
    print(f"  Analysis window  : {WINDOW_MINUTES} minutes")
    print()

    # Fetch range vectors for both power and utilisation.
    power_series = fetch_range_vector("gpu_power_draw_w")
    util_series = fetch_range_vector("gpu_utilization_percent")

    # For idle-burn detection we only need the latest utilisation
    # value.  Grabbing the last point from each uuid's time series.
    util_latest = {}
    for uuid_key, points in util_series.items():
        if points:
            util_latest[uuid_key] = points[-1][1]  # (ts, val) -> val

    print_report(power_series, util_latest)


if __name__ == "__main__":
    main()
