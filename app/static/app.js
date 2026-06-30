async function getJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
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

async function refresh() {
  const [runs, metrics] = await Promise.all([getJson("/pipeline/runs"), getJson("/metrics?limit=100")]);
  setRows("runs", runs, ["status", "started_at", "source_file_count", "bronze_cells_loaded", "silver_facts_loaded", "gold_rows_loaded"]);
  setRows("metrics", metrics, ["fiscal_year", "metric_name", "observations", "total_value", "average_value"]);
}

document.getElementById("run-pipeline").addEventListener("click", async () => {
  await getJson("/pipeline/run", { method: "POST" });
  await refresh();
});

refresh().catch((error) => console.error(error));
