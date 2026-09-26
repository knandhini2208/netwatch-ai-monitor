# Netwatch — AI Network Performance Monitor (Web App)

A Flask + browser dashboard for your network monitoring mini project.
Supports **two data sources**, switchable from the dashboard itself:

- **Simulated** — synthetic traffic with injected anomalies (safe,
  guaranteed to show the model working, good for a first demo)
- **Real (this device)** — genuine real-time metrics: actual ping
  round-trip times to 8.8.8.8 (Google DNS) for latency/jitter/packet
  loss, and this machine's real network interface counters (via
  `psutil`) for bandwidth and error rate

Same ML pipeline either way: preprocessing → Isolation Forest anomaly
detection → intelligent, severity-ranked alerts.

## How to run

1. Open this folder in VS Code (or a terminal).
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the server:
   ```
   python app.py
   ```
4. Open your browser to: **http://127.0.0.1:5000**
5. Pick a mode at the top ("Simulated" or "Real (this device)"), click
   **Generate data** / **Collect real data**, then **Run detection**.

Real mode takes longer to "Generate data" (roughly 15-30 seconds) —
it's actually pinging 8.8.8.8 and reading your network counters in a
loop to build an initial baseline, not an instant simulation. That
delay is your evidence it's doing something real.

## How it works

- `app.py` is the Flask backend. Every endpoint takes a `?mode=sim` or
  `?mode=real` query param (the frontend sets this automatically
  based on which mode button is selected):
  - `POST /api/generate` — builds a starting dataset (synthetic batch,
    or a real collected baseline)
  - `POST /api/analyze` — runs preprocessing, trains the Isolation
    Forest model, scores the data, generates alerts
  - `POST /api/tick` — used by "live monitoring": adds one more batch
    (simulated) or one real sample (real mode) and re-runs the pipeline
  - `GET /api/chart-data` — time-series data for the charts
  - `GET /api/alerts` / `GET /api/alerts/download` — the alert list,
    and a CSV download of it
  - `GET /api/status` — tells the frontend what stage things are at
- Each mode keeps its own separate CSV files
  (`network_data_sim.csv` / `network_data_real.csv`, etc.) so
  switching modes never mixes fake and real data.
- `data_simulator.py` generates the synthetic traffic.
  `real_metrics.py` collects the real metrics (ping + psutil).
  `preprocessing.py`, `anomaly_detection.py`, `alert_system.py` are
  the shared pipeline, used by both modes identically.
- `static/` is the frontend: plain HTML/CSS/JS (no build step). Chart.js
  is bundled locally in `static/vendor/` so it works even without
  internet access to a CDN.

## About "real" mode

- It pings a **public** host (8.8.8.8) to measure latency/jitter/loss
  — it does not scan or monitor your local network or other devices,
  only the path from this machine outward.
- Bandwidth and error rate come from your OS's own network interface
  counters (the same numbers Task Manager / `ifconfig` would show),
  covering all your traffic during that interval, not just the pings.
- On a normal, stable connection you should expect **few or no
  anomalies** — that's the model working correctly on real data, not
  a bug. Compare this to simulated mode, which always has anomalies
  because they're deliberately injected.
- If you want to *see* a real anomaly for a demo, try running it while
  doing something that spikes your network (a large download, a video
  call) or briefly disabling Wi-Fi for one tick.

## Features

- **Live monitoring** — click "Start live monitoring" to auto-refresh
  every 5 seconds: simulated mode appends a synthetic batch, real mode
  collects one new real sample, and the pipeline re-runs each time.
- **Severity filter** — filter the alert feed by critical/medium/low
  without re-fetching from the server.
- **Download CSV** — grabs the current mode's alerts as a file.

## Notes for your report/viva

- Talking point: this app can be pointed at either synthetic or real
  traffic through the same pipeline — a good answer if asked "is this
  just simulated?" or "is this real-time?".
- The rational-agent framing, descriptive statistics
  (`preprocessing.descriptive_stats`), and pipeline stages all map to
  your syllabus units exactly as before — see the original project's
  README for those talking points in full.
