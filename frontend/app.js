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

function renderAlerts(alerts, listId = "alerts-list") {
  const list = $(listId);
  if (!list) return;
  list.innerHTML = (alerts?.length ? alerts : ["No critical alerts right now."]).map((a) => `<li>${a}</li>`).join("");
}

function renderHealth(health) {
  const box = $("health-score");
  if (!box || !health) return;
  box.innerHTML = `
    <div class="health-score">${health.score} / 100</div>
    <div class="health-label">${health.label || "Good"}</div>
    <div class="health-rows">
      <div class="health-row"><span>Profitability</span><strong>${health.profitability}</strong></div>
      <div class="health-row"><span>Liquidity</span><strong>${health.liquidity}</strong></div>
      <div class="health-row"><span>Solvency</span><strong>${health.solvency}</strong></div>
      <div class="health-row"><span>Efficiency</span><strong>${health.efficiency}</strong></div>
    </div>`;
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
  const box = $("quick-actions");
  if (!box) return;
  const actions = [
    { icon: "◎", label: "Select Sectors", action: "focus-sectors" },
    { icon: "↗", label: "Run Advanced Forecast", view: "forecasts", trigger: "advanced" },
    { icon: "◆", label: "Open Scenario Sandbox", view: "scenarios" },
    { icon: "💡", label: "Ask AI Advisor", view: "intelligence" },
    { icon: "↑", label: "Upload Financial File", view: "settings" },
    { icon: "◎", label: "Run Monte Carlo Simulation", view: "forecasts", trigger: "monte" },
    { icon: "📄", label: "Generate Farmer Report", view: "reports" },
  ];
  box.innerHTML = actions.map((a) =>
    `<button type="button" class="qa-btn" data-view="${a.view || ""}" data-action="${a.action || ""}" data-trigger="${a.trigger || ""}"><span>${a.icon}</span>${a.label}</button>`
  ).join("");
  box.querySelectorAll(".qa-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.action === "focus-sectors") $("sector-select")?.scrollIntoView({ behavior: "smooth", block: "center" });
      else if (btn.dataset.view) {
        navigate(btn.dataset.view);
        if (btn.dataset.trigger === "advanced") runAdvancedForecast();
        if (btn.dataset.trigger === "monte") runMonteCarlo();
      }
    });
  });
}

function renderDashboardResults(data) {
  $("dashboard-empty")?.classList.add("hidden");
  $("dashboard-results")?.classList.remove("hidden");
  renderKpis(data.kpis);
  renderAlerts(data.alerts);
  renderAlerts(data.alerts, "alerts-full");
  renderHealth(data.health);
  renderRecommendations(data.recommendations);
  renderScenarios(data.scenario_snapshots);
  renderBarChart("chart-cashflow", data.cashflow_chart_data, ["cash_in", "cash_out"]);
  renderBarChart("chart-profit", data.profit_chart_data, ["profit"]);
  renderEngineCharts(data.charts);
  if ($("recent-updates")) {
    $("recent-updates").innerHTML = (data.recent_updates || []).map((u) =>
      `<li><strong>${u.label}</strong><br><span class="muted">${u.detail} · ${u.when}</span></li>`).join("");
  }
  if ($("upcoming-payments")) {
    $("upcoming-payments").innerHTML = (data.upcoming_payments || []).map((p) =>
      `<li><strong>${p.label}</strong> — €${Number(p.amount || 0).toLocaleString()} (${p.due})</li>`).join("");
  }
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
  const scenBox = $("forecast-scenarios");
  if (scenBox) {
    scenBox.innerHTML = (data.scenarios || []).map((s) =>
      `<div class="scenario-item"><strong>${s.name}</strong> — Profit €${Number(s.profit).toLocaleString()} @ €${s.milk_price}/L</div>`
    ).join("");
  }
}

function renderMonteCarlo(monte) {
  const box = $("monte-carlo-panel");
  if (!box || !monte) return;
  box.innerHTML = `
    <div class="health-rows">
      <div class="health-row"><span>Expected profit</span><strong>€${Number(monte.expected_profit || 0).toLocaleString()}</strong></div>
      <div class="health-row"><span>Best case (90th)</span><strong>€${Number(monte.best_case || 0).toLocaleString()}</strong></div>
      <div class="health-row"><span>Expected case</span><strong>€${Number(monte.expected_case || 0).toLocaleString()}</strong></div>
      <div class="health-row"><span>Worst case (10th)</span><strong>€${Number(monte.worst_case || 0).toLocaleString()}</strong></div>
      <div class="health-row"><span>Confidence range</span><strong>€${monte.confidence_range?.[0]?.toLocaleString()} – €${monte.confidence_range?.[1]?.toLocaleString()}</strong></div>
      <div class="health-row"><span>P(loss)</span><strong>${((monte.probability_of_loss || 0) * 100).toFixed(1)}%</strong></div>
    </div>
    <p class="muted" style="margin-top:0.75rem">${monte.interpretation || ""}</p>`;
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

function navigate(view) {
  state.view = view;
  document.querySelectorAll(".nav-link").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => { v.classList.remove("active"); v.classList.add("hidden"); });
  const section = $(`view-${view}`);
  if (section) { section.classList.add("active"); section.classList.remove("hidden"); }
  if (view === "intelligence") loadFinancialIntelligence();
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
  renderKpis(data.kpis);
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
  showStatus("Updating analysis for selected sectors…", "info");
  try {
    await refreshFarmData();
    if (state.view === "intelligence") await loadFinancialIntelligence();
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
  renderKpis(data.kpis);
  renderQuickActions();
}

async function runAnalysis(showMsg = true) {
  const btn = $("run-analysis-btn");
  if (btn) btn.disabled = true;
  if (showMsg) showStatus("Running analysis…", "info");
  try {
    const data = await api("/farmer/run-analysis", { method: "POST", headers: { "Content-Type": "application/json" }, body: sectorsBody() });
    state.analysis = data;
    state.profile = data.profile;
    state.selectedSectors = data.selected_sectors || state.selectedSectors;
    renderSidebar(data.profile);
    renderDashboardResults(data);
    if (showMsg) showStatus("Analysis complete.", "success");
  } catch (err) {
    if (showMsg) showStatus(err.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function runAdvancedForecast() {
  const btn = $("run-advanced-forecast-btn");
  if (btn) btn.disabled = true;
  showStatus("Running advanced forecast…", "info");
  try {
    const data = await api("/farmer/run-advanced-forecast", { method: "POST", headers: { "Content-Type": "application/json" }, body: sectorsBody() });
    renderForecastResults(data);
    showStatus("Advanced forecast complete.", "success");
  } catch (err) {
    showStatus(err.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function runMonteCarlo() {
  showStatus("Running Monte Carlo simulation…", "info");
  try {
    const data = await api("/farmer/run-monte-carlo", { method: "POST", headers: { "Content-Type": "application/json" }, body: sectorsBody({ iterations: 1000 }) });
    renderMonteCarlo(data.monte_carlo);
    $("forecast-results")?.classList.remove("hidden");
    showStatus("Monte Carlo complete.", "success");
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
    btn.addEventListener("click", () => navigate(btn.dataset.view));
  });
  $("run-analysis-btn")?.addEventListener("click", () => runAnalysis());
  $("run-advanced-forecast-btn")?.addEventListener("click", runAdvancedForecast);
  $("run-monte-carlo-btn")?.addEventListener("click", runMonteCarlo);
  $("run-sandbox-btn")?.addEventListener("click", runSandbox);
  $("sector-select")?.querySelectorAll("input[data-sector]").forEach((input) => {
    input.addEventListener("change", () => onSectorChange(input));
  });
  $("refresh-intelligence-btn")?.addEventListener("click", loadFinancialIntelligence);
  $("ask-advisor-btn")?.addEventListener("click", askAdvisor);
  $("advisor-question")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") askAdvisor();
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
