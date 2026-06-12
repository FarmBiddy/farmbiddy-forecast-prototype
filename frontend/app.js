/**
 * FarmBiddy visual interface — fetches from /api/... and renders results.
 */

const API = "/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatEuro(value) {
  if (value === null || value === undefined) return "—";
  return "€" + Number(value).toLocaleString("en-IE", { maximumFractionDigits: 0 });
}

function formatPercent(value) {
  if (value === null || value === undefined) return "—";
  return Number(value).toFixed(1) + "%";
}

function riskClass(level) {
  if (!level) return "";
  return "risk-" + level.toLowerCase();
}

function chartUrl(filePath) {
  const fileName = filePath.replace(/\\/g, "/").split("/").pop();
  return "/chart-files/" + fileName;
}

function chartLabel(type) {
  const labels = {
    running_balance: "Running Balance",
    revenue_vs_costs: "Revenue vs Costs",
    cost_breakdown: "Cost Breakdown",
    scenario_profit: "Scenario Profit Comparison",
    kpi_comparison: "KPI Comparison",
    historical_profit_trend: "Historical Profit Trend",
  };
  return labels[type] || type;
}

function showStatus(message, type) {
  const el = document.getElementById("status-message");
  el.textContent = message;
  el.className = "status-message " + type;
  el.classList.remove("hidden");
}

function hideStatus() {
  document.getElementById("status-message").classList.add("hidden");
}

function getSelectedFarms() {
  return [...document.querySelectorAll("#farm-list input:checked")].map(
    (cb) => cb.value
  );
}

function getOutputOptions() {
  const outputs = { kpis: true, charts: false };

  document.querySelectorAll('#output-options input[name="output"]').forEach((cb) => {
    outputs[cb.value] = cb.checked;
  });

  outputs.charts = document.getElementById("charts-enabled").checked;
  return outputs;
}

function getChartTypes() {
  if (!document.getElementById("charts-enabled").checked) return [];

  return [...document.querySelectorAll('#chart-options input[name="chart"]:checked')].map(
    (cb) => cb.value
  );
}

async function apiFetch(path, options) {
  const response = await fetch(API + path, options);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || "Request failed");
  }

  return response.json();
}

// ---------------------------------------------------------------------------
// Load farms on startup
// ---------------------------------------------------------------------------

async function loadFarms() {
  const farmList = document.getElementById("farm-list");
  const sandboxSelect = document.getElementById("sandbox-farm");

  try {
    const data = await apiFetch("/farms");
    farmList.innerHTML = "";
    sandboxSelect.innerHTML = "";

    data.farms.forEach((farm) => {
      // Farm checkboxes
      const item = document.createElement("label");
      item.className = "farm-item";
      item.innerHTML =
        `<input type="checkbox" value="${farm.farm_file}" />` +
        `<strong>${farm.farm_name}</strong>` +
        `<span class="farm-meta">${farm.milking_cows || "—"} cows · €${farm.milk_price || "—"}/L</span>`;
      farmList.appendChild(item);

      // Sandbox dropdown
      const option = document.createElement("option");
      option.value = farm.farm_file;
      option.textContent = farm.farm_name;
      sandboxSelect.appendChild(option);
    });
  } catch (error) {
    farmList.innerHTML = `<p class="loading">Could not load farms: ${error.message}</p>`;
  }
}

// ---------------------------------------------------------------------------
// Render single-farm dashboard
// ---------------------------------------------------------------------------

function renderKpiCards(summary, kpis, riskLevel) {
  const monthlyCashflow = kpis ? kpis.monthly_cashflow : null;

  return `
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="label">Annual Revenue</div>
        <div class="value">${formatEuro(summary.annual_revenue)}</div>
      </div>
      <div class="kpi-card">
        <div class="label">Annual Costs</div>
        <div class="value">${formatEuro(summary.annual_costs)}</div>
      </div>
      <div class="kpi-card">
        <div class="label">Annual Profit</div>
        <div class="value">${formatEuro(summary.annual_profit)}</div>
      </div>
      <div class="kpi-card">
        <div class="label">Profit Margin</div>
        <div class="value">${formatPercent(summary.profit_margin)}</div>
      </div>
      <div class="kpi-card ${riskClass(riskLevel)}">
        <div class="label">Risk Level</div>
        <div class="value">${riskLevel || "—"}</div>
      </div>
      <div class="kpi-card">
        <div class="label">Monthly Cashflow</div>
        <div class="value">${formatEuro(monthlyCashflow)}</div>
      </div>
    </div>
  `;
}

function renderAlerts(alerts) {
  if (!alerts || alerts.length === 0) {
    return `<p class="no-alerts">No major alerts.</p>`;
  }

  return `<div class="alert-box"><ul>${alerts.map((a) => `<li>${a}</li>`).join("")}</ul></div>`;
}

function renderRiskDrivers(drivers) {
  if (!drivers || drivers.length === 0) {
    return `<p class="no-alerts">No major risk drivers identified.</p>`;
  }

  return drivers
    .map(
      (d) =>
        `<div class="risk-driver">` +
        `<strong>${d.driver}</strong> ` +
        `<span class="risk-badge ${d.risk}">${d.risk}</span>` +
        `<p>${d.commentary}</p></div>`
    )
    .join("");
}

function renderMonthlyTable(monthly) {
  if (!monthly || monthly.length === 0) return "";

  const rows = monthly
    .map(
      (m) =>
        `<tr>` +
        `<td>Month ${m.month}</td>` +
        `<td class="num">${formatEuro(m.revenue)}</td>` +
        `<td class="num">${formatEuro(m.costs)}</td>` +
        `<td class="num">${formatEuro(m.cashflow)}</td>` +
        `<td class="num">${formatEuro(m.running_balance)}</td>` +
        `</tr>`
    )
    .join("");

  return `
    <table class="data-table">
      <thead>
        <tr>
          <th>Month</th>
          <th class="num">Revenue</th>
          <th class="num">Costs</th>
          <th class="num">Cashflow</th>
          <th class="num">Running Balance</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderAdvisory(advisory) {
  if (!advisory) return "";

  const strengths = (advisory.key_strengths || [])
    .map((s) => `<li>${s}</li>`)
    .join("");
  const concerns = (advisory.key_concerns || [])
    .map((c) => `<li>${c}</li>`)
    .join("");

  return `
    <div class="advisory-block"><strong>Headline:</strong> ${advisory.headline}</div>
    <div class="advisory-block"><strong>Financial position:</strong> ${advisory.financial_position}</div>
    <div class="advisory-block"><strong>Cashflow:</strong> ${advisory.cashflow_commentary}</div>
    <div class="advisory-block"><strong>Risk:</strong> ${advisory.risk_commentary}</div>
    <div class="advisory-block"><strong>Key strengths:</strong><ul class="advisory-list">${strengths}</ul></div>
    <div class="advisory-block"><strong>Key concerns:</strong><ul class="advisory-list">${concerns}</ul></div>
    <div class="advisory-block"><strong>Recommendation:</strong> ${advisory.advisor_recommendation}</div>
  `;
}

function renderScenarios(scenarios) {
  if (!scenarios || scenarios.length === 0) return "";

  const rows = scenarios
    .map(
      (s) =>
        `<tr><td>${s.name}</td><td class="num">€${s.milk_price}</td>` +
        `<td class="num">${formatEuro(s.revenue)}</td>` +
        `<td class="num">${formatEuro(s.profit)}</td></tr>`
    )
    .join("");

  return `
    <table class="data-table">
      <thead>
        <tr><th>Scenario</th><th class="num">Milk Price</th><th class="num">Revenue</th><th class="num">Profit</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderCharts(charts) {
  if (!charts || Object.keys(charts).length === 0) return "";

  const cards = Object.entries(charts)
    .map(([type, path]) => {
      const url = chartUrl(path);
      return `
        <div class="chart-card">
          <div class="chart-card-header">
            <span>${chartLabel(type)}</span>
            <a href="${url}" target="_blank">Open full screen</a>
          </div>
          <iframe class="chart-iframe" src="${url}" title="${chartLabel(type)}"></iframe>
        </div>
      `;
    })
    .join("");

  return `<div class="charts-grid">${cards}</div>`;
}

function renderSingleFarm(result) {
  const summary = result.forecast_summary || {};
  const kpis = result.kpis || {};

  let html = `<h2 class="farm-title">${summary.farm_name || result.farm_file}</h2>`;
  html += renderKpiCards(summary, kpis, result.risk_level);

  if (result.alerts) {
    html += `<div class="result-section"><h3>Alerts</h3>${renderAlerts(result.alerts)}</div>`;
  }

  if (result.top_risk_drivers) {
    html += `<div class="result-section"><h3>Top Risk Drivers</h3>${renderRiskDrivers(result.top_risk_drivers)}</div>`;
  }

  if (result.advisory_summary) {
    html += `<div class="result-section"><h3>Advisory Summary</h3>${renderAdvisory(result.advisory_summary)}</div>`;
  }

  if (result.monthly_forecast) {
    html += `<div class="result-section"><h3>Monthly Cashflow Forecast</h3>${renderMonthlyTable(result.monthly_forecast)}</div>`;
  }

  if (result.scenarios) {
    html += `<div class="result-section"><h3>Scenarios</h3>${renderScenarios(result.scenarios)}</div>`;
  }

  if (result.profitability_dashboard) {
    const d = result.profitability_dashboard;
    html += `
      <div class="result-section">
        <h3>Profitability Dashboard</h3>
        <div class="kpi-grid">
          <div class="kpi-card"><div class="label">Revenue / Cow</div><div class="value">${formatEuro(d.revenue_per_cow)}</div></div>
          <div class="kpi-card"><div class="label">Cost / Cow</div><div class="value">${formatEuro(d.cost_per_cow)}</div></div>
          <div class="kpi-card"><div class="label">Profit / Cow</div><div class="value">${formatEuro(d.profit_per_cow)}</div></div>
          <div class="kpi-card"><div class="label">Feed Cost Ratio</div><div class="value">${formatPercent(d.feed_cost_ratio)}</div></div>
          <div class="kpi-card"><div class="label">Lowest Cash Balance</div><div class="value">${formatEuro(d.lowest_cash_balance)}</div></div>
          <div class="kpi-card"><div class="label">Lowest Balance Month</div><div class="value" style="font-size:1rem">${d.lowest_cash_balance_month}</div></div>
        </div>
      </div>
    `;
  }

  if (result.charts) {
    html += `<div class="result-section"><h3>Charts</h3>${renderCharts(result.charts)}</div>`;
  }

  return html;
}

// ---------------------------------------------------------------------------
// Render multi-farm comparison
// ---------------------------------------------------------------------------

function renderComparisonTable(comparison) {
  if (!comparison || comparison.length === 0) return "";

  // Find best profit for highlighting
  const maxProfit = Math.max(...comparison.map((r) => r.annual_profit || 0));

  const rows = comparison
    .map((row) => {
      const highlight = row.annual_profit === maxProfit ? "compare-best" : "";
      return `
        <tr class="${highlight}">
          <td><strong>${row.farm_name}</strong></td>
          <td class="num">${formatEuro(row.annual_profit)}</td>
          <td class="num">${formatPercent(row.profit_margin)}</td>
          <td><span class="risk-badge ${row.risk_level}">${row.risk_level || "—"}</span></td>
          <td class="num">${formatEuro(row.revenue_per_cow)}</td>
          <td class="num">${formatEuro(row.profit_per_cow)}</td>
          <td class="num">${formatPercent(row.feed_cost_ratio)}</td>
        </tr>
      `;
    })
    .join("");

  return `
    <table class="data-table">
      <thead>
        <tr>
          <th>Farm</th>
          <th class="num">Annual Profit</th>
          <th class="num">Profit Margin</th>
          <th>Risk Level</th>
          <th class="num">Revenue / Cow</th>
          <th class="num">Profit / Cow</th>
          <th class="num">Feed Cost Ratio</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function renderComparisonCards(comparison) {
  return comparison
    .map((row) => {
      return `
        <div class="result-section">
          <h3>${row.farm_name}</h3>
          <div class="kpi-grid">
            <div class="kpi-card"><div class="label">Annual Profit</div><div class="value">${formatEuro(row.annual_profit)}</div></div>
            <div class="kpi-card"><div class="label">Profit Margin</div><div class="value">${formatPercent(row.profit_margin)}</div></div>
            <div class="kpi-card ${riskClass(row.risk_level)}"><div class="label">Risk</div><div class="value">${row.risk_level}</div></div>
            <div class="kpi-card"><div class="label">Profit / Cow</div><div class="value">${formatEuro(row.profit_per_cow)}</div></div>
          </div>
        </div>
      `;
    })
    .join("");
}

function renderComparisonMode(data) {
  let html = `<h2 class="farm-title">Farm Comparison (${data.comparison.length} farms)</h2>`;

  html += `<div class="result-section"><h3>Comparison Table</h3>${renderComparisonTable(data.comparison)}</div>`;
  html += renderComparisonCards(data.comparison);

  // Show charts from each farm if generated
  data.results.forEach((result) => {
    if (result.charts && Object.keys(result.charts).length > 0) {
      const name = (result.forecast_summary || {}).farm_name || result.farm_file;
      html += `<div class="result-section"><h3>Charts — ${name}</h3>${renderCharts(result.charts)}</div>`;
    }
  });

  // Per-farm detail sections (alerts, advisory) when available
  data.results.forEach((result) => {
    const name = (result.forecast_summary || {}).farm_name || result.farm_file;

    if (result.alerts && result.alerts.length > 0) {
      html += `<div class="result-section"><h3>Alerts — ${name}</h3>${renderAlerts(result.alerts)}</div>`;
    }

    if (result.advisory_summary) {
      html += `<div class="result-section"><h3>Advisory — ${name}</h3>${renderAdvisory(result.advisory_summary)}</div>`;
    }
  });

  return html;
}

// ---------------------------------------------------------------------------
// Run analysis
// ---------------------------------------------------------------------------

async function runAnalysis() {
  const farms = getSelectedFarms();

  if (farms.length === 0) {
    showStatus("Please select at least one farm.", "error");
    return;
  }

  const outputs = getOutputOptions();
  const chartTypes = getChartTypes();

  if (outputs.charts && chartTypes.length === 0) {
    showStatus("Select at least one chart type, or disable chart generation.", "error");
    return;
  }

  const btn = document.getElementById("run-analysis-btn");
  btn.disabled = true;
  showStatus("Running analysis…", "loading");

  document.getElementById("welcome").classList.add("hidden");
  const resultsEl = document.getElementById("results");
  resultsEl.classList.add("hidden");
  resultsEl.innerHTML = "";

  try {
    const payload = {
      farm_files: farms,
      outputs: outputs,
      chart_types: chartTypes.length > 0 ? chartTypes : null,
      save_result: true,
    };

    const data = await apiFetch("/analyse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (data.mode === "single") {
      resultsEl.innerHTML = renderSingleFarm(data.results[0]);
    } else {
      resultsEl.innerHTML = renderComparisonMode(data);
    }

    resultsEl.classList.remove("hidden");
    hideStatus();
    showStatus(`Analysis complete — ${farms.length} farm(s) processed.`, "success");
  } catch (error) {
    showStatus("Error: " + error.message, "error");
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Sandbox
// ---------------------------------------------------------------------------

async function runSandbox() {
  const farmFile = document.getElementById("sandbox-farm").value;

  if (!farmFile) {
    showStatus("Select a farm for the sandbox.", "error");
    return;
  }

  const changes = {};
  const fields = [
    ["sandbox-milk-price", "milk_price"],
    ["sandbox-feed", "feed"],
    ["sandbox-fertiliser", "fertiliser"],
    ["sandbox-labour", "labour"],
    ["sandbox-loans", "loan_repayments"],
    ["sandbox-cows", "milking_cows"],
    ["sandbox-litres", "litres_per_cow"],
    ["sandbox-cash", "opening_cash_balance"],
  ];

  fields.forEach(([elementId, fieldName]) => {
    const value = document.getElementById(elementId).value;
    if (value !== "") {
      changes[fieldName] = elementId === "sandbox-cows"
        ? parseInt(value, 10)
        : parseFloat(value);
    }
  });

  if (Object.keys(changes).length === 0) {
    showStatus("Enter at least one sandbox change.", "error");
    return;
  }

  const btn = document.getElementById("run-sandbox-btn");
  btn.disabled = true;
  showStatus("Running sandbox forecast…", "loading");

  const resultsEl = document.getElementById("sandbox-results");
  resultsEl.classList.add("hidden");

  try {
    const data = await apiFetch("/sandbox", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        farm_file: farmFile,
        changes: changes,
        outputs: {
          forecast_summary: true,
          monthly_forecast: true,
          alerts: true,
          risk_level: true,
          top_risk_drivers: true,
          kpis: true,
        },
      }),
    });

    resultsEl.innerHTML =
      `<h3>Sandbox Results</h3>` +
      `<p><em>Original farm file was not modified.</em></p>` +
      renderSingleFarm(data);

    resultsEl.classList.remove("hidden");
    hideStatus();
    showStatus("Sandbox forecast complete.", "success");
  } catch (error) {
    showStatus("Sandbox error: " + error.message, "error");
  } finally {
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Initialise
// ---------------------------------------------------------------------------

document.getElementById("run-analysis-btn").addEventListener("click", runAnalysis);
document.getElementById("run-sandbox-btn").addEventListener("click", runSandbox);

loadFarms();
