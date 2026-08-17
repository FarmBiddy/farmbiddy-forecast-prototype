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
  view: "overview",
  activeSubtab: null,
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
    $("sf-milk").textContent = `Milk Price: ${formatCurrency(profile.milk_price, { decimals: 2 })}/L`;
    $("sf-processor").textContent = `Processor: ${profile.milk_processor || "—"}`;
  } else {
    $("sf-herd").textContent = `Sectors: ${sectors}`;
    $("sf-milk").textContent = profile.farm_type ? `Type: ${profile.farm_type}` : "Mixed enterprise";
    $("sf-processor").textContent = `${state.selectedSectors.length} sector(s) selected`;
  }
  $("sf-updated").textContent = `Last Updated: ${profile.last_updated || "Today"}`;
  if ($("settings-farm")) $("settings-farm").textContent = profile.farm_name;
}

function profileItem(label, value) {
  return `<div class="profile-item"><span>${label}</span><strong>${value ?? "—"}</strong></div>`;
}

function profileSection(title, itemsHtml) {
  if (!itemsHtml) return "";
  return `<div class="profile-section"><h4 class="profile-section-title">${title}</h4><div class="profile-section-grid">${itemsHtml}</div></div>`;
}

function formatNum(n) {
  if (n == null || n === "") return "—";
  return Number(n).toLocaleString();
}

/**
 * Shared currency formatter (Phase 9 / UX items 11-12).
 * Always shows negative values as "-€1,234" (sign before the symbol),
 * never "€-1,234", and defaults to whole euros unless `decimals` is set
 * (e.g. milk/lamb prices per litre/kg use 2-3 decimals).
 */
function formatCurrency(value, { decimals = 0 } = {}) {
  const num = Number(value);
  if (value == null || value === "" || !Number.isFinite(num)) return "—";
  const sign = num < 0 ? "-" : "";
  const abs = Math.abs(num);
  return `${sign}€${abs.toLocaleString("en-IE", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

/** Shared percentage formatter — one decimal place everywhere by default. */
function formatPercent(value, { decimals = 1 } = {}) {
  const num = Number(value);
  if (value == null || value === "" || !Number.isFinite(num)) return "—";
  return `${num.toFixed(decimals)}%`;
}

/** Class name for consistent positive/negative colouring on change-style figures. */
function signClass(value) {
  const num = Number(value);
  if (!Number.isFinite(num) || num === 0) return "";
  return num > 0 ? "positive" : "negative";
}

function renderProfileDetail(profile) {
  const box = $("farm-profile-detail");
  if (!box || !profile) return;
  const sectors = profile.sector_profile || {};
  const land = profile.land_by_sector || {};
  const selected = profile.selected_sectors || state.selectedSectors || [];

  const general = [
    profileItem("Farm", profile.farm_name),
    profileItem("Owner", profile.owner_name),
    profileItem("Location", profile.county || profile.location),
    profileItem("Herd no.", profile.herd_number),
    profileItem("Farm size", profile.total_hectares != null ? `${profile.total_hectares} ha` : "—"),
    profileItem("Sectors", sectorSummaryLabel()),
    profileItem("Farm type", profile.farm_type || "Mixed"),
    profileItem("Cash opening", formatCurrency(profile.opening_cash_balance)),
  ].join("");

  let dairy = "";
  if (selected.includes("dairy") && sectors.dairy) {
    const d = sectors.dairy;
    dairy = [
      profileItem("Milking cows", d.milking_cows != null ? `${d.milking_cows} cows` : "—"),
      profileItem("Litres per cow", d.litres_per_cow != null ? `${formatNum(d.litres_per_cow)} L/yr` : "—"),
      profileItem("Annual milk litres", d.annual_milk_litres != null ? `${formatNum(d.annual_milk_litres)} L` : "—"),
      profileItem("Milk price", d.milk_price != null ? `${formatCurrency(d.milk_price, { decimals: 3 })}/L` : "—"),
      profileItem("Processor", d.processor),
      profileItem("Dry cows", d.dry_cows),
      profileItem("Replacement heifers", d.replacement_heifers),
      profileItem("Calves", d.calves),
      profileItem("Milk solids bonus", d.milk_solids_bonus_per_litre != null ? `${formatCurrency(d.milk_solids_bonus_per_litre, { decimals: 3 })}/L` : "—"),
    ].join("");
  }

  let beef = "";
  if (selected.includes("beef") && sectors.beef) {
    const b = sectors.beef;
    beef = [
      profileItem("Cattle on farm", b.cattle_on_farm),
      profileItem("Finishing units", b.finishing_units),
      profileItem("Beef sale price", b.avg_sale_price_per_head != null ? `${formatCurrency(b.avg_sale_price_per_head)}/head` : "—"),
    ].join("");
  }

  let lamb = "";
  if (selected.includes("lamb") && sectors.lamb) {
    const l = sectors.lamb;
    lamb = [
      profileItem("Ewes", l.ewes),
      profileItem("Lambs on farm", l.lambs_on_farm),
      profileItem("Lamb price", l.avg_lamb_price_per_kg != null ? `${formatCurrency(l.avg_lamb_price_per_kg, { decimals: 2 })}/kg` : "—"),
      profileItem("Lambs sold (12 mo)", l.lambs_sold_trailing_12),
    ].join("");
  }

  const landRows = [
    selected.includes("dairy") && land.dairy != null ? profileItem("Dairy land", `${land.dairy} ha`) : "",
    selected.includes("beef") && land.beef != null ? profileItem("Beef land", `${land.beef} ha`) : "",
    selected.includes("lamb") && land.lamb != null ? profileItem("Lamb land", `${land.lamb} ha`) : "",
  ].filter(Boolean).join("");
  const landSection = landRows ? profileSection("Land use", landRows) : "";

  box.innerHTML = [
    profileSection("General", general),
    profileSection("Dairy", dairy),
    profileSection("Beef", beef),
    profileSection("Lamb / Sheep", lamb),
    landSection,
  ].filter(Boolean).join("");
}

function renderKpis(kpis, containerId = "kpi-row") {
  const row = $(containerId);
  if (!row || !kpis) return;
  row.innerHTML = kpis.map((k) => `
    <div class="kpi-card">
      <div class="kpi-title-row">
        <div class="kpi-title">${k.title}</div>
        ${periodBadgeHtml(k.period)}
      </div>
      <div class="kpi-value">${k.value}</div>
      <div class="kpi-sub ${k.trend === "down" ? "down" : k.trend === "neutral" ? "neutral" : ""}">${k.subtitle || ""}</div>
    </div>`).join("");
}

function renderMetricCards(items, containerId) {
  const box = $(containerId);
  if (!box) return;
  box.innerHTML = items.map((i) => `
    <div class="kpi-card">
      <div class="kpi-title-row">
        <div class="kpi-title">${i.label}</div>
        ${periodBadgeHtml(i.period)}
      </div>
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

function renderHealthScoreDetail(health) {
  const box = $("health-score-detail");
  if (!box) return;
  if (!health || health.score == null) {
    box.innerHTML = `<p class="muted">Score breakdown appears after analysis.</p>`;
    return;
  }
  const rows = [
    ["Profitability", health.profitability],
    ["Cashflow", health.cashflow],
    ["Feed pressure", health.feed_pressure],
    ["Debt pressure", health.debt_pressure],
    ["Risk level", health.risk_level],
  ];
  const goodOnes = rows.filter(([, v]) => v === "Good" || v === "Low").map(([label]) => label);
  const attentionOnes = rows.filter(([, v]) => v === "Weak" || v === "Negative" || v === "High" || v === "Needs attention").map(([label]) => label);

  box.innerHTML = `
    <div class="health-detail-toggle-row">
      <button type="button" id="health-detail-toggle" class="link-btn">What's affecting this score? ▾</button>
    </div>
    <div id="health-detail-body" class="health-detail-body hidden">
      <div class="health-detail-score">${health.score}/100 — ${health.label}</div>
      <table class="data-table health-detail-table">
        <tbody>
          ${rows.map(([label, value]) => `<tr><td>${label}</td><td>${value ?? "—"}</td></tr>`).join("")}
        </tbody>
      </table>
      <p class="muted">
        ${goodOnes.length ? `Performing well: ${goodOnes.join(", ")}. ` : ""}
        ${attentionOnes.length ? `Needs attention: ${attentionOnes.join(", ")}. ` : ""}
        ${!goodOnes.length && !attentionOnes.length ? "All factors are within a moderate range." : ""}
      </p>
      <p class="muted">Based on profit margin, risk level, feed cost ratio, monthly cashflow, opening cash balance, and loan repayments from your current analysis.</p>
    </div>`;

  $("health-detail-toggle")?.addEventListener("click", () => {
    const body = $("health-detail-body");
    const btn = $("health-detail-toggle");
    const expanded = !body.classList.contains("hidden");
    body.classList.toggle("hidden");
    if (btn) btn.textContent = expanded ? "What's affecting this score? ▾" : "What's affecting this score? ▴";
  });
}

function renderSectorTable(rows) {
  const box = $("sector-performance-table");
  if (!box) return;
  const periodSlot = $("sector-performance-period");
  if (periodSlot) periodSlot.innerHTML = periodBadgeHtml(rows?.[0]?.period);
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
            <td>${formatCurrency(r.revenue)}</td>
            <td class="${signClass(r.profit)}">${formatCurrency(r.profit)}</td>
            <td>${formatPercent(r.margin_pct)}</td>
            <td class="${statusClass(r.status)}">${r.status}</td>
          </tr>`).join("")}
      </tbody>
    </table>`;
}

function renderLoansSummary(summary) {
  const box = $("loans-summary");
  const warningBox = $("loans-low-cash-warning");
  if (!box) return;
  if (!summary || !summary.loan_count) {
    box.innerHTML = `<p class="muted">No outstanding loans on record.</p>`;
    warningBox?.classList.add("hidden");
    return;
  }

  const nextLoan = summary.next_loan_to_clear;
  const nextLoanSub = nextLoan
    ? `${nextLoan.years_remaining} yrs remaining, ${formatCurrency(nextLoan.monthly_repayment)}/mo freed up after`
    : "";

  box.innerHTML = [
    overviewMetricCard("Total Debt", formatCurrency(summary.total_outstanding_debt), `${summary.loan_count} loan(s) outstanding`),
    overviewMetricCard("Annual Repayments", formatCurrency(summary.total_annual_repayments), "Across all loans, per year"),
    overviewMetricCard("Next Loan to Clear", nextLoan ? nextLoan.lender : "—", nextLoanSub),
  ].join("");

  if (warningBox) {
    if (summary.low_cash_interaction) {
      warningBox.classList.remove("hidden");
      warningBox.innerHTML = `<ul class="alert-list">${renderAlertListItem(summary.low_cash_interaction)}</ul>`;
    } else {
      warningBox.classList.add("hidden");
      warningBox.innerHTML = "";
    }
  }
}

function renderDebtRegister(loans) {
  const box = $("debt-register-table");
  if (!box) return;
  if (!loans?.length) {
    box.innerHTML = `<p class="muted">No outstanding loans on record.</p>`;
    return;
  }
  box.innerHTML = `
    <table class="sector-table">
      <thead>
        <tr>
          <th>Lender</th>
          <th>Outstanding Balance</th>
          <th>Interest Rate</th>
          <th>Years Remaining</th>
          <th>Repayment</th>
          <th>Maturity</th>
        </tr>
      </thead>
      <tbody>
        ${loans.map((l) => `
          <tr>
            <td><strong>${l.lender}</strong></td>
            <td>${formatCurrency(l.outstanding_balance)}</td>
            <td>${formatPercent(l.rate, { decimals: 2 })}</td>
            <td>${l.years_remaining} yrs</td>
            <td>${formatCurrency(l.monthly_repayment)}/mo</td>
            <td>${l.maturity || "—"}</td>
          </tr>`).join("")}
      </tbody>
    </table>`;
}

/**
 * Small reusable "period badge" (Phase 10 / UX item 3) — shown on every KPI
 * card and table so a figure's time window (Trailing 12 Months, Forecast,
 * Historical Actual, Scenario Result, Point in Time…) is never ambiguous.
 * `period` is the {period_type, start_date, end_date, label} object the
 * backend attaches to the relevant figure.
 */
function periodBadgeHtml(period) {
  if (!period?.period_type) return "";
  const title = period.start_date && period.end_date && period.start_date !== period.end_date
    ? `${period.start_date} to ${period.end_date}`
    : (period.start_date || period.period_type);
  return `<span class="period-badge" title="${title}">${period.label || period.period_type}</span>`;
}

const MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function formatChartEuro(value) {
  return formatCurrency(value);
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

function renderCashPositionChart(cashPosition) {
  const el = $("cash-position-chart");
  if (!el) return;
  const history = cashPosition?.history || [];
  const forecast = cashPosition?.forecast || [];
  const points = [...history, ...forecast];

  if (!points.length) {
    el.innerHTML = `<p class="muted">Not enough data yet — run an analysis to see your cash position.</p>`;
    return;
  }

  el._lastCashPositionData = cashPosition;
  if (!el._resizeObs) {
    el._resizeObs = new ResizeObserver(() => {
      if (el._lastCashPositionData) renderCashPositionChart(el._lastCashPositionData);
    });
    el._resizeObs.observe(el);
  }

  const width = Math.max(el.clientWidth || 0, 640);
  const height = 300;
  const padL = 76;
  const padR = 24;
  const padT = 34;
  const padB = 40;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;

  const values = points.map((p) => Number(p.closing_balance) || 0);
  let minVal = Math.min(0, ...values);
  let maxVal = Math.max(0, ...values);
  if (minVal === maxVal) { minVal -= 1; maxVal += 1; }
  const pad = (maxVal - minVal) * 0.12 || 1;
  minVal -= pad;
  maxVal += pad;

  const n = points.length;
  const xScale = (i) => padL + (n === 1 ? plotW / 2 : (plotW * i) / (n - 1));
  const yScale = (v) => padT + plotH - ((v - minVal) / (maxVal - minVal)) * plotH;

  const tickCount = 5;
  const gridLines = [];
  const yLabels = [];
  for (let t = 0; t <= tickCount; t++) {
    const val = minVal + ((maxVal - minVal) * t) / tickCount;
    const y = yScale(val);
    gridLines.push(`<line class="overview-grid-line" x1="${padL}" y1="${y}" x2="${width - padR}" y2="${y}" />`);
    yLabels.push(`<text class="overview-axis-y" x="${padL - 8}" y="${y + 4}" text-anchor="end">${formatChartEuro(val)}</text>`);
  }

  const zeroLine = (minVal < 0 && maxVal > 0)
    ? `<line class="cash-position-zero-line" x1="${padL}" y1="${yScale(0)}" x2="${width - padR}" y2="${yScale(0)}" />`
    : "";

  const historyCount = history.length;
  const boundaryIdx = historyCount > 0 && forecast.length ? historyCount - 1 : -1;
  const todayMarker = boundaryIdx >= 0 ? `
    <line class="cash-position-today-line" x1="${xScale(boundaryIdx)}" y1="${padT}" x2="${xScale(boundaryIdx)}" y2="${padT + plotH}" />
    <text class="cash-position-today-label" x="${xScale(boundaryIdx)}" y="${padT - 12}" text-anchor="middle">Today</text>` : "";

  const pathFrom = (start, end) => {
    let d = "";
    for (let i = start; i < end; i++) {
      const x = xScale(i);
      const y = yScale(Number(points[i].closing_balance) || 0);
      d += `${i === start ? "M" : "L"}${x},${y} `;
    }
    return d.trim();
  };

  const actualPath = historyCount > 0 ? pathFrom(0, historyCount) : "";
  // Forecast path starts at the last actual point so the two lines connect visually.
  const forecastStart = Math.max(historyCount - 1, 0);
  const forecastPath = forecast.length > 0 ? pathFrom(forecastStart, n) : "";

  const dots = points.map((p, i) => {
    const x = xScale(i);
    const y = yScale(Number(p.closing_balance) || 0);
    const cls = p.series === "forecast" ? "cash-position-dot cash-position-dot-forecast" : "cash-position-dot cash-position-dot-actual";
    return `<circle class="${cls}" data-idx="${i}" tabindex="0" cx="${x}" cy="${y}" r="4" />`;
  }).join("");

  const xLabels = points.map((p, i) => {
    if (n > 12 && i % 2 !== 0 && i !== n - 1) return "";
    return `<text class="overview-axis-x" x="${xScale(i)}" y="${height - 12}" text-anchor="middle">${p.label || ""}</text>`;
  }).join("");

  el.innerHTML = `
    <div class="overview-chart-wrap cash-position-wrap">
      <div class="overview-chart-legend" aria-hidden="true">
        <span class="overview-legend-item"><i class="overview-legend-swatch cash-position-legend-actual"></i>Actual</span>
        <span class="overview-legend-item"><i class="overview-legend-swatch cash-position-legend-forecast"></i>Forecast</span>
      </div>
      <svg class="overview-chart-svg" width="100%" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Monthly cash position, actual and forecast">
        ${gridLines.join("")}
        ${yLabels.join("")}
        <line class="overview-axis-line" x1="${padL}" y1="${padT + plotH}" x2="${width - padR}" y2="${padT + plotH}" />
        ${zeroLine}
        ${todayMarker}
        <path class="cash-position-path cash-position-path-actual" d="${actualPath}" fill="none" />
        <path class="cash-position-path cash-position-path-forecast" d="${forecastPath}" fill="none" />
        ${dots}
        ${xLabels}
      </svg>
      <div class="overview-chart-tooltip hidden" id="cash-position-tooltip"></div>
    </div>`;

  const tooltip = el.querySelector("#cash-position-tooltip");
  const showTooltip = (idx, clientX, clientY) => {
    const p = points[idx];
    if (!p || !tooltip) return;
    const rows = [
      `<div class="overview-tooltip-row"><span>Cash position</span><strong>${formatChartEuro(p.closing_balance)}</strong></div>`,
      `<div class="overview-tooltip-row"><span>${p.series === "forecast" ? "Expected change" : "Actual change"}</span><strong>${p.net_cashflow != null ? formatChartEuro(p.net_cashflow) : "—"}</strong></div>`,
    ];
    if (p.budget_net != null) {
      rows.push(`<div class="overview-tooltip-row"><span>Budgeted change</span><strong>${formatChartEuro(p.budget_net)}</strong></div>`);
    }
    tooltip.innerHTML = `<div class="overview-tooltip-month">${p.label || ""}${p.series === "forecast" ? " (forecast)" : ""}</div>${rows.join("")}`;
    tooltip.classList.remove("hidden");
    const wrap = el.querySelector(".overview-chart-wrap");
    const rect = wrap.getBoundingClientRect();
    const left = Math.min(Math.max(clientX - rect.left + 12, 8), rect.width - 190);
    const top = Math.max(clientY - rect.top - 90, 8);
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  };
  const hideTooltip = () => tooltip?.classList.add("hidden");

  el.querySelectorAll(".cash-position-dot").forEach((dot) => {
    dot.addEventListener("mouseenter", (e) => showTooltip(+dot.dataset.idx, e.clientX, e.clientY));
    dot.addEventListener("mousemove", (e) => showTooltip(+dot.dataset.idx, e.clientX, e.clientY));
    dot.addEventListener("mouseleave", hideTooltip);
    dot.addEventListener("focus", () => {
      const r = dot.getBoundingClientRect();
      showTooltip(+dot.dataset.idx, r.left + r.width / 2, r.top);
    });
    dot.addEventListener("blur", hideTooltip);
  });
}

function renderAlertListItem(a) {
  if (typeof a === "string") return `<li class="alert-medium">${a}</li>`;
  const sev = a.severity || "medium";
  const rows = [];
  if (a.cause || a.why) rows.push(`<div class="alert-detail"><strong>Why:</strong> ${a.cause || a.why}</div>`);
  if (a.review) rows.push(`<div class="alert-detail"><strong>Review:</strong> ${a.review}</div>`);
  return `
    <li class="alert-${sev}">
      <div class="alert-headline-row">
        <span class="alert-headline">${a.what || a.message}</span>
        ${a.when ? `<span class="alert-badge">${a.when}</span>` : ""}
      </div>
      ${a.message ? `<div class="alert-message muted">${a.message}</div>` : ""}
      ${rows.join("")}
    </li>`;
}

function renderExecutiveAlerts(alerts, listId = "alerts-list") {
  const list = $(listId);
  if (!list) return;
  const items = alerts?.length ? alerts : [{ message: "Nothing needs your attention right now.", severity: "info" }];
  list.innerHTML = items.map(renderAlertListItem).join("");
}

function overviewMetricCard(label, valueHtml, subHtml, extraClass = "") {
  return `
    <div class="overview-metric-card ${extraClass}">
      <div class="overview-metric-label">${label}</div>
      <div class="overview-metric-value">${valueHtml}</div>
      ${subHtml ? `<div class="overview-metric-sub">${subHtml}</div>` : ""}
    </div>`;
}

function renderOverviewSummary(summary, needsAttention) {
  const box = $("overview-summary");
  if (!box || !summary) return;
  const cash = summary.current_cash_position || {};
  const lowest = summary.lowest_projected_cash_balance || {};
  const annual = summary.projected_annual_cashflow || {};
  const profit = summary.expected_annual_farm_profit || {};
  const attentionCount = needsAttention?.length || 0;
  const attentionSub = attentionCount > 1
    ? `+ ${attentionCount - 1} more in Action Plan &rarr; Needs Your Attention`
    : "";

  box.innerHTML = [
    overviewMetricCard(
      "Cash Available",
      cash.value ?? "—",
      cash.period?.label || "",
    ),
    overviewMetricCard(
      "Expected Future Cash (lowest point)",
      `<span class="${lowest.is_deficit ? "negative" : ""}">${lowest.value ?? "—"}</span>`,
      lowest.month_label ? `${lowest.month_label} of the forecast` : "Next 12 months",
    ),
    overviewMetricCard(
      "Expected Cash Over the Year",
      `<span class="${annual.is_deficit ? "negative" : "positive"}">${annual.value ?? "—"}</span>`,
      annual.is_deficit ? "Projected deficit" : "Projected surplus",
    ),
    overviewMetricCard(
      "Expected Annual Farm Profit",
      `<span class="${profit.is_deficit ? "negative" : "positive"}">${profit.value ?? "—"}</span>`,
      "Trailing 12 months, annualised",
    ),
    overviewMetricCard(
      "Needs Your Attention",
      summary.main_financial_concern || "—",
      attentionSub,
      "overview-metric-wide",
    ),
    overviewMetricCard(
      "What To Do Next",
      summary.recommended_next_action || "—",
      "",
      "overview-metric-wide",
    ),
  ].join("");
}

function renderCurrentPeriod(currentPeriod) {
  const badge = $("current-period-badge");
  const grid = $("current-period-grid");
  if (!grid) return;
  if (!currentPeriod) {
    if (badge) badge.innerHTML = "";
    grid.innerHTML = `<p class="muted">Not enough data yet — run an analysis to see this month's figures.</p>`;
    return;
  }
  if (badge) badge.innerHTML = periodBadgeHtml(currentPeriod.period);
  grid.innerHTML = [
    overviewMetricCard("Income", currentPeriod.income ?? "—", "Money that came in"),
    overviewMetricCard("Costs", currentPeriod.costs ?? "—", "Money that went out"),
    overviewMetricCard(
      "Difference",
      `<span class="${currentPeriod.is_deficit ? "negative" : "positive"}">${currentPeriod.difference ?? "—"}</span>`,
      currentPeriod.is_deficit ? "Spent more than came in" : "Money left over this month",
    ),
  ].join("");
}

function renderExecutiveDashboard(data) {
  $("dashboard-empty")?.classList.add("hidden");
  $("dashboard-results")?.classList.remove("hidden");
  renderOverviewHeader(data.overview_header);
  renderCurrentPeriod(data.overview_summary?.current_period);
  renderOverviewSummary(data.overview_summary, data.needs_attention);
  renderCashPositionChart(data.overview_summary?.cash_position);
  renderKpis(data.executive_kpis || data.kpis);
  renderHealthSnapshot(data.health_snapshot);
  renderHealthScoreDetail(data.health_score);
  renderSectorTable(data.sector_performance);
  renderExecutiveAlerts(data.needs_attention, "alerts-full");
  updateAlertsNavHighlight(data.needs_attention);
  renderOverviewChart(data.overview_chart);
  renderLoansSummary(data.loans_summary);
  renderDebtRegister(data.debt_register);
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
      Annual Profit: <span class="${signClass(s.annual_profit)}">${formatCurrency(s.annual_profit)}</span> (${s.profit_impact || ""})
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
    { label: "Annual Revenue", value: formatCurrency(s.annual_revenue) },
    { label: "Annual Profit", value: formatCurrency(s.annual_profit) },
    { label: "Profit Margin", value: formatPercent(s.profit_margin) },
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
  const expected = monte.expected_profit || 0;
  const low = monte.worst_case ?? monte.confidence_range?.[0] ?? 0;
  const high = monte.best_case ?? monte.confidence_range?.[1] ?? 0;
  const lossPct = (monte.probability_of_loss || 0) * 100;
  box.innerHTML = `
    <ul class="profit-outlook-list">
      <li>Expected profit is ${formatCurrency(expected)}</li>
      <li>It can range between ${formatCurrency(low)} and ${formatCurrency(high)}</li>
      <li>Probability of making a loss is ${formatPercent(lossPct)}.</li>
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
  btn.textContent = "Action Plan";
  if (count >= 5) {
    btn.classList.add("nav-alerts--warn-high");
    btn.textContent = "⚠ Action Plan";
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
  const sandboxPeriodSlot = $("sandbox-period");
  if (sandboxPeriodSlot) sandboxPeriodSlot.innerHTML = periodBadgeHtml(c.period);
  renderMetricCards([
    { label: "Profit (base)", value: formatCurrency(c.profit_base) },
    { label: "Profit (scenario)", value: formatCurrency(c.profit_scenario) },
    { label: "Difference", value: formatCurrency(c.profit_difference), sub: c.profit_difference >= 0 ? "Better" : "Worse" },
    { label: "Risk change", value: `${c.risk_base} → ${c.risk_scenario}` },
  ], "sandbox-comparison");
  const table = $("sandbox-table");
  if (table) {
    table.innerHTML = `<table class="data-table"><tbody>
      <tr><td>Revenue</td><td>${formatCurrency(c.revenue_base)}</td><td>${formatCurrency(c.revenue_scenario)}</td><td class="${signClass(c.revenue_difference)}">${formatCurrency(c.revenue_difference)}</td></tr>
      <tr><td>Monthly profit</td><td>${formatCurrency(c.monthly_profit_base)}</td><td>${formatCurrency(c.monthly_profit_scenario)}</td><td>—</td></tr>
      <tr><td>Monthly cashflow</td><td>${formatCurrency(c.monthly_cashflow_base)}</td><td>${formatCurrency(c.monthly_cashflow_scenario)}</td><td>—</td></tr>
      <tr><td>Lowest cash</td><td>${formatCurrency(c.min_cash_base)}</td><td>${formatCurrency(c.min_cash_scenario)}</td><td>—</td></tr>
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
    "Cover page and summary",
    "Farm profile and financial snapshot",
    "Profitability and cash-flow charts",
    "12-month forecast and profit outlook (best, likely & worst case)",
    "What If? comparison table",
    "Financial intelligence and recommendations",
    "Risk dashboard and 90-day action plan",
    "Investment readiness score",
  ],
  executive: [
    "Cover page and summary",
    "Financial intelligence highlights",
    "Top 5 recommended actions",
    "AI farm advisor summary",
  ],
  scenario: [
    "Summary",
    "What If? comparison table and charts",
    "Risk dashboard",
    "Recommended actions",
  ],
  investment: [
    "Summary and financial snapshot",
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
      <div class="kpi-card"><span class="kpi-label">Cash Available</span><span class="kpi-value">${formatCurrency(k.cash_available)}</span></div>
      <div class="kpi-card"><span class="kpi-label">Annual Profit</span><span class="kpi-value">${formatCurrency(k.annual_profit)}</span></div>
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
    items.push({ label: "Profit change", value: formatCurrency(metrics.profit_change) });
  }
  if (metrics.cashflow_change != null) {
    items.push({
      label: "Cashflow",
      value: `${formatCurrency(metrics.cashflow_change)}/mo`,
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

// Five main sections (Overview, Cash Flow, Farm Performance, Action Plan,
// Farm Data) plus Advanced Analysis / Settings replaced the old flat list of
// 8 nav items (UX items 1/7/9/13). Several of those sections now hold more
// than one page's worth of content behind in-page sub-tabs, so navigation
// and lazy-loading are keyed on (view, sub-tab) rather than view alone.
const DEFAULT_SUBTAB = {
  cashflow: "cashflow-forecast",
  "farm-performance": "fp-sectors",
  "action-plan": "ap-alerts",
};

const SUBTAB_LOADERS = {
  "cashflow-forecast": () => ensureAdvancedForecast(),
  "cashflow-budget": () => { loadCashflowBudget(); loadCategoryBudgets(); },
  "cashflow-income-expenses": () => loadIncomeExpenses(),
  "cashflow-documents": () => loadDocuments(),
  "fp-historical": () => { loadHistoricalData(); loadYearOverYear(); },
  "ap-recommendations": () => loadFinancialIntelligence(),
  "ap-ask": () => initFarmIntelligencePage(),
  "ap-reports": () => {
    initReportDate();
    updateReportSections();
  },
};

async function runSubtabLoader(tab) {
  const loader = SUBTAB_LOADERS[tab];
  if (!loader) return;
  try {
    await loader();
  } catch (err) {
    showStatus(err.message, "error");
  }
}

function switchSubtab(group, tab) {
  const groupEl = document.querySelector(`[data-subtab-group="${group}"]`);
  const section = groupEl?.closest(".view");
  if (!section) return;
  section.querySelectorAll(`[data-subtab-group="${group}"] .subtab-btn`).forEach((b) => {
    b.classList.toggle("active", b.dataset.subtab === tab);
  });
  section.querySelectorAll("[data-subtab-panel]").forEach((panel) => {
    panel.classList.toggle("hidden", panel.dataset.subtabPanel !== tab);
  });
  state.activeSubtab = tab;
  runSubtabLoader(tab);
}

function setupSubtabs() {
  document.querySelectorAll(".subtab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const group = btn.closest("[data-subtab-group]")?.dataset.subtabGroup;
      const tab = btn.dataset.subtab;
      if (group && tab) switchSubtab(group, tab);
    });
  });
}

async function navigate(view) {
  state.view = view;
  document.querySelectorAll(".nav-link").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => { v.classList.remove("active"); v.classList.add("hidden"); });
  const section = $(`view-${view}`);
  if (section) { section.classList.add("active"); section.classList.remove("hidden"); }

  const defaultSubtab = DEFAULT_SUBTAB[view] || null;
  state.activeSubtab = defaultSubtab;
  if (defaultSubtab) await runSubtabLoader(defaultSubtab);
  if (view === "advanced-analysis") await ensureAdvancedForecast();
  if (view === "settings") await loadOnboarding();
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
                  <td>${formatCurrency(r.revenue)}</td>
                  <td>${formatCurrency(r.costs)}</td>
                  <td class="${signClass((r.revenue || 0) - (r.costs || 0))}">${formatCurrency((r.revenue || 0) - (r.costs || 0))}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>
      </div>`;
  };

  let html = renderTable(data.combined_monthly, "Combined (selected sectors)");
  (data.sectors || []).forEach((s) => {
    html += renderTable(s.monthly, `${s.label} — totals: ${formatCurrency(s.totals?.revenue)} revenue`);
  });
  box.innerHTML = html || `<p class="muted">No historical data available.</p>`;
}

function yoyMetricCard(label, metric) {
  if (!metric) return "";
  const sign = metric.change > 0 ? "positive" : (metric.change < 0 ? "negative" : "");
  const changeSign = metric.change > 0 ? "+" : "";
  const pctText = metric.change_pct != null ? ` (${metric.change_pct > 0 ? "+" : ""}${formatPercent(metric.change_pct)})` : "";
  return overviewMetricCard(
    label,
    formatCurrency(metric.current),
    `<span class="${sign}">${changeSign}${formatCurrency(metric.change)}${pctText}</span> vs ${formatCurrency(metric.previous)} the year before`,
  );
}

function renderYearOverYear(data) {
  const box = $("yoy-summary");
  if (!box) return;
  if (!data?.comparisons?.length) {
    box.innerHTML = `<p class="muted">Not enough years of recorded data yet for a year-over-year comparison — check back once a second year of actuals is available.</p>`;
    return;
  }

  const comparisons = data.comparisons;
  const latest = comparisons[comparisons.length - 1];
  const noteHtml = latest.basis === "same_months_partial"
    ? `<p class="muted">${latest.note}</p>`
    : (latest.basis === "no_overlap" ? `<p class="muted">${latest.note}</p>` : "");

  const olderRows = comparisons.slice(0, -1).reverse().map((c) => `
    <li>
      <strong>${c.year} vs ${c.previous_year}</strong> —
      Farm Profit ${formatCurrency(c.farm_profit?.current)}
      (<span class="${c.farm_profit?.change > 0 ? "positive" : (c.farm_profit?.change < 0 ? "negative" : "")}">${c.farm_profit?.change > 0 ? "+" : ""}${formatCurrency(c.farm_profit?.change)}</span> vs ${c.previous_year})
      ${c.basis === "same_months_partial" ? `<span class="muted"> — ${c.note}</span>` : ""}
    </li>`).join("");

  box.innerHTML = `
    <h4>${latest.year} vs ${latest.previous_year}</h4>
    ${noteHtml}
    <div class="overview-summary-grid">
      ${yoyMetricCard("Income", latest.income)}
      ${yoyMetricCard("Costs", latest.costs)}
      ${yoyMetricCard("Farm Profit", latest.farm_profit)}
      ${yoyMetricCard("Cash Generated", latest.cash_generated)}
    </div>
    ${olderRows ? `<h4>Earlier comparisons</h4><ul class="profit-outlook-list">${olderRows}</ul>` : ""}`;
}

async function loadYearOverYear() {
  const box = $("yoy-summary");
  if (box) box.innerHTML = `<p class="muted">Loading year-over-year comparison…</p>`;
  try {
    const data = await api(`/farmer/year-over-year${sectorsQuery()}`);
    renderYearOverYear(data);
  } catch (err) {
    if (box) box.innerHTML = `<p class="muted">Could not load: ${err.message}</p>`;
  }
}

function budgetStatusLabel(status) {
  if (status === "ahead") return "Ahead";
  if (status === "behind") return "Behind";
  return "On budget";
}

function classificationLabel(classification) {
  if (classification === "long_term") return "Ongoing issue";
  if (classification === "short_term") return "One-off / short-term";
  return "—";
}

function renderCashflowBudgetTable(data) {
  $("cashflow-budget-loading")?.classList.add("hidden");
  const entries = data.entries || [];

  const summary = $("cashflow-budget-summary");
  if (summary) {
    summary.classList.remove("hidden");
    summary.innerHTML = `${entries.length} month(s) compared. `
      + `${data.deficit_months || 0} month(s) in deficit `
      + `(${data.short_term_deficit_months || 0} short-term, ${data.long_term_deficit_months || 0} long-term/structural). `
      + `${data.behind_budget_months || 0} month(s) behind budget.`;
  }

  const table = $("cashflow-budget-table");
  if (!table) return;
  if (!entries.length) {
    table.innerHTML = `<p class="muted">No overlapping budget and actual months found.</p>`;
    return;
  }
  table.innerHTML = `
    <table class="sector-table data-table">
      <thead>
        <tr>
          <th>Month</th>
          <th>Actual Net</th>
          <th>Budgeted Net</th>
          <th>Difference</th>
          <th>vs Budget</th>
          <th>Shortfall Type</th>
          <th>Why</th>
        </tr>
      </thead>
      <tbody>
        ${entries.map((e) => `
          <tr>
            <td>${e.period_info?.label || e.period}</td>
            <td class="${signClass(e.actual_net)}">${formatCurrency(e.actual_net)}</td>
            <td>${formatCurrency(e.budgeted_net)}</td>
            <td class="${signClass(e.variance)}">${formatCurrency(e.variance)}</td>
            <td>${budgetStatusLabel(e.budget_status)}</td>
            <td>${classificationLabel(e.classification)}</td>
            <td class="muted">${e.classification_reason || e.cause_summary || ""}</td>
          </tr>`).join("")}
      </tbody>
    </table>`;
}

async function loadCashflowBudget() {
  $("cashflow-budget-loading")?.classList.remove("hidden");
  $("cashflow-budget-summary")?.classList.add("hidden");
  try {
    const data = await api(`/farmer/cashflow-budget${sectorsQuery()}`);
    renderCashflowBudgetTable(data);
  } catch (err) {
    if ($("cashflow-budget-loading")) {
      $("cashflow-budget-loading").classList.remove("hidden");
      $("cashflow-budget-loading").textContent = `Could not load: ${err.message}`;
    }
    showStatus(err.message, "error");
  }
}

async function ensureCategoryChoicesLoaded() {
  if (state.incomeExpenses) return;
  try {
    state.incomeExpenses = await api(`/farmer/income-expenses${sectorsQuery()}`);
  } catch (err) {
    // Non-fatal: the category dropdown just stays empty until this loads.
  }
}

function cbStatusClass(status) {
  if (status === "above_budget" || status === "behind") return "negative";
  if (status === "below_budget" || status === "ahead") return "positive";
  return "muted";
}

function renderCbCategoryRow(row) {
  if (row.status === "no_budget_set") {
    return `
      <div class="ie-category-row">
        <div class="ie-category-row-label">
          <span>${row.label}</span>
          <button type="button" class="btn-link cb-set-budget-btn" data-record-type="${row.record_type}" data-category="${row.category_id}">Set a budget</button>
        </div>
        <p class="muted small">No budget set yet.</p>
      </div>`;
  }
  return `
    <div class="ie-category-row">
      <div class="ie-category-row-label">
        <span>${row.label}</span>
        <strong class="${cbStatusClass(row.status)}">${row.summary}</strong>
      </div>
      <p class="muted small">
        Budget ${formatCurrency(row.budget_total)} · Actual ${formatCurrency(row.actual_total)}
        (${row.months_with_budget}/${row.months_in_window} months budgeted)
      </p>
    </div>`;
}

function renderCbCategoryList(containerId, rows, emptyMessage) {
  const box = $(containerId);
  if (!box) return;
  if (!rows?.length) {
    box.innerHTML = `<p class="muted">${emptyMessage}</p>`;
    return;
  }
  box.innerHTML = rows.map(renderCbCategoryRow).join("");
  box.querySelectorAll(".cb-set-budget-btn").forEach((btn) => {
    btn.addEventListener("click", () => openCbBudgetForm({ record_type: btn.dataset.recordType, category: btn.dataset.category }));
  });
}

function renderCategoryBudgets(data) {
  $("cb-loading")?.classList.add("hidden");
  $("cb-content")?.classList.remove("hidden");

  const summaryBox = $("cb-overall-summary");
  if (summaryBox) {
    summaryBox.innerHTML = `<strong class="${cbStatusClass(data.overall_status)}">${data.overall_summary}</strong>`;
  }

  renderCbCategoryList("cb-top-contributors", data.top_contributors, "No categories are meaningfully over or under budget right now.");
  renderCbCategoryList("cb-all-categories", data.categories, "No category budgets have been set yet.");
  renderCbCategoryList("cb-unbudgeted-categories", data.unbudgeted_categories, "Every category with activity already has a budget.");
}

async function loadCategoryBudgets() {
  $("cb-loading")?.classList.remove("hidden");
  $("cb-content")?.classList.add("hidden");
  try {
    await ensureCategoryChoicesLoaded();
    const data = await api(`/farmer/category-budget-vs-actual${sectorsQuery()}`);
    state.categoryBudgets = data;
    renderCategoryBudgets(data);
  } catch (err) {
    if ($("cb-loading")) $("cb-loading").textContent = `Could not load: ${err.message}`;
    showStatus(err.message, "error");
  }
}

function cbUpdatePeriodFields() {
  const mode = $("cb-period-mode")?.value;
  $("cb-month-field")?.classList.toggle("hidden", mode !== "monthly");
  $("cb-year-field")?.classList.toggle("hidden", mode !== "annual");
}

function openCbBudgetForm(prefill = {}) {
  const form = $("cb-budget-form");
  if (!form) return;
  form.classList.remove("hidden");
  $("cb-add-budget-btn")?.classList.add("hidden");

  $("cb-budget-id").value = "";
  $("cb-record-type").value = prefill.record_type || "expense";
  $("cb-category").innerHTML = ieCategoryOptions($("cb-record-type").value);
  if (prefill.category) $("cb-category").value = prefill.category;
  $("cb-period-mode").value = "monthly";
  const today = new Date();
  $("cb-month").value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
  $("cb-year").value = today.getFullYear();
  $("cb-amount").value = "";
  cbUpdatePeriodFields();
  form.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function closeCbBudgetForm() {
  $("cb-budget-form")?.classList.add("hidden");
  $("cb-add-budget-btn")?.classList.remove("hidden");
  $("cb-budget-form")?.reset();
}

async function submitCbBudgetForm(e) {
  e.preventDefault();
  const recordType = $("cb-record-type").value;
  const category = $("cb-category").value;
  const amount = parseFloat($("cb-amount").value);
  const mode = $("cb-period-mode").value;

  if (!category || !(amount >= 0)) {
    showStatus("Please choose a category and enter an amount of 0 or more.", "error");
    return;
  }

  try {
    if (mode === "annual") {
      const year = parseInt($("cb-year").value, 10);
      if (!year) {
        showStatus("Please enter a year.", "error");
        return;
      }
      await api(`/farmer/category-budgets/annual${sectorsQuery()}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ record_type: recordType, category, year, annual_amount: amount, sector: null, notes: null }),
      });
      showStatus("Annual budget saved and split evenly across the 12 months.", "success");
    } else {
      const monthValue = $("cb-month").value;
      if (!monthValue) {
        showStatus("Please choose a month.", "error");
        return;
      }
      const [year, month] = monthValue.split("-").map(Number);
      await api(`/farmer/category-budgets/monthly${sectorsQuery()}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ record_type: recordType, category, year, month, amount, sector: null, notes: null }),
      });
      showStatus("Budget saved.", "success");
    }
    closeCbBudgetForm();
    await loadCategoryBudgets();
  } catch (err) {
    showStatus(err.message, "error");
  }
}

function ieCategoryOptions(recordType) {
  const choices = recordType === "income"
    ? (state.incomeExpenses?.income_category_choices || [])
    : (state.incomeExpenses?.expense_category_choices || []);
  return choices.map((c) => `<option value="${c.id}">${c.label}</option>`).join("");
}

function ieCategoryLabel(recordType, categoryId) {
  const choices = recordType === "income"
    ? state.incomeExpenses?.income_category_choices
    : state.incomeExpenses?.expense_category_choices;
  return choices?.find((c) => c.id === categoryId)?.label || categoryId;
}

function renderIeCategoryList(containerId, rows) {
  const box = $(containerId);
  if (!box) return;
  if (!rows?.length) {
    box.innerHTML = `<p class="muted">No recorded amounts for this period yet.</p>`;
    return;
  }
  const maxTotal = Math.max(...rows.map((r) => Math.abs(r.total || 0)), 1);
  box.innerHTML = rows.map((r) => `
    <div class="ie-category-row">
      <div class="ie-category-row-label">
        <span>${r.label}</span>
        <strong>${formatCurrency(r.total)}</strong>
      </div>
      <div class="ie-category-bar-track">
        <div class="ie-category-bar-fill" style="width:${Math.max(4, (Math.abs(r.total || 0) / maxTotal) * 100)}%"></div>
      </div>
    </div>`).join("");
}

function renderIncomeExpensesSummary(data) {
  $("income-expenses-loading")?.classList.add("hidden");
  $("income-expenses-content")?.classList.remove("hidden");

  const row = $("ie-summary-row");
  if (row) {
    const isDeficit = (data.difference || 0) < 0;
    row.innerHTML = [
      overviewMetricCard("Income", formatCurrency(data.income_total), data.period?.label || ""),
      overviewMetricCard("Costs", formatCurrency(data.expense_total), data.period?.label || ""),
      overviewMetricCard(
        "Difference",
        `<span class="${isDeficit ? "negative" : "positive"}">${formatCurrency(data.difference)}</span>`,
        isDeficit ? "Costs ahead of income" : "Income ahead of costs",
      ),
    ].join("");
  }

  renderIeCategoryList("ie-income-categories", data.income_categories);
  renderIeCategoryList("ie-expense-categories", data.expense_categories);
}

function renderFinancialRecordsList(records) {
  const box = $("ie-records-list");
  if (!box) return;
  if (!records?.length) {
    box.innerHTML = `<p class="muted">No manual entries yet — add your first one above.</p>`;
    return;
  }
  box.innerHTML = records.map((r) => `
    <div class="ie-record-row" data-id="${r.id}">
      <div class="ie-record-main">
        <span class="ie-record-type ${r.record_type}">${r.record_type === "income" ? "Income" : "Expense"}</span>
        <span class="ie-record-date">${r.date}</span>
        <span class="ie-record-category">${ieCategoryLabel(r.record_type, r.category)}</span>
        <span class="ie-record-desc">${r.description}${r.counterparty ? ` · ${r.counterparty}` : ""}</span>
      </div>
      <div class="ie-record-amount ${r.record_type === "income" ? "positive" : "negative"}">${r.record_type === "income" ? "+" : "-"}${formatCurrency(r.amount)}</div>
      <div class="ie-record-actions">
        <button type="button" class="btn-link ie-edit-btn" data-id="${r.id}">Edit</button>
        <button type="button" class="btn-link ie-delete-btn" data-id="${r.id}">Delete</button>
      </div>
    </div>`).join("");

  box.querySelectorAll(".ie-edit-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const record = records.find((r) => r.id === btn.dataset.id);
      if (record) openIeEntryForm(record);
    });
  });
  box.querySelectorAll(".ie-delete-btn").forEach((btn) => {
    btn.addEventListener("click", () => deleteIeRecord(btn.dataset.id));
  });
}

async function loadFinancialRecordsList() {
  try {
    const data = await api(`/farmer/financial-records${sectorsQuery()}`);
    state.financialRecords = data.records || [];
    renderFinancialRecordsList(state.financialRecords);
  } catch (err) {
    showStatus(err.message, "error");
  }
}

async function loadIncomeExpenses() {
  $("income-expenses-loading")?.classList.remove("hidden");
  $("income-expenses-content")?.classList.add("hidden");
  try {
    const data = await api(`/farmer/income-expenses${sectorsQuery()}`);
    state.incomeExpenses = data;
    renderIncomeExpensesSummary(data);
    await loadFinancialRecordsList();
  } catch (err) {
    if ($("income-expenses-loading")) $("income-expenses-loading").textContent = `Could not load: ${err.message}`;
    showStatus(err.message, "error");
  }
}

function populateIeCategorySelect() {
  const typeSelect = $("ie-entry-type");
  const categorySelect = $("ie-entry-category");
  if (!typeSelect || !categorySelect) return;
  const previous = categorySelect.value;
  categorySelect.innerHTML = ieCategoryOptions(typeSelect.value);
  if ([...categorySelect.options].some((o) => o.value === previous)) categorySelect.value = previous;
}

function openIeEntryForm(record = null) {
  const form = $("ie-entry-form");
  if (!form) return;
  form.classList.remove("hidden");
  $("ie-add-entry-btn")?.classList.add("hidden");

  $("ie-entry-id").value = record?.id || "";
  $("ie-entry-type").value = record?.record_type || "expense";
  $("ie-entry-type").disabled = !!record;
  populateIeCategorySelect();
  if (record?.category) $("ie-entry-category").value = record.category;
  $("ie-entry-date").value = record?.date || new Date().toISOString().slice(0, 10);
  $("ie-entry-amount").value = record?.amount ?? "";
  $("ie-entry-description").value = record?.description || "";
  $("ie-entry-counterparty").value = record?.counterparty || "";
  $("ie-entry-notes").value = record?.notes || "";
  form.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function closeIeEntryForm() {
  $("ie-entry-form")?.classList.add("hidden");
  $("ie-add-entry-btn")?.classList.remove("hidden");
  $("ie-entry-form")?.reset();
  const typeSelect = $("ie-entry-type");
  if (typeSelect) typeSelect.disabled = false;
}

async function submitIeEntryForm(e) {
  e.preventDefault();
  const id = $("ie-entry-id")?.value;
  const recordType = $("ie-entry-type").value;
  const payload = {
    record_type: recordType,
    date: $("ie-entry-date").value,
    category: $("ie-entry-category").value,
    amount: parseFloat($("ie-entry-amount").value),
    description: $("ie-entry-description").value.trim(),
    counterparty: $("ie-entry-counterparty").value.trim() || null,
    notes: $("ie-entry-notes").value.trim() || null,
  };
  if (!payload.category || !payload.description || !payload.date || !(payload.amount > 0)) {
    showStatus("Please fill in date, category, description and a positive amount.", "error");
    return;
  }
  try {
    if (id) {
      const editPayload = { ...payload };
      delete editPayload.record_type;
      await api(`/farmer/financial-records/${id}${sectorsQuery()}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editPayload),
      });
      showStatus("Entry updated.", "success");
    } else {
      const result = await api(`/farmer/financial-records${sectorsQuery()}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      showStatus(
        result.possible_duplicate
          ? "Saved — note: a very similar entry already exists. Check Your Entries if this wasn't intentional."
          : "Entry added.",
        result.possible_duplicate ? "info" : "success",
      );
    }
    closeIeEntryForm();
    await loadIncomeExpenses();
  } catch (err) {
    showStatus(err.message, "error");
  }
}

async function deleteIeRecord(id) {
  if (!confirm("Delete this entry? This cannot be undone.")) return;
  try {
    await api(`/farmer/financial-records/${id}${sectorsQuery()}`, { method: "DELETE" });
    showStatus("Entry deleted.", "success");
    await loadIncomeExpenses();
  } catch (err) {
    showStatus(err.message, "error");
  }
}

function docPaymentBadgeHtml(doc) {
  return doc.payment_status === "paid"
    ? `<span class="doc-badge paid">Paid</span>`
    : `<span class="doc-badge unpaid">Not paid yet</span>`;
}

function docTypeLabel(doc) {
  return doc.document_type === "invoice" ? "Invoice" : "Receipt";
}

function docNoteHtml(doc) {
  if (doc.possible_duplicate_manual_record_id) {
    return `<div class="doc-record-note">Not counted separately in Income &amp; Expenses — it matches an entry you already logged manually.</div>`;
  }
  if (doc.payment_status === "unpaid") {
    return `<div class="doc-record-note">Not yet counted in your cash flow — mark it paid once payment happens.</div>`;
  }
  return "";
}

function renderDocumentsList(documents) {
  const box = $("doc-list");
  if (!box) return;
  if (!documents?.length) {
    box.innerHTML = `<p class="muted">No invoices or receipts logged yet — add your first one above.</p>`;
    return;
  }
  box.innerHTML = documents.map((d) => `
    <div class="ie-record-row" data-id="${d.id}">
      <div class="ie-record-main">
        <span class="ie-record-type ${d.record_type}">${d.record_type === "income" ? "Income" : "Expense"}</span>
        <span class="doc-badge">${docTypeLabel(d)}</span>
        ${docPaymentBadgeHtml(d)}
        <span class="ie-record-date">${d.date}</span>
        <span class="ie-record-category">${ieCategoryLabel(d.record_type, d.category)}</span>
        <span class="ie-record-desc">${d.counterparty}${d.reference ? ` · Ref ${d.reference}` : ""}</span>
        ${docNoteHtml(d)}
      </div>
      <div class="ie-record-amount ${d.record_type === "income" ? "positive" : "negative"}">${d.record_type === "income" ? "+" : "-"}${formatCurrency(d.amount)}</div>
      <div class="ie-record-actions">
        <button type="button" class="btn-link doc-edit-btn" data-id="${d.id}">Edit</button>
        <button type="button" class="btn-link doc-delete-btn" data-id="${d.id}">Delete</button>
      </div>
    </div>`).join("");

  box.querySelectorAll(".doc-edit-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const doc = documents.find((d) => d.id === btn.dataset.id);
      if (doc) openDocForm(doc);
    });
  });
  box.querySelectorAll(".doc-delete-btn").forEach((btn) => {
    btn.addEventListener("click", () => deleteDocRecord(btn.dataset.id));
  });
}

async function loadDocuments() {
  try {
    await ensureCategoryChoicesLoaded();
    const data = await api(`/farmer/documents${sectorsQuery()}`);
    state.documents = data.documents || [];
    renderDocumentsList(state.documents);
  } catch (err) {
    showStatus(err.message, "error");
  }
}

function populateDocCategorySelect() {
  const typeSelect = $("doc-record-type");
  const categorySelect = $("doc-category");
  if (!typeSelect || !categorySelect) return;
  const previous = categorySelect.value;
  categorySelect.innerHTML = ieCategoryOptions(typeSelect.value);
  if ([...categorySelect.options].some((o) => o.value === previous)) categorySelect.value = previous;
}

function docUpdatePaymentDateVisibility() {
  const paid = $("doc-payment-status")?.value === "paid";
  $("doc-payment-date-field")?.classList.toggle("hidden", !paid);
}

function docApplyTypeDefaults() {
  const isReceipt = $("doc-type")?.value === "receipt";
  $("doc-payment-status").value = isReceipt ? "paid" : "unpaid";
  docUpdatePaymentDateVisibility();
}

function openDocForm(doc = null) {
  const form = $("doc-form");
  if (!form) return;
  form.classList.remove("hidden");
  $("doc-add-btn")?.classList.add("hidden");

  $("doc-id").value = doc?.id || "";
  $("doc-type").value = doc?.document_type || "receipt";
  $("doc-type").disabled = !!doc;
  $("doc-record-type").value = doc?.record_type || "expense";
  $("doc-record-type").disabled = !!doc;
  populateDocCategorySelect();
  if (doc?.category) $("doc-category").value = doc.category;
  $("doc-date").value = doc?.date || new Date().toISOString().slice(0, 10);
  $("doc-amount").value = doc?.amount ?? "";
  $("doc-counterparty").value = doc?.counterparty || "";
  $("doc-payment-status").value = doc?.payment_status || (($("doc-type").value === "receipt") ? "paid" : "unpaid");
  $("doc-payment-date").value = doc?.payment_date || "";
  $("doc-reference").value = doc?.reference || "";
  $("doc-notes").value = doc?.notes || "";
  docUpdatePaymentDateVisibility();
  form.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function closeDocForm() {
  $("doc-form")?.classList.add("hidden");
  $("doc-add-btn")?.classList.remove("hidden");
  $("doc-form")?.reset();
  $("doc-type").disabled = false;
  $("doc-record-type").disabled = false;
}

async function submitDocForm(e) {
  e.preventDefault();
  const id = $("doc-id")?.value;
  const paymentStatus = $("doc-payment-status").value;
  const payload = {
    document_type: $("doc-type").value,
    record_type: $("doc-record-type").value,
    date: $("doc-date").value,
    category: $("doc-category").value,
    amount: parseFloat($("doc-amount").value),
    counterparty: $("doc-counterparty").value.trim(),
    payment_status: paymentStatus,
    payment_date: paymentStatus === "paid" ? ($("doc-payment-date").value || null) : null,
    reference: $("doc-reference").value.trim() || null,
    notes: $("doc-notes").value.trim() || null,
  };
  if (!payload.category || !payload.counterparty || !payload.date || !(payload.amount > 0)) {
    showStatus("Please fill in date, category, supplier/customer and a positive amount.", "error");
    return;
  }
  try {
    if (id) {
      const editPayload = { ...payload };
      delete editPayload.document_type;
      delete editPayload.record_type;
      await api(`/farmer/documents/${id}${sectorsQuery()}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editPayload),
      });
      showStatus("Invoice/receipt updated.", "success");
    } else {
      await api(`/farmer/documents${sectorsQuery()}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      showStatus("Invoice/receipt saved.", "success");
    }
    closeDocForm();
    await loadDocuments();
  } catch (err) {
    showStatus(err.message, "error");
  }
}

async function deleteDocRecord(id) {
  if (!confirm("Delete this invoice/receipt? This cannot be undone.")) return;
  try {
    await api(`/farmer/documents/${id}${sectorsQuery()}`, { method: "DELETE" });
    showStatus("Invoice/receipt deleted.", "success");
    await loadDocuments();
  } catch (err) {
    showStatus(err.message, "error");
  }
}

// -----------------------------------------------------------------------
// Simple Farm Setup / Onboarding (P1.3)
// -----------------------------------------------------------------------

let onbLoanRowCount = 0;

async function loadOnboarding() {
  try {
    const data = await api(`/farmer/onboarding${sectorsQuery()}`);
    state.onboarding = data;
    renderOnboardingForm(data);
  } catch (err) {
    showStatus(err.message, "error");
  }
}

function renderOnboardingForm(data) {
  const farmTypeSelect = $("onb-farm-type");
  if (farmTypeSelect) {
    farmTypeSelect.innerHTML = (data.farm_types || [])
      .map((t) => `<option value="${t.id}">${t.label}</option>`)
      .join("");
    if (data.farm_type) farmTypeSelect.value = data.farm_type;
  }

  const incomeBox = $("onb-income-items");
  if (incomeBox) {
    incomeBox.innerHTML = (data.income_category_choices || [])
      .map((c) => `
        <div class="onb-item-row">
          <label for="onb-income-${c.id}">${c.label} (€/year)</label>
          <input type="number" id="onb-income-${c.id}" data-onb-income="${c.id}" min="0" step="0.01" placeholder="0" />
        </div>`)
      .join("");
  }

  const costBox = $("onb-cost-items");
  if (costBox) {
    costBox.innerHTML = (data.expense_category_choices || [])
      .map((c) => `
        <div class="onb-item-row">
          <label for="onb-cost-${c.id}">${c.label} (€/year)</label>
          <input type="number" id="onb-cost-${c.id}" data-onb-cost="${c.id}" min="0" step="0.01" placeholder="0" />
        </div>`)
      .join("");
  }

  if ($("onb-current-cash")) $("onb-current-cash").value = data.current_cash ?? "";

  const loanBox = $("onb-loan-items");
  if (loanBox) {
    loanBox.innerHTML = "";
    onbLoanRowCount = 0;
    addOnboardingLoanRow();
  }

  const statusLine = $("onboarding-status-line");
  if (statusLine) {
    statusLine.textContent = data.completed
      ? `Farm Setup completed${data.farm_type_label ? ` — ${data.farm_type_label}` : ""}${data.loan_repayments_annual ? `, loan repayments ${formatCurrency(data.loan_repayments_annual)}/year` : ""}. You can update it below at any time.`
      : "Not set up yet — fill this in to get your first useful forecast.";
  }

  $("onboarding-result")?.classList.add("hidden");
}

function addOnboardingLoanRow() {
  const loanBox = $("onb-loan-items");
  if (!loanBox) return;
  const idx = onbLoanRowCount++;
  const row = document.createElement("div");
  row.className = "onb-loan-row";
  row.dataset.loanRow = String(idx);
  row.innerHTML = `
    <label>Lender (optional)
      <input type="text" data-loan-lender maxlength="120" placeholder="e.g. AIB" />
    </label>
    <label>Monthly repayment (€)
      <input type="number" data-loan-monthly min="0" step="0.01" placeholder="0" />
    </label>
    <label>Outstanding balance (optional, €)
      <input type="number" data-loan-balance min="0" step="0.01" placeholder="0" />
    </label>
    <button type="button" class="btn-link onb-remove-loan-btn">Remove</button>`;
  row.querySelector(".onb-remove-loan-btn").addEventListener("click", () => row.remove());
  loanBox.appendChild(row);
}

function collectOnboardingPayload() {
  const incomeItems = [...document.querySelectorAll("[data-onb-income]")]
    .map((input) => ({ category: input.dataset.onbIncome, annual_amount: parseFloat(input.value) || 0 }))
    .filter((item) => item.annual_amount > 0);

  const costItems = [...document.querySelectorAll("[data-onb-cost]")]
    .map((input) => ({ category: input.dataset.onbCost, annual_amount: parseFloat(input.value) || 0 }))
    .filter((item) => item.annual_amount > 0);

  const loanItems = [...document.querySelectorAll("[data-loan-row]")]
    .map((row) => ({
      lender: row.querySelector("[data-loan-lender]")?.value.trim() || null,
      monthly_repayment: parseFloat(row.querySelector("[data-loan-monthly]")?.value) || 0,
      outstanding_balance: row.querySelector("[data-loan-balance]")?.value
        ? parseFloat(row.querySelector("[data-loan-balance]").value)
        : null,
    }))
    .filter((item) => item.monthly_repayment > 0);

  const currentCashRaw = $("onb-current-cash")?.value;
  const currentCash = currentCashRaw !== "" && currentCashRaw != null ? parseFloat(currentCashRaw) : null;

  return {
    farm_type: $("onb-farm-type")?.value,
    income_items: incomeItems,
    cost_items: costItems,
    loan_items: loanItems,
    current_cash: currentCash,
  };
}

async function submitOnboardingForm(e) {
  e.preventDefault();
  const payload = collectOnboardingPayload();
  if (!payload.farm_type) {
    showStatus("Please choose a farm type.", "error");
    return;
  }
  try {
    const data = await api(`/farmer/onboarding${sectorsQuery()}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const s = data.summary;
    const resultBox = $("onboarding-result");
    if (resultBox) {
      resultBox.classList.remove("hidden");
      resultBox.innerHTML = `
        <p><strong>Farm Setup saved.</strong></p>
        <p>${s.income_budgets_set} income budget(s) and ${s.cost_budgets_set} cost budget(s) set for ${s.year}, totalling ${formatCurrency(s.total_annual_income_budgeted)} income and ${formatCurrency(s.total_annual_cost_budgeted)} costs (naive net: ${formatCurrency(s.naive_annual_net)}).</p>
        ${s.current_cash_set ? `<p>Current cash on hand set to ${formatCurrency(s.current_cash)}.</p>` : ""}
      `;
    }
    showStatus("Farm Setup saved.", "success");
    await loadOnboarding();
    await refreshFarmData();
    if (state.analysis) await runAnalysis(false);
  } catch (err) {
    showStatus(err.message, "error");
  }
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
    if (state.activeSubtab === "ap-recommendations") await loadFinancialIntelligence();
    if (state.activeSubtab === "ap-ask") clearFiChat(true);
    if (state.activeSubtab === "cashflow-forecast" || state.view === "advanced-analysis") await ensureAdvancedForecast();
    if (state.activeSubtab === "fp-historical") await loadHistoricalData();
    if (state.activeSubtab === "cashflow-budget") { await loadCashflowBudget(); await loadCategoryBudgets(); }
    if (state.activeSubtab === "ap-reports") $("report-preview")?.classList.add("hidden");
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

const WHATIF_PRESETS = {
  milk_down: { label: "Milk price drops 10c/L", inputs: { milk_price_cents_change: -10 } },
  milk_up: { label: "Milk price rises 5c/L", inputs: { milk_price_cents_change: 5 } },
  feed_up: { label: "Feed costs rise 15%", inputs: { feed_pct_change: 15 } },
  fert_up: { label: "Fertiliser costs rise 20%", inputs: { fertiliser_pct_change: 20 } },
  fuel_up: { label: "Fuel costs rise 25%", inputs: { fuel_pct_change: 25 } },
};

async function runSandbox(overrideInputs = null, label = "Custom scenario") {
  const btn = $("run-sandbox-btn");
  if (btn) btn.disabled = true;
  if (!overrideInputs) {
    document.querySelectorAll(".whatif-preset-btn").forEach((b) => b.classList.remove("active"));
  }
  showStatus("Running scenario…", "info");
  try {
    const inputs = overrideInputs || getSandboxInputs();
    const data = await api("/farmer/scenario-sandbox", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: sectorsBody(inputs),
    });
    if ($("whatif-active-label")) $("whatif-active-label").textContent = label;
    renderSandboxResults(data);
    showStatus("Scenario complete.", "success");
  } catch (err) {
    showStatus(err.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function runWhatIfPreset(presetKey, btn) {
  const preset = WHATIF_PRESETS[presetKey];
  if (!preset) return;
  document.querySelectorAll(".whatif-preset-btn").forEach((b) => b.classList.toggle("active", b === btn));
  runSandbox(preset.inputs, preset.label);
}

function renderCashflowActionsResults(data) {
  const summary = $("cashflow-actions-summary");
  if (summary) {
    summary.classList.remove("hidden");
    summary.innerHTML = `Current lowest cash balance: ${formatCurrency(data.base_lowest_balance)} `
      + `(${data.base_deficit_months || 0} month${data.base_deficit_months === 1 ? "" : "s"} in deficit over the next 12 months). `
      + periodBadgeHtml(data.period);
  }
  const table = $("cashflow-actions-table");
  if (!table) return;
  const rows = (data.results || []).map((r) => `
    <tr>
      <td><strong>${r.label}</strong><br><span class="muted">${r.description}</span></td>
      <td>${formatCurrency(r.lowest_balance_scenario)}</td>
      <td>${r.deficit_months_scenario}</td>
      <td class="${signClass(r.improvement)}">${formatCurrency(r.improvement)}</td>
    </tr>`).join("");
  table.innerHTML = `
    <table class="data-table">
      <thead><tr><th>Action</th><th>Lowest balance after</th><th>Deficit months after</th><th>Improvement</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

async function testAllCashflowActions() {
  const btn = $("test-all-actions-btn");
  if (btn) btn.disabled = true;
  showStatus("Testing all cash-flow actions…", "info");
  try {
    const data = await api(`/farmer/cashflow-actions${sectorsQuery()}`);
    renderCashflowActionsResults(data);
    showStatus("Cash-flow actions tested.", "success");
  } catch (err) {
    showStatus(err.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function getCashflowActionInputs() {
  const val = (id) => { const v = $(id)?.value; return v === "" || v == null ? undefined : parseFloat(v); };
  const intVal = (id) => { const v = $(id)?.value; return v === "" || v == null ? undefined : parseInt(v, 10); };
  const action = $("cfa-action")?.value || "bring_forward_sales";
  const amount = val("cfa-amount");
  const from = intVal("cfa-from-month");
  const to = intVal("cfa-to-month");
  const inputs = { action, amount };
  if (action === "use_short_term_credit") {
    inputs.draw_month = from;
    inputs.repay_month = to;
  } else if (action === "match_payments_to_surplus") {
    inputs.payment_month = from;
  } else {
    inputs.from_month = from;
    inputs.to_month = to;
  }
  return inputs;
}

async function testOneCashflowAction() {
  const btn = $("test-one-action-btn");
  if (btn) btn.disabled = true;
  showStatus("Testing action…", "info");
  try {
    const data = await api("/farmer/cashflow-action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: sectorsBody(getCashflowActionInputs()),
    });
    const box = $("cashflow-action-result");
    if (box) {
      box.classList.remove("hidden");
      box.innerHTML = `
        <strong>${data.label}</strong><br>
        ${data.description}<br><br>
        Lowest balance: ${formatCurrency(data.lowest_balance_base)} → ${formatCurrency(data.lowest_balance_scenario)}<br>
        Deficit months: ${data.deficit_months_base} → ${data.deficit_months_scenario}`;
    }
    showStatus("Action tested.", "success");
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
  setupSubtabs();
  $("run-sandbox-btn")?.addEventListener("click", () => runSandbox());
  document.querySelectorAll(".whatif-preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => runWhatIfPreset(btn.dataset.preset, btn));
  });
  $("test-all-actions-btn")?.addEventListener("click", testAllCashflowActions);
  $("test-one-action-btn")?.addEventListener("click", testOneCashflowAction);
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

  $("ie-add-entry-btn")?.addEventListener("click", () => openIeEntryForm());
  $("ie-cancel-entry-btn")?.addEventListener("click", closeIeEntryForm);
  $("ie-entry-form")?.addEventListener("submit", submitIeEntryForm);
  $("ie-entry-type")?.addEventListener("change", populateIeCategorySelect);

  $("cb-add-budget-btn")?.addEventListener("click", () => openCbBudgetForm());
  $("cb-cancel-budget-btn")?.addEventListener("click", closeCbBudgetForm);
  $("cb-budget-form")?.addEventListener("submit", submitCbBudgetForm);
  $("cb-record-type")?.addEventListener("change", () => { $("cb-category").innerHTML = ieCategoryOptions($("cb-record-type").value); });
  $("cb-period-mode")?.addEventListener("change", cbUpdatePeriodFields);

  $("doc-add-btn")?.addEventListener("click", () => openDocForm());
  $("doc-cancel-btn")?.addEventListener("click", closeDocForm);
  $("doc-form")?.addEventListener("submit", submitDocForm);
  $("doc-record-type")?.addEventListener("change", populateDocCategorySelect);
  $("doc-payment-status")?.addEventListener("change", docUpdatePaymentDateVisibility);
  $("doc-type")?.addEventListener("change", () => { if (!$("doc-id").value) docApplyTypeDefaults(); });

  $("onb-add-loan")?.addEventListener("click", addOnboardingLoanRow);
  $("onboarding-form")?.addEventListener("submit", submitOnboardingForm);
}

document.addEventListener("DOMContentLoaded", () => {
  setupNav();
  loadInitial().catch((err) => showStatus(err.message, "error"));
});
