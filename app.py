"""
app.py
-------
Flask backend for the Network Performance Monitoring web app.
Wraps the existing pipeline (data_simulator / real_metrics,
preprocessing, anomaly_detection, alert_system) behind a small JSON
API, and serves the static frontend that visualizes it in the browser.

Supports two data sources, selected per-request with ?mode=sim|real:
  - "sim"  -> synthetic data from data_simulator.py (safe demo data,
              guaranteed anomalies, good for showing the model works)
  - "real" -> actual metrics from THIS machine's network, collected
              by real_metrics.py (genuine real-time monitoring)

Run:  python app.py
Then open http://127.0.0.1:5000 in your browser.
"""

import os
from datetime import timedelta
import pandas as pd
from flask import Flask, jsonify, request, send_file

from data_simulator import generate_dataset
from real_metrics import collect_sample, collect_baseline
from preprocessing import load_and_clean, descriptive_stats
from anomaly_detection import train_model, score_dataset
from alert_system import generate_alerts

app = Flask(__name__, static_folder="static", static_url_path="")

METRIC_COLUMNS = ["latency_ms", "packet_loss", "bandwidth_mbps",
                   "jitter_ms", "error_rate"]


def paths_for(mode):
    """Returns (data_csv, scored_csv, alerts_csv) for the given mode."""
    if mode not in ("sim", "real"):
        mode = "sim"
    return f"network_data_{mode}.csv", f"scored_data_{mode}.csv", f"alerts_{mode}.csv"


def get_mode():
    """Reads ?mode=sim|real from the query string, defaulting to sim."""
    return request.args.get("mode", "sim")


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/generate", methods=["POST"])
def api_generate():
    """
    Creates a fresh starting dataset.
    mode=sim  -> synthetic batch (num_samples, anomaly_fraction in body)
    mode=real -> collects a short real baseline from this machine
                 (takes roughly 30-60 seconds; blocking on purpose so
                 the frontend can show a clear "collecting..." state)
    """
    mode = get_mode()
    data_csv, scored_csv, alerts_csv = paths_for(mode)
    body = request.get_json(silent=True) or {}

    if mode == "real":
        num_samples = int(body.get("num_samples", 15))
        rows = collect_baseline(num_samples=num_samples)
        df = pd.DataFrame(rows)
        df.to_csv(data_csv, index=False)
        injected = None
    else:
        num_samples = int(body.get("num_samples", 1000))
        anomaly_fraction = float(body.get("anomaly_fraction", 0.05))
        df = generate_dataset(num_samples=num_samples, anomaly_fraction=anomaly_fraction)
        df.to_csv(data_csv, index=False)
        injected = int(df["is_anomaly"].sum())

    for path in (scored_csv, alerts_csv):
        if os.path.exists(path):
            os.remove(path)

    return jsonify({"status": "ok", "rows": len(df), "injected_anomalies": injected})


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Runs preprocessing + anomaly detection + alert generation."""
    mode = get_mode()
    data_csv, scored_csv, alerts_csv = paths_for(mode)

    if not os.path.exists(data_csv):
        return jsonify({"error": "No data yet. Generate/collect data first."}), 400

    clean_df = load_and_clean(data_csv)
    if len(clean_df) < 10:
        return jsonify({"error": "Need at least 10 samples before running detection."}), 400

    stats_df = descriptive_stats(clean_df)

    model = train_model(clean_df)
    scored_df = score_dataset(clean_df, model)
    scored_df.to_csv(scored_csv, index=False)

    alerts_df = generate_alerts(scored_df)
    alerts_df.to_csv(alerts_csv, index=False)

    stats_records = (
        stats_df.reset_index().rename(columns={"index": "metric"}).to_dict(orient="records")
    )

    return jsonify({
        "status": "ok",
        "stats": stats_records,
        "num_samples": len(scored_df),
        "predicted_anomalies": int(scored_df["predicted_anomaly"].sum()),
        "num_alerts": len(alerts_df),
    })


@app.route("/api/tick", methods=["POST"])
def api_tick():
    """
    Appends ONE new batch of 'live' samples and re-runs the pipeline.
    mode=sim  -> 20 synthetic samples continuing the timeline
    mode=real -> 1 real sample collected right now from this machine
    """
    mode = get_mode()
    data_csv, scored_csv, alerts_csv = paths_for(mode)

    if not os.path.exists(data_csv):
        return jsonify({"error": "No data yet. Generate/collect data first."}), 400

    existing = pd.read_csv(data_csv, parse_dates=["timestamp"])
    last_timestamp = existing["timestamp"].max()

    if mode == "real":
        new_rows = pd.DataFrame([collect_sample()])
    else:
        new_rows = generate_dataset(
            num_samples=20, anomaly_fraction=0.05, seed=None,
            start_time=last_timestamp + timedelta(seconds=5),
        )

    combined = pd.concat([existing, new_rows], ignore_index=True)
    combined.to_csv(data_csv, index=False)

    clean_df = load_and_clean(data_csv)
    model = train_model(clean_df)
    scored_df = score_dataset(clean_df, model)
    scored_df.to_csv(scored_csv, index=False)

    alerts_df = generate_alerts(scored_df)
    alerts_df.to_csv(alerts_csv, index=False)

    return jsonify({
        "status": "ok",
        "num_samples": len(scored_df),
        "predicted_anomalies": int(scored_df["predicted_anomaly"].sum()),
        "num_alerts": len(alerts_df),
        "new_rows": len(new_rows),
    })


@app.route("/api/chart-data")
def api_chart_data():
    """Returns the scored time-series data for plotting in the browser."""
    mode = get_mode()
    _, scored_csv, _ = paths_for(mode)

    if not os.path.exists(scored_csv):
        return jsonify({"error": "Run analysis first."}), 400

    df = pd.read_csv(scored_csv, parse_dates=["timestamp"])
    payload = {
        "timestamps": df["timestamp"].dt.strftime("%H:%M:%S").tolist(),
        "predicted_anomaly": df["predicted_anomaly"].tolist(),
        "metrics": {col: df[col].tolist() for col in METRIC_COLUMNS},
    }
    return jsonify(payload)


@app.route("/api/alerts")
def api_alerts():
    """Returns the generated alerts, most recent first."""
    mode = get_mode()
    _, _, alerts_csv = paths_for(mode)

    if not os.path.exists(alerts_csv):
        return jsonify([])

    df = pd.read_csv(alerts_csv, parse_dates=["timestamp"])
    df = df.sort_values("timestamp", ascending=False)
    df["timestamp"] = df["timestamp"].dt.strftime("%H:%M:%S")
    return jsonify(df.to_dict(orient="records"))


@app.route("/api/alerts/download")
def api_alerts_download():
    """Serves the current mode's alerts CSV as a downloadable file."""
    mode = get_mode()
    _, _, alerts_csv = paths_for(mode)

    if not os.path.exists(alerts_csv):
        return jsonify({"error": "No alerts yet. Run detection first."}), 400
    return send_file(alerts_csv, as_attachment=True,
                      download_name=f"netwatch_alerts_{mode}.csv")


@app.route("/api/status")
def api_status():
    """Tells the frontend what stage the pipeline is currently in, per mode."""
    mode = get_mode()
    data_csv, scored_csv, _ = paths_for(mode)
    return jsonify({
        "has_data": os.path.exists(data_csv),
        "has_results": os.path.exists(scored_csv),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
