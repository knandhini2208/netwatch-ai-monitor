"""
real_metrics.py
-----------------
Collects REAL network performance samples from the machine this app
is running on, instead of simulating them. Used by the web app's
"Real (this device)" mode.

Two sources of truth:
  - `ping` (the OS command) -> real round-trip latency, jitter, and
    packet loss to an external host.
  - `psutil.net_io_counters()` -> real throughput (bandwidth) and
    error/drop counts from this machine's network interface(s).

Note: once this app is deployed to a server, "this device" means the
SERVER's network, not your laptop's -- see the README for what that
means for your demo.
"""

import platform
import re
import subprocess
import time
from datetime import datetime

import psutil

PING_TARGET = "8.8.8.8"  # Google DNS -- stable, always-up, good for a latency reference

_last_net_io = None
_last_net_time = None


def _ping_host(host=PING_TARGET, count=2, timeout_s=6):
    """
    Runs the OS's own ping command (no extra permissions needed) and
    parses per-reply round-trip times and packet loss.

    Returns (avg_latency_ms, jitter_ms, packet_loss_pct).
    If the host is unreachable (e.g. no internet, or ICMP blocked by
    a firewall/host), returns (None, None, 100.0) rather than raising
    -- callers should treat None latency as "unknown", not zero.
    """
    is_windows = platform.system().lower() == "windows"
    cmd = ["ping", "-n" if is_windows else "-c", str(count), host]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s
        )
        output = result.stdout
    except Exception:
        return None, None, 100.0

    # "time=23ms" (Linux/Mac) or "time=23ms" / "time<1ms" (Windows)
    times = [float(t) for t in re.findall(r"time[=<]\s*([\d.]+)\s*ms", output, re.IGNORECASE)]

    loss_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:packet\s*)?loss", output, re.IGNORECASE)
    packet_loss = float(loss_match.group(1)) if loss_match else (0.0 if times else 100.0)

    if not times:
        return None, None, packet_loss

    avg_latency = sum(times) / len(times)
    jitter = (max(times) - min(times)) if len(times) > 1 else 0.0
    return round(avg_latency, 2), round(jitter, 2), packet_loss


def _bandwidth_and_errors():
    """
    Measures real throughput (Mbps) and a simple error rate since the
    last call, using the OS's network interface counters. The first
    call in a process has nothing to compare against, so it returns
    zeros -- normal, and only happens once per server run.
    """
    global _last_net_io, _last_net_time
    counters = psutil.net_io_counters()
    now = time.time()

    if _last_net_io is None:
        _last_net_io, _last_net_time = counters, now
        return 0.0, 0.0

    elapsed = max(now - _last_net_time, 0.001)
    bytes_delta = (
        (counters.bytes_sent - _last_net_io.bytes_sent)
        + (counters.bytes_recv - _last_net_io.bytes_recv)
    )
    bandwidth_mbps = (bytes_delta * 8) / elapsed / 1_000_000

    packets_delta = (
        (counters.packets_sent - _last_net_io.packets_sent)
        + (counters.packets_recv - _last_net_io.packets_recv)
    )
    errors_delta = (
        (counters.errin - _last_net_io.errin)
        + (counters.errout - _last_net_io.errout)
        + (counters.dropin - _last_net_io.dropin)
        + (counters.dropout - _last_net_io.dropout)
    )
    error_rate = (errors_delta / packets_delta * 100) if packets_delta > 0 else 0.0

    _last_net_io, _last_net_time = counters, now
    return round(bandwidth_mbps, 3), round(error_rate, 4)


def collect_sample(host=PING_TARGET, ping_count=2):
    """
    Collects one real sample: {timestamp, latency_ms, packet_loss,
    bandwidth_mbps, jitter_ms, error_rate} -- same shape as the
    simulator's rows, so it drops straight into the existing pipeline.
    """
    latency, jitter, packet_loss = _ping_host(host, ping_count)
    bandwidth, error_rate = _bandwidth_and_errors()

    return {
        "timestamp": datetime.now(),
        "latency_ms": latency if latency is not None else 0.0,
        "packet_loss": packet_loss,
        "bandwidth_mbps": bandwidth,
        "jitter_ms": jitter if jitter is not None else 0.0,
        "error_rate": error_rate,
    }


def collect_baseline(num_samples=15, host=PING_TARGET, ping_count=2):
    """
    Collects a short back-to-back run of real samples to give the
    anomaly model an initial baseline of "what normal looks like" on
    this machine. Takes roughly num_samples * ping_count seconds.
    """
    return [collect_sample(host, ping_count) for _ in range(num_samples)]


if __name__ == "__main__":
    print("Collecting 5 real samples (takes ~10-15s)...")
    for row in collect_baseline(num_samples=5):
        print(row)
