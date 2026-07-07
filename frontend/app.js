/**
 * FarmBiddy Farmer Edition — multi-sector dashboard (Dairy, Beef, Lamb)
 */

const API = "/api";
const ACTIVE_FARM_FILE = "multi_sector_farm.json";

let state = {
  profile: null,
  analysis: null,
  activeFarmFile: ACTIVE_FARM_FILE,
  selectedSectors: ["dairy", "beef", "lamb"],
  availableSectors: [],
  view: "dashboard",
};

const $ = (id) => document.getElementById(id);

function showStatus(msg, type = "info") {
  const bar = $("status-bar");
  if (!bar) return;
  bar.textContent = msg;
  bar.className = `status-bar ${type}`;
  bar.classList.remove("hidden");
}

function getSelectedSectorsFromUI() {
  const checked = [...document.querySelectorAll("#sector-select input[data-sector]:checked")]
    .map((el) => el.dataset.sector);
  return checked.length ? checked : ["dairy", "beef", "lamb"];
}

function sectorsQuery() {
  const params = new URLSearchParams();
  params.set("farm_file", state.activeFarmFile);
  if (state.selectedSectors.length) {
    params.set("sectors", state.selectedSectors.join(","));
  }
  return `?${params.toString()}`;
}

function sectorsBody(extra = {}) {
  return JSON.stringify({
    farm_file: state.activeFarmFile,
    sectors: state.selectedSectors,
    ...extra,
  });
}

async function api(path, options = {}) {
  const res = await fetch(API + path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

function setGreeting() {
  const hour = new Date().getHours();
  const name = state.profile?.owner_name?.split(" ")[0] || "Farmer";
  const greet = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  if ($("greeting")) $("greeting").textContent = `${greet}, ${name}!`;
  if ($("today-date")) {
    $("today-date").textContent = new Date().toLocaleDateString("en-IE", {
      weekday: "short", day: "numeric", month: "short", year: "numeric",
    });
  }
}

function renderSectorSelect(sectors) {
  const box = $("sector-select");
  if (!box || !sectors?.length) return;
  state.availableSectors = sectors;
  box.querySelectorAll("input[data-sector]").forEach((input) => {
    const info = sectors.find((s) => s.id === input.dataset.sector);
    if (info) {
      input.checked = info.selected;
      input.parentElement.querySelector("span").textContent = info.label;
    }
  });
  state.selectedSectors = getSelectedSectorsFromUI();
}

function sectorSummaryLabel() {
  const labels = {
    dairy: "Dairy",
    beef: "Beef",
    lamb: "Lamb",
  };
  return state.selectedSectors.map((id) => labels[id] || id).join(", ");
}

function renderSidebar(profile) {
  if (!profile) return;
  $("sf-farm-name").textContent = profile.farm_name || "My Farm";
  const sectors = sectorSummaryLabel();
  if (state.selectedSectors.includes("dairy") && profile.milking_cows) {
    $("sf-herd").textContent = `${profile.milking_cows} Milking Cows`;
    $("sf-milk").textContent = `Milk Price: €${Number(profile.milk_price || 0).toFixed(2)}/L`;
    $("sf-processor").textContent = `Processor: ${profile.milk_processor || "—"}`;
  } else {
    $("sf-herd").textContent = `Sectors: ${sectors}`;
    $("sf-milk").textContent = profile.farm_type ? `Type: ${profile.farm_type}` : "Mixed enterprise";
    $("sf-processor").textContent = `${state.selectedSectors.length} sector(s) selected`;
  }
  $("sf-updated").textContent = `Last Updated: ${profile.last_updated || "Today"}`;
  if ($("settings-farm")) $("settings-farm").textContent = profile.farm_name;
}

function renderProfileDetail(profile) {
  const box = $("farm-profile-detail");
  if (!box || !profile) return;
  const dairyRows = state.selectedSectors.includes("dairy") ? `
    <div class="profile-item"><span>Herd</span><strong>${profile.milking_cows || "—"} cows</strong></div>
    <div class="profile-item"><span>Milk price</span><strong>€${profile.milk_price || "—"}/L</strong></div>
    <div class="profile-item"><span>Processor</span><strong>${profile.milk_processor || "—"}</strong></div>` : "";
  box.innerHTML = `
    <div class="profile-item"><span>Farm</span><strong>${profile.farm_name}</strong></div>
    <div class="profile-item"><span>Sectors</span><strong>${sectorSummaryLabel()}</strong></div>
    <div class="profile-item"><span>Farm type</span><strong>${profile.farm_type || "Mixed"}</strong></div>
    ${dairyRows}
    <div class="profile-item"><span>Cash opening</span><strong>€${Number(profile.opening_cash_balance || 0).toLocaleString()}</strong></div>`;
}

function renderKpis(kpis, containerId = "kpi-row") {
  const row = $(containerId);
  if (!row || !kpis) return;
  row.innerHTML = kpis.map((k) => `
    <div class="kpi-card">
      <div class="kpi-title">${k.title}</div>
      <div class="kpi-value">${k.value}</div>
      <div class="kpi-sub ${k.trend === "down" ? "down" : k.trend === "neutral" ? "neutral" : ""}">${k.subtitle || ""}</div>
    </div>`).join("");
}

function renderMetricCards(items, containerId) {
  const box = $(containerId);
  if (!box) return;
  box.innerHTML = items.map((i) => `
    <div class="kpi-card">
      <div class="kpi-title">${i.label}</div>
      <div class="kpi-value">${i.value}</div>
      ${i.sub ? `<div class="kpi-sub">${i.sub}</div>` : ""}
    </div>`).join("");
}

function renderBarChart(containerId, data, keys) {
  const el = $(containerId);
  if (!el || !data?.length) {
    if (el) el.innerHTML = `<p class="muted">No chart data yet.</p>`;
    return;
  }
  const max = Math.max(...data.flatMap((d) => keys.map((k) => Math.abs(d[k] || 0))), 1);
  const barMaxPx = 150;
  el.innerHTML = `<div class="chart-bars">${data.slice(0, 12).map((d) => {
    const bars = keys.map((k) => {
      const h = Math.max(3, (Math.abs(d[k] || 0) / max) * barMaxPx);
      const cls = k.includes("out") || k === "costs" ? "bar-out" : k.includes("profit") || k === "net" ? "bar-profit" : "bar-in";
      return `<div class="bar ${cls}" style="height:${h}px" title="${k}: ${d[k]}"></div>`;
    }).join("");
    return `<div class="bar-group"><div class="bar-stack">${bars}</div><span class="bar-label">M${d.month}</span></div>`;
  }).join("")}</div>`;
}

function renderEngineCharts(charts, containerId = "engine-charts") {
  const box = $(containerId);
  if (!box) return;
  if (!charts || !Object.keys(charts).length) {
    box.innerHTML = `<p class="muted">Charts appear after analysis.</p>`;
    return;
  }
  box.innerHTML = Object.entries(charts).map(([name, path]) => {
    const file = path.replace(/\\/g, "/").split("/").pop();
    return `<iframe src="/chart-files/${file}" title="${name.replace(/_/g, " ")}"></iframe>`;
  }).join("");
}

function renderOverviewHeader(header) {
  const box = $("exec-overview-header");
  if (!box || !header) return;
  const badges = (header.sector_labels || []).map((l) =>
    `<span class="exec-sector-badge">${l}</span>`).join("");
  box.innerHTML = `
    <div>
      <h3>${header.farm_name || "My Farm"}</h3>
      <span class="exec-status-badge">${header.status_label || "Overview"}</span>
      <div class="exec-sector-badges">${badges}</div>
    </div>
    <div class="exec-meta">
      <div>Last updated: ${header.last_updated || "—"}</div>
      ${header.location ? `<div>${header.location}</div>` : ""}
    </div>`;
}

function renderHealthSnapshot(indicators) {
  const box = $("health-snapshot");
  if (!box) return;
  if (!indicators?.length) {
    box.innerHTML = `<p class="muted">Health indicators appear after analysis.</p>`;
    return;
  }
  box.innerHTML = indicators.map((ind) => `
    <div class="health-pill ${ind.colour || "amber"}">
      <div class="health-pill-label">${ind.label}</div>
      <div class="health-pill-status">${ind.status}</div>
    </div>`).join("");
}

function renderSectorTable(rows) {
  const box = $("sector-performance-table");
  if (!box) return;
  if (!rows?.length) {
    box.innerHTML = `<p class="muted">No sector data for current selection.</p>`;
    return;
  }
  const statusClass = (s) => `status-${(s || "").toLowerCase()}`;
  box.innerHTML = `
    <table class="sector-table">
      <thead>
        <tr><th>Sector</th><th>Revenue</th><th>Profit</th><th>Margin</th><th>Status</th></tr>
      </thead>
      <tbody>
        ${rows.map((r) => `
          <tr>
            <td><strong>${r.label}</strong></td>
            <td>€${Number(r.revenue || 0).toLocaleString()}</td>
            <td>€${Number(r.profit || 0).toLocaleString()}</td>
            <td>${r.margin_pct}%</td>
            <td class="${statusClass(r.status)}">${r.status}</td>
          </tr>`).join("")}
      </tbody>
    </table>`;
}

const MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatChartEuro(value) {
  return `€${Number(value || 0).toLocaleString("en-IE", { maximumFractionDigits: 0 })}`;
}

function formatOverviewMonthLabel(d) {
  if (d.period) {
    const parts = d.period.split("-");
    const year = parts[0] || "";
    const month = parseInt(parts[1], 10);
    if (month >= 1 && month <= 12) {
      return `${MONTH_SHORT[month - 1]} ${year.slice(-2)}`;
    }
  }
  return d.month ? `M${d.month}` : "";
}

function niceChartTicks(maxValue, count = 5) {
  if (maxValue <= 0) return [0];
  const rough = maxValue / count;
  const magnitude = Math.pow(10, Math.floor(Math.log10(rough)));
  const residual = rough / magnitude;
  let niceUnit = magnitude;
  if (residual > 5) niceUnit = 10 * magnitude;
  else if (residual > 2) niceUnit = 5 * magnitude;
  else if (residual > 1) niceUnit = 2 * magnitude;
  const ticks = [];
  for (let v = 0; v <= maxValue + niceUnit * 0.01; v += niceUnit) {
    ticks.push(v);
  }
  if (ticks[ticks.length - 1] < maxValue) ticks.push(ticks[ticks.length - 1] + niceUnit);
  return ticks;
}

function renderOverviewChart(data) {
  const el = $("overview-chart");
  if (!el || !data?.length) {
    if (el) el.innerHTML = `<p class="muted">No chart data yet.</p>`;
    return;
  }

  el._lastChartData = data;
  if (!el._resizeObs) {
    el._resizeObs = new ResizeObserver(() => {
      if (el._lastChartData) renderOverviewChart(el._lastChartData);
    });
    el._resizeObs.observe(el);
  }

  const width = Math.max(el.clientWidth || 0, 640);
  const height = 280;
  const padL = 68;
  const padR = 24;
  const padT = 36;
  const padB = 40;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const maxVal = Math.max(...data.flatMap((d) => [Math.abs(d.revenue || 0), Math.abs(d.costs || 0)]), 1);
  const yTicks = niceChartTicks(maxVal, 5);
  const yMax = yTicks[yTicks.length - 1] || maxVal;

  const n = data.length;
  const slotW = plotW / n;
  const barW = Math.min(11, Math.max(5, slotW * 0.28));
  const barGap = 3;

  const yScale = (v) => padT + plotH - (v / yMax) * plotH;

  const gridLines = yTicks.map((tick) => {
    const y = yScale(tick);
    return `<line class="overview-grid-line" x1="${padL}" y1="${y}" x2="${width - padR}" y2="${y}" />`;
  }).join("");

  const yLabels = yTicks.map((tick) => {
    const y = yScale(tick);
    return `<text class="overview-axis-y" x="${padL - 8}" y="${y + 4}" text-anchor="end">${formatChartEuro(tick)}</text>`;
  }).join("");

  const bars = data.map((d, i) => {
    const cx = padL + slotW * i + slotW / 2;
    const rev = Math.abs(d.revenue || 0);
    const cost = Math.abs(d.costs || 0);
    const revH = Math.max(2, (rev / yMax) * plotH);
    const costH = Math.max(2, (cost / yMax) * plotH);
    const revX = cx - barGap / 2 - barW;
    const costX = cx + barGap / 2;
    const baseY = padT + plotH;
    const label = formatOverviewMonthLabel(d);
    return `
      <g class="overview-bar-group" data-idx="${i}" tabindex="0">
        <rect class="overview-bar overview-bar-revenue" x="${revX}" y="${baseY - revH}" width="${barW}" height="${revH}" rx="3" ry="3" />
        <rect class="overview-bar overview-bar-costs" x="${costX}" y="${baseY - costH}" width="${barW}" height="${costH}" rx="3" ry="3" />
        <text class="overview-axis-x" x="${cx}" y="${height - 12}" text-anchor="middle">${label}</text>
      </g>`;
  }).join("");

  el.innerHTML = `
    <div class="overview-chart-wrap">
      <div class="overview-chart-legend" aria-hidden="true">
        <span class="overview-legend-item"><i class="overview-legend-swatch overview-legend-revenue"></i>Revenue</span>
        <span class="overview-legend-item"><i class="overview-legend-swatch overview-legend-costs"></i>Costs</span>
      </div>
      <svg class="overview-chart-svg" width="100%" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Revenue vs costs over 24 months">
        ${gridLines}
        ${yLabels}
        <line class="overview-axis-line" x1="${padL}" y1="${padT + plotH}" x2="${width - padR}" y2="${padT + plotH}" />
        ${bars}
      </svg>
      <div class="overview-chart-tooltip hidden" id="overview-chart-tooltip"></div>
    </div>`;

  const tooltip = el.querySelector("#overview-chart-tooltip");
  const showTooltip = (idx, clientX, clientY) => {
    const d = data[idx];
    if (!d || !tooltip) return;
    const rev = d.revenue || 0;
    const cost = d.costs || 0;
    const label = formatOverviewMonthLabel(d);
    tooltip.innerHTML = `
      <div class="overview-tooltip-month">${label}</div>
      <div class="overview-tooltip-row"><span>Revenue</span><strong>${formatChartEuro(rev)}</strong></div>
      <div class="overview-tooltip-row"><span>Costs</span><strong>${formatChartEuro(cost)}</strong></div>
      <div class="overview-tooltip-row overview-tooltip-diff"><span>Difference</span><strong>${formatChartEuro(rev - cost)}</strong></div>`;
    tooltip.classList.remove("hidden");
    const wrap = el.querySelector(".overview-chart-wrap");
    const rect = wrap.getBoundingClientRect();
    const left = Math.min(Math.max(clientX - rect.left + 12, 8), rect.width - 168);
    const top = Math.max(clientY - rect.top - 80, 8);
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  };

  const hideTooltip = () => tooltip?.classList.add("hidden");

  el.querySelectorAll(".overview-bar-group").forEach((group) => {
    group.addEventListener("mouseenter", (e) => showTooltip(+group.dataset.idx, e.clientX, e.clientY));
    group.addEventListener("mousemove", (e) => showTooltip(+group.dataset.idx, e.clientX, e.clientY));
    group.addEventListener("mouseleave", hideTooltip);
    group.addEventListener("focus", (e) => {
      const r = group.getBoundingClientRect();
      showTooltip(+group.dataset.idx, r.left + r.width / 2, r.top);
    });
    group.addEventListener("blur", hideTooltip);
  });
}

function renderExecutiveAlerts(alerts, listId = "alerts-list") {
  const list = $(listId);
  if (!list) return;
  const items = alerts?.length ? alerts : [{ message: "No critical alerts right now.", severity: "info" }];
  list.innerHTML = items.map((a) => {
    const msg = typeof a === "string" ? a : a.message;
    const sev = typeof a === "string" ? "medium" : (a.severity || "medium");
    return `<li class="alert-${sev}">${msg}</li>`;
  }).join("");
}

function renderExecutiveDashboard(data) {
  $("dashboard-empty")?.classList.add("hidden");
  $("dashboard-results")?.classList.remove("hidden");
  renderOverviewHeader(data.overview_header);
  renderKpis(data.executive_kpis || data.kpis);
  renderHealthSnapshot(data.health_snapshot);
  renderSectorTable(data.sector_performance);
  renderExecutiveAlerts(data.alerts);
  renderExecutiveAlerts(data.alerts, "alerts-full");
  updateAlertsNavHighlight(data.alerts);
  renderOverviewChart(data.overview_chart);
}

function renderRecommendations(recs, listId = "recommendations") {
  const list = $(listId);
  if (!list) return;
  list.innerHTML = (recs || []).map((r) =>
    `<li><strong>${r.title}</strong>${r.reason || r.description ? `<br><span class="muted">${r.reason || r.description}</span>` : ""}</li>`
  ).join("") || "<li>Run analysis to see recommendations.</li>";
}

function renderScenarios(snapshots) {
  const box = $("scenario-snapshots");
  if (!box) return;
  box.innerHTML = (snapshots || []).map((s) => `
    <div class="scenario-item">
      <strong>${s.label}</strong>
      Annual Profit: €${Number(s.annual_profit || 0).toLocaleString()} (${s.profit_impact || ""})
      <br><span class="muted">Risk: ${s.risk_level}</span>
    </div>`).join("");
}

function renderQuickActions() {
  // Quick actions removed from executive dashboard — navigation via sidebar only.
}

function renderForecastResults(data) {
  $("forecast-results")?.classList.remove("hidden");
  if ($("forecast-interpretation")) $("forecast-interpretation").textContent = data.interpretation || "";
  const s = data.forecast_summary || {};
  renderMetricCards([
    { label: "Annual Revenue", value: `€${Number(s.annual_revenue || 0).toLocaleString()}` },
    { label: "Annual Profit", value: `€${Number(s.annual_profit || 0).toLocaleString()}` },
    { label: "Profit Margin", value: `${s.profit_margin || 0}%` },
    { label: "Risk Level", value: data.risk_level || "—" },
  ], "forecast-kpis");
  renderBarChart("forecast-cashflow-chart", data.cashflow_chart_data, ["cash_in", "cash_out"]);
  renderBarChart("forecast-profit-chart", data.profit_chart_data, ["profit"]);
  renderEngineCharts(data.charts, "forecast-engine-charts");
  renderMonteCarlo(data.monte_carlo);
}

function renderMonteCarlo(monte) {
  const box = $("monte-carlo-panel");
  if (!box || !monte) return;
  const expected = Number(monte.expected_profit || 0);
  const low = Number(monte.worst_case ?? monte.confidence_range?.[0] ?? 0);
  const high = Number(monte.best_case ?? monte.confidence_range?.[1] ?? 0);
  const lossPct = ((monte.probability_of_loss || 0) * 100).toFixed(1);
  box.innerHTML = `
    <ul class="profit-outlook-list">
      <li>Expected profit is €${expected.toLocaleString()}</li>
      <li>It can range between €${low.toLocaleString()} and €${high.toLocaleString()}</li>
      <li>Probability of making a loss is ${lossPct}%.</li>
    </ul>
    ${monte.interpretation ? `<p class="muted profit-outlook-tip">${monte.interpretation}</p>` : ""}`;
}

function countActionableAlerts(alerts) {
  return (alerts || []).filter((a) => {
    const sev = typeof a === "string" ? "medium" : (a.severity || "medium");
    return sev !== "info";
  }).length;
}

function updateAlertsNavHighlight(alerts) {
  const btn = $("nav-alerts");
  if (!btn) return;
  const count = countActionableAlerts(alerts);
  btn.classList.remove("nav-alerts--warn-low", "nav-alerts--warn-mid", "nav-alerts--warn-high");
  btn.textContent = "Alerts";
  if (count >= 5) {
    btn.classList.add("nav-alerts--warn-high");
    btn.textContent = "⚠ Alerts";
  } else if (count >= 3) {
    btn.classList.add("nav-alerts--warn-mid");
  } else if (count >= 1) {
    btn.classList.add("nav-alerts--warn-low");
  }
}

function renderSandboxResults(data) {
  $("sandbox-results")?.classList.remove("hidden");
  if ($("sandbox-summary")) $("sandbox-summary").textContent = data.summary || "";
  const c = data.comparison || {};
  renderMetricCards([
    { label: "Profit (base)", value: `€${Number(c.profit_base || 0).toLocaleString()}` },
    { label: "Profit (scenario)", value: `€${Number(c.profit_scenario || 0).toLocaleString()}` },
    { label: "Difference", value: `€${Number(c.profit_difference || 0).toLocaleString()}`, sub: c.profit_difference >= 0 ? "Better" : "Worse" },
    { label: "Risk change", value: `${c.risk_base} → ${c.risk_scenario}` },
  ], "sandbox-comparison");
  const table = $("sandbox-table");
  if (table) {
    table.innerHTML = `<table class="data-table"><tbody>
      <tr><td>Revenue</td><td>€${Number(c.revenue_base).toLocaleString()}</td><td>€${Number(c.revenue_scenario).toLocaleString()}</td><td>€${Number(c.revenue_difference).toLocaleString()}</td></tr>
      <tr><td>Monthly profit</td><td>€${Number(c.monthly_profit_base).toLocaleString()}</td><td>€${Number(c.monthly_profit_scenario).toLocaleString()}</td><td>—</td></tr>
      <tr><td>Monthly cashflow</td><td>€${Number(c.monthly_cashflow_base).toLocaleString()}</td><td>€${Number(c.monthly_cashflow_scenario).toLocaleString()}</td><td>—</td></tr>
      <tr><td>Lowest cash</td><td>€${Number(c.min_cash_base).toLocaleString()}</td><td>€${Number(c.min_cash_scenario).toLocaleString()}</td><td>—</td></tr>
    </tbody></table>`;
  }
  renderRecommendations(data.recommendations, "sandbox-recommendations");
}

function getSandboxInputs() {
  const val = (id) => { const v = $(id)?.value; return v === "" || v == null ? undefined : parseFloat(v); };
  const intVal = (id) => { const v = $(id)?.value; return v === "" || v == null ? undefined : parseInt(v, 10); };
  return {
    milk_price_cents_change: val("sb-milk-cents") || 0,
    milk_price_pct_change: val("sb-milk-pct") || 0,
    feed_pct_change: val("sb-feed-pct") || 0,
    fertiliser_pct_change: val("sb-fert-pct") || 0,
    labour_pct_change: val("sb-labour-pct") || 0,
    vet_pct_change: val("sb-vet-pct") || 0,
    fuel_pct_change: val("sb-fuel-pct") || 0,
    electricity_pct_change: val("sb-elec-pct") || 0,
    loan_repayments: val("sb-loans"),
    milking_cows: intVal("sb-cows"),
    litres_per_cow: val("sb-litres"),
    opening_cash_balance: val("sb-cash"),
  };
}

const REPORT_SECTIONS = {
  full: [
    "Cover page and executive summary",
    "Farm profile and financial snapshot",
    "Profitability and cashflow charts",
    "12-month forecast and Monte Carlo",
    "Scenario comparison table",
    "Financial intelligence and recommendations",
    "Risk dashboard and 90-day action plan",
    "Investment readiness score",
  ],
  executive: [
    "Cover page and executive summary",
    "Financial intelligence highlights",
    "Top 5 recommended actions",
    "AI farm advisor summary",
  ],
  scenario: [
    "Executive summary",
    "Scenario comparison table and charts",
    "Risk dashboard",
    "Recommended actions",
  ],
  investment: [
    "Executive summary and financial snapshot",
    "Investment readiness score",
    "AI advisor summary for banks and investors",
  ],
};

function initReportDate() {
  const input = $("report-date");
  if (input && !input.value) {
    input.value = new Date().toISOString().slice(0, 10);
  }
}

function updateReportSections() {
  const type = $("report-type")?.value || "full";
  const list = $("report-sections");
  if (!list) return;
  list.innerHTML = (REPORT_SECTIONS[type] || REPORT_SECTIONS.full)
    .map((s) => `<li>${s}</li>`).join("");
}

function formatReportDate(isoDate) {
  if (!isoDate) return "";
  const d = new Date(isoDate + "T12:00:00");
  return d.toLocaleDateString("en-IE", { day: "numeric", month: "long", year: "numeric" });
}

function getReportParams() {
  const reportType = $("report-type")?.value || "full";
  const dateVal = $("report-date")?.value;
  const params = new URLSearchParams();
  params.set("farm_file", state.activeFarmFile);
  params.set("sectors", state.selectedSectors.join(","));
  params.set("report_type", reportType);
  if (dateVal) params.set("report_date", formatReportDate(dateVal));
  return {
    reportType,
    reportDate: dateVal ? formatReportDate(dateVal) : null,
    query: `?${params.toString()}`,
  };
}

function renderReportPreview(data, downloadUrl) {
  $("report-preview")?.classList.remove("hidden");
  if ($("report-preview-headline")) {
    $("report-preview-headline").textContent = `${data.report_type_label} — ${data.farm_name}`;
  }
  const k = data.kpis || {};
  const h = data.health_score || {};
  if ($("report-preview-kpis")) {
    $("report-preview-kpis").innerHTML = `
      <div class="kpi-card"><span class="kpi-label">Cash Available</span><span class="kpi-value">€${Number(k.cash_available || 0).toLocaleString()}</span></div>
      <div class="kpi-card"><span class="kpi-label">Annual Profit</span><span class="kpi-value">€${Number(k.annual_profit || 0).toLocaleString()}</span></div>
      <div class="kpi-card"><span class="kpi-label">Risk Level</span><span class="kpi-value">${k.risk_level || "—"}</span></div>
      <div class="kpi-card"><span class="kpi-label">Health Score</span><span class="kpi-value">${h.score ?? k.health_score ?? "—"}/100</span></div>`;
  }
  if ($("report-preview-summary")) {
    $("report-preview-summary").textContent = data.executive_summary || "";
  }
  const link = $("report-download-link");
  if (link && downloadUrl) {
    link.href = downloadUrl;
    link.classList.remove("hidden");
  } else if (link) {
    link.classList.add("hidden");
  }
}

async function previewReport() {
  const btn = $("preview-report-btn");
  if (btn) btn.disabled = true;
  setReportStatus("Building preview…");
  try {
    const { query } = getReportParams();
    const data = await api(`/farmer/report${query}`);
    renderReportPreview(data);
    setReportStatus(`Preview ready — ${data.page_count_estimate} sections planned.`, "success");
    showStatus("Report preview loaded.", "success");
  } catch (err) {
    setReportStatus(err.message, "error");
    showStatus(err.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function generateReport() {
  const btn = $("generate-report-btn");
  if (btn) btn.disabled = true;
  setReportStatus("Generating PDF report…");
  showStatus("Generating professional PDF…", "info");
  try {
    const { reportType, reportDate } = getReportParams();
    const data = await api("/farmer/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        farm_file: state.activeFarmFile,
        sectors: state.selectedSectors,
        report_type: reportType,
        report_date: reportDate,
      }),
    });
    renderReportPreview(data, data.download_url);
    setReportStatus(`PDF ready — ${data.page_count} pages. Downloading…`, "success");
    showStatus("Report generated successfully.", "success");
    window.open(data.download_url, "_blank");
  } catch (err) {
    setReportStatus(err.message, "error");
    showStatus(err.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function setReportStatus(msg, type = "info") {
  const el = $("report-status");
  if (!el) return;
  el.textContent = msg;
  el.className = `report-status ${type}`;
  el.classList.remove("hidden");
}

function sectorCacheKey() {
  return (state.selectedSectors || []).slice().sort().join(",");
}

function invalidateAdvancedForecast() {
  state.advancedForecast = null;
  state.advancedForecastKey = null;
}

async function ensureAdvancedForecast(showMsg = false) {
  const key = sectorCacheKey();
  if (state.advancedForecast && state.advancedForecastKey === key) {
    renderForecastResults(state.advancedForecast);
    return;
  }
  await runAdvancedForecast(showMsg);
}

const FARM_INTELLIGENCE_QUESTIONS = [
  "What happens if milk price increases by 5c/L?",
  "What happens if feed costs increase by 10%?",
  "How healthy is my business?",
  "What are my key strengths?",
  "What are my biggest financial risks?",
  "Where am I losing the most money?",
  "Which sector is performing best?",
  "How can I improve profitability?",
  "Will I need additional funding?",
  "What will my cashflow look like over the next 12 months?",
];

let fiBusy = false;
let fiHistory = [];
let fiLastQuestion = "";
let fiLastResponse = null;

const FI_SECTOR_LABELS = { dairy: "Dairy", beef: "Beef", lamb: "Lamb" };

function fiSectorLabel(sectorId) {
  return FI_SECTOR_LABELS[sectorId] || sectorId.charAt(0).toUpperCase() + sectorId.slice(1);
}

function buildFiFollowUps(data, lastQuestion) {
  const intent = data?.intent || "";
  const followUps = [];

  if (intent === "scenario_milk_price") {
    followUps.push("What if milk price increases by 3c/L?");
    followUps.push("What if milk price falls by 5c/L?");
  } else if (intent === "scenario_feed_cost") {
    followUps.push("What if feed costs increase by 5%?");
    followUps.push("What if feed costs increase by 15%?");
  } else if (intent === "scenario_labour_cost") {
    followUps.push("What if labour costs increase by 5%?");
  } else if (intent === "scenario_herd_size") {
    followUps.push("What if I add 25 cows?");
  } else if (intent === "health_score") {
    followUps.push("What are my biggest financial risks?");
    followUps.push("What will my cashflow look like over the next 12 months?");
  } else if (intent === "risks") {
    followUps.push("How can I improve profitability?");
  } else if (intent === "profitability") {
    followUps.push("Which sector is performing best?");
  } else if (intent === "cashflow_forecast") {
    followUps.push("Will I need additional funding?");
  }

  if (lastQuestion) {
    followUps.push(`Explain in simpler terms: ${lastQuestion}`);
  }
  followUps.push("What should I do next?");

  return [...new Set(followUps)].slice(0, 4);
}

function appendFiFollowUps(body, followUps) {
  if (!followUps.length) return;
  const row = document.createElement("div");
  row.className = "fi-followups";
  followUps.forEach((question) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "fi-followup-btn";
    btn.title = question;
    btn.textContent = question.length > 52 ? `${question.slice(0, 49)}…` : question;
    btn.addEventListener("click", () => {
      askFarmIntelligence(question);
    });
    row.appendChild(btn);
  });
  body.appendChild(row);
}

function clearFiChat(showNotice = false) {
  fiHistory = [];
  fiLastQuestion = "";
  fiLastResponse = null;
  const messages = $("fi-messages");
  if (messages) {
    messages.innerHTML = "";
    messages.classList.add("hidden");
  }
  $("fi-empty")?.classList.remove("hidden");
  if ($("fi-question")) $("fi-question").value = "";
  if (showNotice) showStatus("Chat cleared — selected sectors changed.", "info");
}

function formatFiSectorCallout(data) {
  if (data.scope_summary) {
    return data.scope_summary;
  }

  const intent = data.intent || "";
  const affected = data.affected_sectors || [];
  const unaffected = data.unaffected_sectors || [];

  if (intent === "funding_need") {
    return "This applies to your whole farm.";
  }
  if (!intent.startsWith("scenario_")) {
    return "";
  }
  if (intent === "scenario_milk_price" && !affected.length) {
    return "Dairy is not in your selected sectors — milk price changes would not apply.";
  }
  const parts = [];
  if (affected.length) {
    parts.push(`Direct impact: ${affected.map(fiSectorLabel).join(", ")} only.`);
  }
  if (unaffected.length) {
    parts.push(`${unaffected.map(fiSectorLabel).join(" and ")} not directly affected.`);
  }
  return parts.join(" ");
}

function formatFiMetrics(metrics) {
  if (!metrics) return [];
  const items = [];
  if (metrics.health_score != null) {
    items.push({ label: "Health score", value: `${metrics.health_score}/100` });
  }
  if (metrics.profit_change != null) {
    items.push({ label: "Profit change", value: `€${Number(metrics.profit_change).toLocaleString("en-IE")}` });
  }
  if (metrics.cashflow_change != null) {
    items.push({
      label: "Cashflow",
      value: `€${Number(metrics.cashflow_change).toLocaleString("en-IE")}/mo`,
    });
  }
  if (metrics.risk_level) {
    items.push({ label: "Risk", value: metrics.risk_level });
  }
  return items;
}

function scrollFiChat() {
  const chat = $("fi-chat");
  if (chat) chat.scrollTop = chat.scrollHeight;
}

function appendFiUserMessage(question) {
  $("fi-empty")?.classList.add("hidden");
  const messages = $("fi-messages");
  if (!messages) return;
  messages.classList.remove("hidden");

  const wrap = document.createElement("div");
  wrap.className = "fi-message fi-message-user";
  wrap.innerHTML = '<div class="fi-message-label">You</div>';
  const body = document.createElement("div");
  body.className = "fi-message-body";
  body.textContent = question;
  wrap.appendChild(body);
  messages.appendChild(wrap);
  scrollFiChat();
}

function appendFiLoadingMessage() {
  const messages = $("fi-messages");
  if (!messages) return;
  const wrap = document.createElement("div");
  wrap.className = "fi-message fi-message-advisor";
  wrap.id = "fi-loading-msg";
  wrap.innerHTML = '<div class="fi-message-label">Farm Intelligence</div>';
  const body = document.createElement("div");
  body.className = "fi-message-body fi-loading-text";
  body.textContent = "Analysing your question…";
  wrap.appendChild(body);
  messages.appendChild(wrap);
  scrollFiChat();
}

function removeFiLoadingMessage() {
  $("fi-loading-msg")?.remove();
}

function renderFiAdvisorAnswer(data) {
  const messages = $("fi-messages");
  if (!messages) return;

  const wrap = document.createElement("div");
  wrap.className = "fi-message fi-message-advisor";
  wrap.innerHTML = '<div class="fi-message-label">Farm Intelligence</div>';

  const body = document.createElement("div");
  body.className = "fi-message-body fi-answer-card";

  const callout = formatFiSectorCallout(data);
  if (callout) {
    const sectorEl = document.createElement("div");
    sectorEl.className = "fi-sector-callout";
    sectorEl.textContent = callout;
    body.appendChild(sectorEl);
  }

  const summary = document.createElement("p");
  summary.className = "fi-summary";
  summary.textContent = data.summary || "No summary available.";
  body.appendChild(summary);

  if (data.key_points?.length) {
    const details = document.createElement("details");
    details.className = "fi-details";
    const summaryToggle = document.createElement("summary");
    summaryToggle.textContent = `Show ${data.key_points.length} key point${data.key_points.length === 1 ? "" : "s"}`;
    details.appendChild(summaryToggle);
    const list = document.createElement("ul");
    list.className = "fi-key-points";
    data.key_points.slice(0, 5).forEach((point) => {
      const item = document.createElement("li");
      item.textContent = point;
      list.appendChild(item);
    });
    details.appendChild(list);
    body.appendChild(details);
  }

  const metricItems = formatFiMetrics(data.metrics);
  if (metricItems.length) {
    const row = document.createElement("div");
    row.className = "fi-metrics-row";
    metricItems.forEach(({ label, value }) => {
      const chip = document.createElement("div");
      chip.className = "fi-metric-chip";
      chip.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
      row.appendChild(chip);
    });
    body.appendChild(row);
  }

  if (data.recommendation) {
    const rec = document.createElement("div");
    rec.className = "fi-recommendation";
    rec.textContent = `Recommendation: ${data.recommendation}`;
    body.appendChild(rec);
  }

  appendFiFollowUps(body, buildFiFollowUps(data, fiLastQuestion));

  wrap.appendChild(body);
  messages.appendChild(wrap);
  scrollFiChat();
}

function renderFiAdvisorError(message) {
  const messages = $("fi-messages");
  if (!messages) return;

  const wrap = document.createElement("div");
  wrap.className = "fi-message fi-message-advisor";
  wrap.innerHTML = '<div class="fi-message-label">Farm Intelligence</div>';
  const body = document.createElement("div");
  body.className = "fi-message-body fi-error";
  body.textContent = message || "Something went wrong. Please try again.";
  wrap.appendChild(body);
  messages.appendChild(wrap);
  scrollFiChat();
}

function setFiBusy(busy) {
  fiBusy = busy;
  const askBtn = $("fi-ask-btn");
  const clearBtn = $("fi-clear-btn");
  if (askBtn) askBtn.disabled = busy;
  if (clearBtn) clearBtn.disabled = busy;
  document.querySelectorAll(".fi-suggestion-btn, .fi-followup-btn").forEach((btn) => {
    btn.disabled = busy;
  });
}

async function askFarmIntelligence(question) {
  const q = (question || $("fi-question")?.value || "").trim();
  if (!q || fiBusy) return;

  setFiBusy(true);
  if ($("fi-question")) $("fi-question").value = "";
  fiLastQuestion = q;
  appendFiUserMessage(q);
  appendFiLoadingMessage();

  try {
    const data = await api("/farmer/advisor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: sectorsBody({ question: q }),
    });
    removeFiLoadingMessage();
    fiLastResponse = data;
    fiHistory.push({ question: q, response: data });
    renderFiAdvisorAnswer(data);
  } catch (err) {
    removeFiLoadingMessage();
    fiHistory.push({ question: q, error: err.message });
    renderFiAdvisorError(err.message);
    showStatus(err.message, "error");
  } finally {
    setFiBusy(false);
  }
}

function initFarmIntelligencePage() {
  const box = $("fi-suggestions");
  if (!box || box.dataset.initialized) return;
  box.dataset.initialized = "1";
  box.innerHTML = FARM_INTELLIGENCE_QUESTIONS.map(
    (q) => `<button type="button" class="fi-suggestion-btn" data-question="${q.replace(/"/g, "&quot;")}">${q}</button>`,
  ).join("");
  box.querySelectorAll(".fi-suggestion-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const question = btn.dataset.question || btn.textContent;
      askFarmIntelligence(question);
    });
  });
}

async function navigate(view) {
  state.view = view;
  document.querySelectorAll(".nav-link").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => { v.classList.remove("active"); v.classList.add("hidden"); });
  const section = $(`view-${view}`);
  if (section) { section.classList.add("active"); section.classList.remove("hidden"); }
  if (view === "forecasts") await ensureAdvancedForecast();
  if (view === "farm-intelligence") initFarmIntelligencePage();
  if (view === "intelligence") await loadFinancialIntelligence();
  if (view === "historical") await loadHistoricalData();
  if (view === "reports") {
    initReportDate();
    updateReportSections();
  }
}

function renderFinancialIntelligence(data) {
  $("intelligence-loading")?.classList.add("hidden");
  $("intelligence-content")?.classList.remove("hidden");

  const h = data.health_score || {};
  if ($("intel-summary")) $("intel-summary").textContent = data.advisor_headline || data.plain_summary || "";
  if ($("intel-plain")) $("intel-plain").textContent = data.plain_summary || "";

  const healthBox = $("intel-health");
  if (healthBox) {
    healthBox.innerHTML = `
      <div class="health-score">${h.score ?? "—"} / 100</div>
      <div class="health-label">${h.label || "—"}</div>
      <div class="health-rows">
        <div class="health-row"><span>Profitability</span><strong>${h.profitability || "—"}</strong></div>
        <div class="health-row"><span>Cashflow</span><strong>${h.cashflow || "—"}</strong></div>
        <div class="health-row"><span>Feed pressure</span><strong>${h.feed_pressure || "—"}</strong></div>
        <div class="health-row"><span>Debt pressure</span><strong>${h.debt_pressure || "—"}</strong></div>
        <div class="health-row"><span>Risk level</span><strong>${h.risk_level || "—"}</strong></div>
      </div>`;
  }

  const listHtml = (items) => (items?.length ? items.map((i) => `<li>${i}</li>`).join("") : "<li>None flagged — keep monitoring.</li>");
  if ($("intel-strengths")) $("intel-strengths").innerHTML = listHtml(data.key_strengths);
  if ($("intel-weaknesses")) $("intel-weaknesses").innerHTML = listHtml(data.key_weaknesses);
  if ($("intel-opportunities")) $("intel-opportunities").innerHTML = listHtml(data.opportunities);

  const risksBox = $("intel-risks");
  if (risksBox) {
    risksBox.innerHTML = (data.biggest_risks || []).map((r) => `
      <div class="scenario-item">
        <strong>${r.driver}</strong> — ${r.severity}
        ${r.commentary ? `<br><span class="muted">${r.commentary}</span>` : ""}
      </div>`).join("") || "<p class='muted'>No major risks identified.</p>";
  }

  renderRecommendations(data.recommended_actions, "intel-actions");
}

function renderHistoricalData(data) {
  $("historical-loading")?.classList.add("hidden");
  $("historical-content")?.classList.remove("hidden");
  const box = $("historical-content");
  if (!box) return;

  const renderTable = (rows, title) => {
    if (!rows?.length) return "";
    return `
      <div class="historical-sector-block">
        <h4>${title}</h4>
        <div class="table-wrap">
          <table class="sector-table">
            <thead><tr><th>Period</th><th>Revenue</th><th>Costs</th><th>Profit</th></tr></thead>
            <tbody>
              ${rows.map((r) => `
                <tr>
                  <td>${r.period}</td>
                  <td>€${Number(r.revenue || 0).toLocaleString()}</td>
                  <td>€${Number(r.costs || 0).toLocaleString()}</td>
                  <td>€${Number((r.revenue || 0) - (r.costs || 0)).toLocaleString()}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>
      </div>`;
  };

  let html = renderTable(data.combined_monthly, "Combined (selected sectors)");
  (data.sectors || []).forEach((s) => {
    html += renderTable(s.monthly, `${s.label} — totals: €${Number(s.totals?.revenue || 0).toLocaleString()} revenue`);
  });
  box.innerHTML = html || `<p class="muted">No historical data available.</p>`;
}

async function loadHistoricalData() {
  $("historical-loading")?.classList.remove("hidden");
  $("historical-content")?.classList.add("hidden");
  try {
    const data = await api(`/farmer/historical-data${sectorsQuery()}`);
    renderHistoricalData(data);
  } catch (err) {
    if ($("historical-loading")) $("historical-loading").textContent = `Could not load: ${err.message}`;
    showStatus(err.message, "error");
  }
}

async function loadFinancialIntelligence() {
  $("intelligence-loading")?.classList.remove("hidden");
  $("intelligence-content")?.classList.add("hidden");
  try {
    const data = await api(`/farmer/financial-intelligence${sectorsQuery()}`);
    state.intelligence = data;
    renderFinancialIntelligence(data);
  } catch (err) {
    if ($("intelligence-loading")) $("intelligence-loading").textContent = `Could not load: ${err.message}`;
    showStatus(err.message, "error");
  }
}

async function askAdvisor() {
  const question = $("advisor-question")?.value?.trim();
  if (!question) {
    showStatus("Type a question first.", "error");
    return;
  }
  const btn = $("ask-advisor-btn");
  if (btn) btn.disabled = true;
  try {
    const data = await api("/farmer/ask-advisor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        farm_file: state.activeFarmFile,
        sectors: state.selectedSectors,
      }),
    });
    const box = $("advisor-answer");
    if (box) {
      box.classList.remove("hidden");
      box.innerHTML = `
        <p><strong>Q:</strong> ${data.question}</p>
        <p><strong>A:</strong> ${data.answer}</p>
        ${(data.details || []).map((d) => `<p class="muted">${d}</p>`).join("")}`;
    }
    showStatus("Answer ready.", "success");
  } catch (err) {
    showStatus(err.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function refreshFarmData() {
  const data = await api(`/farmer/dashboard${sectorsQuery()}`);
  state.profile = data.profile;
  state.selectedSectors = data.selected_sectors || state.selectedSectors;
  renderSectorSelect(data.available_sectors);
  setGreeting();
  renderSidebar(data.profile);
  renderProfileDetail(data.profile);
  renderKpis(data.executive_kpis || data.kpis);
  if (data.overview_header) renderOverviewHeader(data.overview_header);
  if (state.analysis) await runAnalysis(false);
}

async function onSectorChange(changedInput) {
  const selected = getSelectedSectorsFromUI();
  if (!selected.length) {
    changedInput.checked = true;
    showStatus("At least one sector must be selected.", "error");
    return;
  }
  state.selectedSectors = selected;
  invalidateAdvancedForecast();
  showStatus("Updating analysis for selected sectors…", "info");
  try {
    await refreshFarmData();
    if (state.view === "intelligence") await loadFinancialIntelligence();
    if (state.view === "farm-intelligence") clearFiChat(true);
    if (state.view === "forecasts") await ensureAdvancedForecast();
    if (state.view === "historical") await loadHistoricalData();
    if (state.view === "reports") $("report-preview")?.classList.add("hidden");
    showStatus(`Analyzing: ${sectorSummaryLabel()}`, "success");
  } catch (err) {
    showStatus(err.message, "error");
  }
}

async function loadInitial() {
  const data = await api(`/farmer/dashboard${sectorsQuery()}`);
  state.selectedSectors = data.selected_sectors || state.selectedSectors;
  renderSectorSelect(data.available_sectors);
  state.profile = data.profile;
  setGreeting();
  renderSidebar(data.profile);
  renderProfileDetail(data.profile);
  renderKpis(data.executive_kpis || data.kpis);
  if (data.overview_header) renderOverviewHeader(data.overview_header);
  await runAnalysis(false);
}

async function runAnalysis(showMsg = true) {
  if (showMsg) showStatus("Running analysis…", "info");
  try {
    const data = await api("/farmer/run-analysis", { method: "POST", headers: { "Content-Type": "application/json" }, body: sectorsBody() });
    state.analysis = data;
    invalidateAdvancedForecast();
    state.profile = data.profile;
    state.selectedSectors = data.selected_sectors || state.selectedSectors;
    renderSidebar(data.profile);
    renderExecutiveDashboard(data);
    if (showMsg) showStatus("Analysis complete.", "success");
  } catch (err) {
    showStatus(err.message, "error");
  }
}

async function runAdvancedForecast(showMsg = true) {
  if (showMsg) showStatus("Running advanced forecast…", "info");
  try {
    const data = await api("/farmer/run-advanced-forecast", { method: "POST", headers: { "Content-Type": "application/json" }, body: sectorsBody() });
    state.advancedForecast = data;
    state.advancedForecastKey = sectorCacheKey();
    renderForecastResults(data);
    if (showMsg) showStatus("Advanced forecast complete.", "success");
  } catch (err) {
    showStatus(err.message, "error");
  }
}

async function runSandbox() {
  const btn = $("run-sandbox-btn");
  if (btn) btn.disabled = true;
  showStatus("Running scenario…", "info");
  try {
    const data = await api("/farmer/scenario-sandbox", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: sectorsBody(getSandboxInputs()),
    });
    renderSandboxResults(data);
    showStatus("Scenario complete.", "success");
  } catch (err) {
    showStatus(err.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function setupNav() {
  document.querySelectorAll(".nav-link").forEach((btn) => {
    btn.addEventListener("click", () => {
      navigate(btn.dataset.view).catch((err) => showStatus(err.message, "error"));
    });
  });
  $("run-sandbox-btn")?.addEventListener("click", runSandbox);
  $("sector-select")?.querySelectorAll("input[data-sector]").forEach((input) => {
    input.addEventListener("change", () => onSectorChange(input));
  });
  $("ask-advisor-btn")?.addEventListener("click", askAdvisor);
  $("advisor-question")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") askAdvisor();
  });
  $("fi-ask-btn")?.addEventListener("click", () => askFarmIntelligence());
  $("fi-clear-btn")?.addEventListener("click", () => clearFiChat());
  $("fi-question")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") askFarmIntelligence();
  });
  $("preview-report-btn")?.addEventListener("click", previewReport);
  $("generate-report-btn")?.addEventListener("click", generateReport);
  $("report-type")?.addEventListener("change", updateReportSections);
  initReportDate();
  updateReportSections();
}

document.addEventListener("DOMContentLoaded", () => {
  setupNav();
  loadInitial().catch((err) => showStatus(err.message, "error"));
});
