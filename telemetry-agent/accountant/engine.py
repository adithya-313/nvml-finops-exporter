"""
accountant/engine.py – FinOps burn-rate calculator

This module queries Prometheus for the current GPU power draw,
computes an hourly cost estimate using a fixed electricity rate,
and prints a human-readable report every 10 seconds.
"""

import time
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Electricity cost in US dollars per kilowatt-hour.  Adjust this to
# match your local rate (residential ~0.10–0.30, commercial ~0.08–0.20).
RATE_KWH = 0.15

# Prometheus server URL (default port when deployed via docker-compose).
PROMETHEUS_URL = "http://localhost:9090"

# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def fetch_power_metrics():
    """
    Query Prometheus for the current gpu_power_draw_w metric.

    PromQL: gpu_power_draw_w -- returns a vector where each element
    corresponds to one time series (one per GPU).  Each element has:
      - metric["uuid"]   : label identifying the GPU
      - value[0]         : timestamp (unix float)
      - value[1]         : the actual metric value (string)

    The JSON response structure is:
    {
      "status": "success",
      "data": {
        "resultType": "vector",
        "result": [
          {
            "metric": { "uuid": "GPU-...", ... },
            "value": [ <timestamp>, "<power_watts>" ]
          }
        ]
      }
    }

    This nesting can be confusing for newcomers — we unpack it step by
    step below so the logic is easy to follow.
    """
    query_endpoint = f"{PROMETHEUS_URL}/api/v1/query"
    query_params = {"query": "gpu_power_draw_w"}

    try:
        http_response = requests.get(query_endpoint, params=query_params, timeout=10)
        http_response.raise_for_status()
    except requests.exceptions.RequestException as request_error:
        print(f"[ERROR] Could not reach Prometheus: {request_error}")
        return []

    # Parse the top-level JSON body.
    response_body = http_response.json()

    # Navigate through the nested structure:
    #   body["data"]["result"]  -->  list of time series
    data_section = response_body.get("data", {})
    result_list = data_section.get("result", [])

    extracted_metrics = []

    for element in result_list:
        # Each element has a "metric" dict (labels) and a "value" list.
        labels = element.get("metric", {})
        value_pair = element.get("value", [])

        # value_pair is [timestamp_unix_float, power_as_string]
        if len(value_pair) >= 2:
            gpu_uuid = labels.get("uuid", "unknown")
            power_watts = float(value_pair[1])  # Convert string to float
            extracted_metrics.append((gpu_uuid, power_watts))

    return extracted_metrics


def compute_burn_rate(power_watts: float) -> float:
    """
    Calculate the hourly electricity cost for a given power draw.

    Formula:  (power_watts / 1000) * RATE_KWH
    - Divide by 1000 to convert watts → kilowatts.
    - Multiply by the $/kWh rate to get dollars per hour.
    """
    kilowatts = power_watts / 1000.0
    hourly_cost = kilowatts * RATE_KWH
    return hourly_cost


def print_report(gpu_entries):
    """Print a formatted table of GPU power and burn rate."""
    print("\n" + "=" * 60)
    print(f"  GPU FINOPS REPORT  ({time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())})")
    print("=" * 60)

    if not gpu_entries:
        print("  No GPU metrics received from Prometheus.")
        print("  Verify that the agent and prometheus services are running.")
        return

    total_power = 0.0
    total_burn = 0.0

    for gpu_uuid, power_watts in gpu_entries:
        hourly_cost = compute_burn_rate(power_watts)
        total_power += power_watts
        total_burn += hourly_cost

        # Truncate the UUID to 24 chars for readability.
        short_uuid = gpu_uuid[:24] if len(gpu_uuid) > 24 else gpu_uuid
        print(f"  [{short_uuid}]  Power: {power_watts:>7.1f}W  |  "
              f"Burn Rate: ${hourly_cost:.4f}/hr")

    print("-" * 60)
    print(f"  {'TOTAL':>26s}  Power: {total_power:>7.1f}W  |  "
          f"Burn Rate: ${total_burn:.4f}/hr")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    """Run the burn-rate calculator every 10 seconds."""
    print("accountant engine started — querying Prometheus every 10s")
    print(f"Electricity rate: ${RATE_KWH}/kWh")

    while True:
        gpu_data = fetch_power_metrics()
        print_report(gpu_data)
        time.sleep(10)


if __name__ == "__main__":
    main()
