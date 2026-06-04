import os
import time
import json
import sys
import asyncio
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from sklearn.ensemble import IsolationForest
import nats
import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pb"))
import telemetry_pb2

RATE_KWH = 0.15

try:
    with open(os.path.join(os.path.dirname(__file__), "pricing.json"), "r") as f:
        pricing_db = json.load(f)["gpus"]
except FileNotFoundError:
    pricing_db = {"default": {"hourly_cost_usd": 1.00}}

gpu_history: dict = {}
gpu_models: dict = {}
CALIBRATION_SAMPLES = 50

DB_CONFIG = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "postgres",
    "host": "timescaledb",
    "port": 5432,
}

db_lock = threading.Lock()
executor = ThreadPoolExecutor(max_workers=2)


def init_db():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS gpu_metrics (
            time        TIMESTAMPTZ NOT NULL,
            uuid        TEXT NOT NULL,
            utilization DOUBLE PRECISION,
            memory_ratio DOUBLE PRECISION,
            temperature  DOUBLE PRECISION,
            power        DOUBLE PRECISION
        );
    """)
    cur.execute(
        "SELECT create_hypertable('gpu_metrics', 'time', if_not_exists => TRUE);"
    )
    cur.close()
    return conn


def insert_metric(conn, ts, uuid, utilization, memory_ratio, temperature, power):
    try:
        with db_lock:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO gpu_metrics (time, uuid, utilization, memory_ratio, temperature, power) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (ts, uuid, utilization, memory_ratio, temperature, power),
            )
            conn.commit()
            cur.close()
    except Exception as e:
        print(f"[DB INSERT ERROR] {e}")


async def main():
    loop = asyncio.get_event_loop()

    print("Connecting to TimescaleDB...")
    conn = None
    while conn is None:
        try:
            conn = init_db()
            print("TimescaleDB connected. Hypertable ready.")
        except Exception as e:
            print(f"[DB] Connection failed: {e} (retry 3s)")
            await asyncio.sleep(3)

    print("Connecting to NATS...")
    nc = None
    while nc is None:
        try:
            nc = await nats.connect("nats://nats:4222")
            print("NATS connected.")
        except Exception as e:
            print(f"[NATS] Connection failed: {e} (retry 3s)")
            await asyncio.sleep(3)

    async def on_message(msg):
        start_time = time.perf_counter()
        try:
            response = telemetry_pb2.TelemetryResponse()
            response.ParseFromString(msg.data)
        except Exception as e:
            print(f"[PARSE ERROR] {e}")
            return

        print("=" * 70)
        print(
            f"  GPU FINOPS REPORT  ({time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(response.timestamp_utc))})"
        )
        print("=" * 70)

        for gpu in response.gpus:
            uuid = gpu.uuid
            mem_ratio = (
                gpu.memory_used_mb / gpu.memory_total_mb
                if gpu.memory_total_mb > 0
                else 0
            )
            feature_vector = [
                gpu.utilization_percent,
                mem_ratio,
                gpu.temperature_c,
                gpu.power_draw_w,
            ]

            if uuid not in gpu_history:
                gpu_history[uuid] = deque(maxlen=300)
            gpu_history[uuid].append(feature_vector)

            ts_str = time.strftime(
                "%Y-%m-%d %H:%M:%S+00", time.gmtime(response.timestamp_utc)
            )
            loop.run_in_executor(
                executor,
                insert_metric,
                conn,
                ts_str,
                uuid,
                gpu.utilization_percent,
                mem_ratio,
                gpu.temperature_c,
                gpu.power_draw_w,
            )

            latest_power = gpu.power_draw_w
            cost_profile = pricing_db.get(uuid, pricing_db["default"])
            burn_rate = cost_profile["hourly_cost_usd"]

            alerts = []
            n = len(gpu_history[uuid])

            if n < CALIBRATION_SAMPLES:
                alerts.append(
                    f"[CALIBRATING: Gathering Baseline Data... ({n}/{CALIBRATION_SAMPLES})]"
                )
            else:
                arr = np.array(gpu_history[uuid])
                if uuid not in gpu_models or n % 50 == 0:
                    model = IsolationForest(
                        contamination=0.1, random_state=42, n_estimators=100
                    )
                    model.fit(arr)
                    gpu_models[uuid] = model
                model = gpu_models[uuid]
                pred = model.predict([feature_vector])
                if pred[0] == -1:
                    score = model.score_samples([feature_vector])[0]
                    alerts.append(
                        f"[CRITICAL ANOMALY: ISOLATION FOREST DEVIATION (score={score:.4f})]"
                    )
                else:
                    score = model.score_samples([feature_vector])[0]
                    alerts.append(f"[IF Score={score:.4f}]")

            latest_util = gpu.utilization_percent
            if latest_util < 5 and latest_power > 50:
                alerts.append("[WARNING: IDLE BURN DETECTED]")
            if latest_util < 5 and mem_ratio > 0.90:
                alerts.append("[CRITICAL: ZOMBIE PROCESS DETECTED - VRAM HOG]")

            alert_str = " | ".join(alerts)
            print(
                f"[{uuid[:15]}...] Pwr: {latest_power:.1f}W | Util: {latest_util:.0f}% | "
                f"Temp: {gpu.temperature_c:.0f}C | Mem Ratio: {mem_ratio:.2f} | "
                f"Rate: ${burn_rate:.2f}/hr | {alert_str}"
            )

        ntp_offset = response.ntp_offset_ms
        if abs(ntp_offset) > 50:
            print(
                f"[CRITICAL TIME DRIFT] Host clock desynchronized by {ntp_offset}ms. "
                f"Time-series math hazard."
            )

        loop_time_ms = (time.perf_counter() - start_time) * 1000
        print(
            f"-> V3 Loop Execution Time (NATS + Isolation Forest): {loop_time_ms:.2f} ms  |  "
            f"NTP offset: {ntp_offset} ms"
        )

    await nc.subscribe("telemetry.gpu.metrics", cb=on_message)
    print("Subscribed to telemetry.gpu.metrics. Waiting for messages...")

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
