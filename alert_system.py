"""
alert_system.py
-----------------
Turns raw anomaly scores + metric values into human-readable,
severity-ranked alerts, and applies a cooldown so the same kind of
problem doesn't spam dozens of alerts in a row (a common complaint
with naive threshold-based monitoring, and the "intelligent" part
of this project).
"""

import pandas as pd

METRIC_COLUMNS = ["latency_ms", "packet_loss", "bandwidth_mbps",
                   "jitter_ms", "error_rate"]

# Thresholds used only to decide *which metric* caused the alert and
# how severe it looks, once the ML model has already flagged the row.
SEVERITY_RULES = {
    "latency_ms": {"medium": 100, "critical": 250},
    "packet_loss": {"medium": 5, "critical": 15},
    "bandwidth_mbps": {"medium": 60, "critical": 30},   # lower is worse
    "jitter_ms": {"medium": 10, "critical": 20},
    "error_rate": {"medium": 1, "critical": 3},
}


def classify_severity(row):
    """
    Looks at which metric(s) triggered the anomaly and returns the
    worst severity found, plus a short reason string.
    """
    severity_rank = {"low": 0, "medium": 1, "critical": 2}
    worst_severity = "low"
    reasons = []

    for metric, rules in SEVERITY_RULES.items():
        value = row[metric]
        if metric == "bandwidth_mbps":
            # lower bandwidth is worse, so comparisons are reversed
            if value <= rules["critical"]:
                sev = "critical"
            elif value <= rules["medium"]:
                sev = "medium"
            else:
                continue
        else:
            if value >= rules["critical"]:
                sev = "critical"
            elif value >= rules["medium"]:
                sev = "medium"
            else:
                continue

        reasons.append(f"{metric}={value}")
        if severity_rank[sev] > severity_rank[worst_severity]:
            worst_severity = sev

    if not reasons:
        worst_severity = "low"
        reasons.append("flagged by model, no single metric far out of range")

    return worst_severity, "; ".join(reasons)


def generate_alerts(scored_df, cooldown_periods=3):
    """
    Walks through the scored dataframe in time order and emits an
    alert for every row where predicted_anomaly == 1, but suppresses
    repeat alerts of the SAME severity within `cooldown_periods` rows
    of each other (basic alert-fatigue prevention).
    """
    alerts = []
    last_alert_index = -cooldown_periods - 1
    last_severity = None

    df = scored_df.sort_values("timestamp").reset_index(drop=True)

    for i, row in df.iterrows():
        if row["predicted_anomaly"] != 1:
            continue

        severity, reason = classify_severity(row)

        in_cooldown = (i - last_alert_index) < cooldown_periods
        same_severity = severity == last_severity

        if in_cooldown and same_severity:
            continue  # suppress duplicate/noisy alert

        alerts.append({
            "timestamp": row["timestamp"],
            "severity": severity,
            "reason": reason,
            "anomaly_score": row["anomaly_score"],
        })

        last_alert_index = i
        last_severity = severity

    return pd.DataFrame(alerts)


if __name__ == "__main__":
    scored = pd.read_csv("scored_data.csv", parse_dates=["timestamp"])
    alerts = generate_alerts(scored)

    print(f"Generated {len(alerts)} alerts (after cooldown filtering):\n")
    print(alerts.to_string(index=False))

    alerts.to_csv("alerts.csv", index=False)
    print("\nSaved alerts.csv")
