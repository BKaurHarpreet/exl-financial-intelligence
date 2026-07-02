async function getJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`${url} -> ${response.status}: ${await response.text()}`);
  return response.json();
}

function setStatus(message, isError) {
  let el = document.getElementById("status-banner");
  if (!el) {
    el = document.createElement("div");
    el.id = "status-banner";
    document.querySelector("main").prepend(el);
  }
  if (!message) {
    el.style.display = "none";
    return;
  }
  el.textContent = message;
  el.style.display = "block";
  el.className = isError ? "status-banner status-error" : "status-banner status-loading";
}

function setRows(tableId, rows, columns) {
  const body = document.querySelector(`#${tableId} tbody`);
  body.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const column of columns) {
      const td = document.createElement("td");
      const value = row[column];
      td.textContent = value === null || value === undefined ? "" : value;
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
}

const METRIC_LABELS = {
  revenue: "Revenue",
  operating_margin_pct: "Operating Margin",
  diluted_eps: "Diluted EPS",
};

function formatValue(metric, value) {
  if (value === null || value === undefined) return "—";
  if (metric === "revenue") return `$${(value / 1000).toFixed(1)}M`;
  if (metric === "operating_margin_pct") return `${value.toFixed(1)}%`;
  if (metric === "diluted_eps") return `$${value.toFixed(2)}`;
  return value;
}

function renderCards(latest) {
  const container = document.getElementById("kpi-cards");
  container.innerHTML = "";
  for (const row of latest) {
    const yoy = row.yoy_change_pct;
    const hasYoy = yoy !== null && yoy !== undefined;
    const arrow = hasYoy ? (yoy >= 0 ? "▲" : "▼") : "";
    const yoyClass = hasYoy ? (yoy >= 0 ? "positive" : "negative") : "";
    const card = document.createElement("div");
    card.className = "kpi-card";
    card.innerHTML = `
      <h3>${METRIC_LABELS[row.metric_name] || row.metric_name}</h3>
      <div class="kpi-value">${formatValue(row.metric_name, row.value)}</div>
      <div class="kpi-yoy ${yoyClass}">${arrow} ${hasYoy ? yoy.toFixed(1) + "% YoY" : "N/A"}</div>
      <p class="kpi-insight">${row.insight_text || ""}</p>
    `;
    container.appendChild(card);
  }
}

const charts = {};
function renderCharts(trends) {
  const container = document.getElementById("kpi-charts");
  container.innerHTML = "";
  const byMetric = {};
  for (const row of trends) {
    (byMetric[row.metric_name] ||= []).push(row);
  }
  for (const [metric, rows] of Object.entries(byMetric)) {
    rows.sort((a, b) => a.fiscal_year - b.fiscal_year);
    const wrapper = document.createElement("div");
    wrapper.className = "chart-card";
    wrapper.innerHTML = `<h3>${METRIC_LABELS[metric] || metric} Trend</h3><canvas></canvas>`;
    container.appendChild(wrapper);
    const ctx = wrapper.querySelector("canvas").getContext("2d");
    if (charts[metric]) charts[metric].destroy();
    charts[metric] = new Chart(ctx, {
      type: "line",
      data: {
        labels: rows.map(r => r.fiscal_year),
        datasets: [{
          label: METRIC_LABELS[metric] || metric,
          data: rows.map(r => r.value),
          borderColor: "#0f766e",
          backgroundColor: "rgba(15,118,110,0.1)",
          tension: 0.25,
          fill: true,
        }],
      },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: false } } },
    });
  }
}

async function refresh() {
  setStatus("Loading dashboard...", false);
  const results = await Promise.allSettled([
    getJson("/pipeline/runs"),
    getJson("/metrics?limit=100"),
    getJson("/kpis/latest"),
    getJson("/kpis"),
  ]);
  const [runsR, metricsR, latestR, trendsR] = results;
  const failures = results.filter(r => r.status === "rejected");

  if (runsR.status === "fulfilled") {
    setRows("runs", runsR.value, ["status", "started_at", "source_file_count", "bronze_cells_loaded", "silver_facts_loaded", "gold_rows_loaded"]);
  }
  if (metricsR.status === "fulfilled") {
    setRows("metrics", metricsR.value, ["fiscal_year", "metric_name", "observations", "total_value", "average_value"]);
  }
  if (latestR.status === "fulfilled" && latestR.value.length > 0) {
    renderCards(latestR.value);
  } else if (latestR.status === "fulfilled") {
    document.getElementById("kpi-cards").innerHTML =
      "<p>No KPI data yet -- the pipeline may still be running on first startup. Try refreshing in a moment.</p>";
  }
  if (trendsR.status === "fulfilled" && trendsR.value.length > 0) {
    renderCharts(trendsR.value);
  }

  if (failures.length > 0) {
    console.error("Dashboard load errors:", failures.map(f => f.reason));
    setStatus(`Some data failed to load (${failures.length} of ${results.length} requests). Check console for details.`, true);
  } else {
    setStatus(null, false);
  }
}

document.getElementById("run-pipeline").addEventListener("click", async () => {
  const button = document.getElementById("run-pipeline");
  button.disabled = true;
  setStatus("Running ETL pipeline... this can take a minute.", false);
  try {
    await getJson("/pipeline/run", { method: "POST" });
    await refresh();
  } catch (error) {
    console.error("Pipeline run failed:", error);
    setStatus(`Pipeline run failed: ${error.message}`, true);
  } finally {
    button.disabled = false;
  }
});

refresh().catch((error) => {
  console.error("Initial dashboard load failed:", error);
  setStatus(`Dashboard failed to load: ${error.message}`, true);
});