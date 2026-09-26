const METRICS = [
  { key: "latency_ms", color: "#3FB8AF" },
  { key: "packet_loss", color: "#5FA8D3" },
  { key: "bandwidth_mbps", color: "#3FB8AF" },
  { key: "jitter_ms", color: "#5FA8D3" },
  { key: "error_rate", color: "#3FB8AF" },
];

const charts = {};

const btnGenerate = document.getElementById("btn-generate");
const btnAnalyze = document.getElementById("btn-analyze");
const btnLive = document.getElementById("btn-live");
const btnDownload = document.getElementById("btn-download");
const severityFilter = document.getElementById("severity-filter");
const liveDot = document.getElementById("live-dot");
const modeButtons = document.querySelectorAll(".mode-btn");

const statSamples = document.getElementById("stat-samples");
const statAnomalies = document.getElementById("stat-anomalies");
const statAlerts = document.getElementById("stat-alerts");
const statModel = document.getElementById("stat-model");

const chartsEmpty = document.getElementById("charts-empty");
const alertList = document.getElementById("alert-list");
const alertCount = document.getElementById("alert-count");

let latestAlerts = [];
let liveInterval = null;
let currentMode = "sim"; // "sim" | "real"
const LIVE_REFRESH_MS = 5000;

function apiUrl(path) {
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}mode=${currentMode}`;
}

function resetDashboard() {
  stopLiveMonitoring();
  Object.keys(charts).forEach((key) => {
    charts[key].destroy();
    delete charts[key];
  });
  document.querySelectorAll(".chart-block").forEach((block) => (block.hidden = true));
  chartsEmpty.hidden = false;

  statSamples.textContent = "—";
  statAnomalies.textContent = "—";
  statAlerts.textContent = "—";
  statModel.textContent = "Idle";
  liveDot.classList.remove("live", "pulsing");

  btnAnalyze.disabled = true;
  btnLive.disabled = true;
  btnDownload.classList.add("disabled");

  latestAlerts = [];
  alertCount.textContent = "";
  alertList.innerHTML = `<div class="empty-state"><p class="muted">Alerts will appear here after detection runs.</p></div>`;
}

async function setMode(mode) {
  if (mode === currentMode) return;
  currentMode = mode;

  modeButtons.forEach((btn) => btn.classList.toggle("active", btn.dataset.mode === mode));
  btnGenerate.textContent = mode === "real" ? "Collect real data" : "Generate data";
  btnDownload.href = apiUrl("/api/alerts/download");

  const modeInfo = document.getElementById("mode-info");
  if (mode === "real") {
    modeInfo.textContent =
      "Real mode pings 8.8.8.8 (Google DNS) for latency/jitter/packet loss, and reads this device's actual network interface counters for bandwidth and error rate.";
    modeInfo.hidden = false;
  } else {
    modeInfo.hidden = true;
  }

  resetDashboard();
  await checkStatus();
}

function setBusy(button, busyLabel) {
  button.dataset.originalText = button.dataset.originalText || button.textContent;
  button.textContent = busyLabel;
  button.disabled = true;
}

function resetButton(button) {
  button.textContent = button.dataset.originalText || button.textContent;
  button.disabled = false;
}

async function generateData() {
  const isReal = currentMode === "real";
  setBusy(btnGenerate, isReal ? "Collecting… (~15-30s)" : "Generating…");
  statModel.textContent = isReal ? "Pinging this device's network" : "Simulating";
  try {
    const body = isReal
      ? { num_samples: 15 }
      : { num_samples: 1000, anomaly_fraction: 0.05 };

    const res = await fetch(apiUrl("/api/generate"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed to generate data");

    statSamples.textContent = data.rows;
    statAnomalies.textContent = "—";
    statAlerts.textContent = "—";
    statModel.textContent = "Data ready";
    btnAnalyze.disabled = false;
  } catch (err) {
    statModel.textContent = "Error";
    alert(err.message);
  } finally {
    resetButton(btnGenerate);
  }
}

function stopLiveMonitoring() {
  if (liveInterval) {
    clearInterval(liveInterval);
    liveInterval = null;
  }
  btnLive.textContent = "Start live monitoring";
  btnLive.classList.remove("live-active");
  liveDot.classList.remove("pulsing");
}

async function tick() {
  try {
    const res = await fetch(apiUrl("/api/tick"), { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Live update failed");

    statSamples.textContent = data.num_samples;
    statAnomalies.textContent = data.predicted_anomalies;
    statAlerts.textContent = data.num_alerts;

    await Promise.all([loadChartData(), loadAlerts()]);
  } catch (err) {
    stopLiveMonitoring();
    statModel.textContent = "Error";
    alert(err.message);
  }
}

function toggleLiveMonitoring() {
  if (liveInterval) {
    stopLiveMonitoring();
    statModel.textContent = "Monitoring";
    return;
  }
  btnLive.textContent = "Stop live monitoring";
  btnLive.classList.add("live-active");
  liveDot.classList.add("pulsing");
  statModel.textContent = "Live";
  tick(); // run once immediately, then on an interval
  liveInterval = setInterval(tick, LIVE_REFRESH_MS);
}

async function runAnalysis() {
  setBusy(btnAnalyze, "Analyzing…");
  statModel.textContent = "Training model";
  try {
    const res = await fetch(apiUrl("/api/analyze"), { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed to run detection");

    statSamples.textContent = data.num_samples;
    statAnomalies.textContent = data.predicted_anomalies;
    statAlerts.textContent = data.num_alerts;
    statModel.textContent = "Monitoring";
    liveDot.classList.add("live");
    btnLive.disabled = false;
    btnDownload.classList.remove("disabled");

    await Promise.all([loadChartData(), loadAlerts()]);
  } catch (err) {
    statModel.textContent = "Error";
    alert(err.message);
  } finally {
    resetButton(btnAnalyze);
  }
}

async function loadChartData() {
  const res = await fetch(apiUrl("/api/chart-data"));
  const data = await res.json();
  if (!res.ok) return;

  chartsEmpty.hidden = true;

  METRICS.forEach(({ key, color }) => {
    const block = document.querySelector(`.chart-block[data-metric="${key}"]`);
    block.hidden = false;
    const canvas = block.querySelector("canvas");
    const values = data.metrics[key];

    const pointColors = data.predicted_anomaly.map((flag) =>
      flag ? "#E2574C" : "rgba(0,0,0,0)"
    );
    const pointRadii = data.predicted_anomaly.map((flag) => (flag ? 3 : 0));

    if (charts[key]) {
      charts[key].data.labels = data.timestamps;
      charts[key].data.datasets[0].data = values;
      charts[key].data.datasets[0].pointBackgroundColor = pointColors;
      charts[key].data.datasets[0].pointRadius = pointRadii;
      charts[key].update();
      return;
    }

    charts[key] = new Chart(canvas, {
      type: "line",
      data: {
        labels: data.timestamps,
        datasets: [
          {
            data: values,
            borderColor: color,
            borderWidth: 1.5,
            pointBackgroundColor: pointColors,
            pointRadius: pointRadii,
            pointHoverRadius: 4,
            tension: 0.15,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { display: false },
          y: {
            ticks: { color: "#8CA0B3", font: { family: "IBM Plex Mono", size: 10 } },
            grid: { color: "#1C2B3A" },
          },
        },
      },
    });
  });
}

async function loadAlerts() {
  const res = await fetch(apiUrl("/api/alerts"));
  latestAlerts = await res.json();
  renderAlerts();
}

function renderAlerts() {
  const filter = severityFilter.value;
  const alerts =
    filter === "all" ? latestAlerts : latestAlerts.filter((a) => a.severity === filter);

  alertCount.textContent = latestAlerts.length ? `${alerts.length} of ${latestAlerts.length}` : "";

  if (!latestAlerts.length) {
    alertList.innerHTML = `<div class="empty-state"><p class="muted">No alerts raised on this run.</p></div>`;
    return;
  }
  if (!alerts.length) {
    alertList.innerHTML = `<div class="empty-state"><p class="muted">No alerts at this severity.</p></div>`;
    return;
  }

  alertList.innerHTML = alerts
    .map(
      (a) => `
      <div class="alert-item">
        <div class="alert-top">
          <span class="severity-tag severity-${a.severity}">${a.severity}</span>
          <span class="alert-time">${a.timestamp}</span>
        </div>
        <div class="alert-reason">${a.reason}</div>
      </div>`
    )
    .join("");
}

async function checkStatus() {
  const res = await fetch(apiUrl("/api/status"));
  const status = await res.json();
  if (status.has_data) btnAnalyze.disabled = false;
  if (status.has_results) {
    liveDot.classList.add("live");
    statModel.textContent = "Monitoring";
    btnLive.disabled = false;
    btnDownload.classList.remove("disabled");
    await Promise.all([loadChartData(), loadAlerts()]);
  }
}

btnGenerate.addEventListener("click", generateData);
btnAnalyze.addEventListener("click", runAnalysis);
btnLive.addEventListener("click", toggleLiveMonitoring);
severityFilter.addEventListener("change", renderAlerts);
modeButtons.forEach((btn) => btn.addEventListener("click", () => setMode(btn.dataset.mode)));

btnDownload.href = apiUrl("/api/alerts/download");
checkStatus();
