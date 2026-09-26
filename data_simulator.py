"""
data_simulator.py
------------------
Generates synthetic network performance data (latency, packet loss,
bandwidth usage, jitter, error rate) and injects realistic anomalies
into it, so the rest of the pipeline has something to detect.

Run this file directly to create network_data.csv, or import
generate_dataset() from other scripts.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def generate_dataset(num_samples=1000, anomaly_fraction=0.05, seed=42, start_time=None):
    """
    Creates a synthetic time-series dataset of network metrics.

    Columns:
        timestamp     - sample time
        latency_ms    - round trip time in milliseconds
        packet_loss   - percentage of packets lost (0-100)
        bandwidth_mbps- throughput in Mbps
        jitter_ms     - variation in latency
        error_rate    - percentage of errored packets
        is_anomaly    - ground-truth label (1 = anomaly, 0 = normal)
                        kept only for evaluating the model, NOT used
                        by the unsupervised detector itself

    `start_time` lets a caller continue an existing timeline (used by
    the live "tick" feature in the web app) instead of always
    restarting from now(). `seed=None` gives fresh random values each
    call, which is what ticking needs.
    """
    rng = np.random.default_rng(seed)

    start_time = start_time or datetime.now()
    timestamps = [start_time + timedelta(seconds=5 * i) for i in range(num_samples)]

    # --- Normal ("healthy network") baseline traffic ---
    latency = rng.normal(loc=40, scale=5, size=num_samples)       # ~40ms average
    packet_loss = rng.normal(loc=0.5, scale=0.2, size=num_samples)  # ~0.5% loss
    bandwidth = rng.normal(loc=100, scale=10, size=num_samples)   # ~100 Mbps
    jitter = rng.normal(loc=2, scale=0.5, size=num_samples)       # ~2ms jitter
    error_rate = rng.normal(loc=0.1, scale=0.05, size=num_samples)

    is_anomaly = np.zeros(num_samples, dtype=int)

    # --- Inject anomalies (spikes / degradation events) ---
    num_anomalies = int(num_samples * anomaly_fraction)
    anomaly_indices = rng.choice(num_samples, size=num_anomalies, replace=False)

    for idx in anomaly_indices:
        anomaly_type = rng.choice(["latency_spike", "packet_loss_spike",
                                    "bandwidth_drop", "jitter_spike"])
        if anomaly_type == "latency_spike":
            latency[idx] += rng.uniform(150, 400)
        elif anomaly_type == "packet_loss_spike":
            packet_loss[idx] += rng.uniform(10, 40)
        elif anomaly_type == "bandwidth_drop":
            bandwidth[idx] -= rng.uniform(60, 90)
        elif anomaly_type == "jitter_spike":
            jitter[idx] += rng.uniform(15, 40)
        is_anomaly[idx] = 1

    # Clip values to physically sensible ranges
    latency = np.clip(latency, 1, None)
    packet_loss = np.clip(packet_loss, 0, 100)
    bandwidth = np.clip(bandwidth, 0, None)
    jitter = np.clip(jitter, 0, None)
    error_rate = np.clip(error_rate, 0, 100)

    df = pd.DataFrame({
        "timestamp": timestamps,
        "latency_ms": latency.round(2),
        "packet_loss": packet_loss.round(2),
        "bandwidth_mbps": bandwidth.round(2),
        "jitter_ms": jitter.round(2),
        "error_rate": error_rate.round(3),
        "is_anomaly": is_anomaly,
    })

    return df


if __name__ == "__main__":
    df = generate_dataset()
    df.to_csv("network_data.csv", index=False)
    print(f"Generated {len(df)} rows -> network_data.csv")
    print(f"Injected anomalies: {df['is_anomaly'].sum()}")
