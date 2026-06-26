const cityColors = {
  NYC: "#2563eb",
  CHI: "#7c3aed",
  MIA: "#0d9488",
  LAX: "#e0820c",
  DEN: "#0ea5e9",
  AUS: "#dc2626",
  BOS: "#4f46e5",
};

const DEG = "\u00b0";
const CENT = "\u00a2";
const EN_DASH = "\u2013";
const LE = "\u2264";
const GE = "\u2265";
const MINUS = "\u2212";
const UP = "\u25b2";
const DOWN = "\u25bc";
const MID = "\u00b7";

const temp = (value) => `${value}${DEG}`;
const range = (low, high) => `${low}${EN_DASH}${high}${DEG}`;
const $ = (id) => document.getElementById(id);

const distributions = {
  nyc: [[`${LE}${temp(85)}`, 5, 4], [range(86, 87), 18, 16], [range(88, 89), 33, 24], [range(90, 91), 28, 31], [range(92, 93), 12, 14], [`${GE}${temp(94)}`, 4, 5]],
  chi: [[`${LE}${temp(82)}`, 9, 10], [temp(83), 17, 16], [range(84, 85), 41, 38], [range(86, 87), 24, 27], [`${GE}${temp(88)}`, 9, 9]],
  lax: [[`${LE}${temp(73)}`, 11, 13], [temp(74), 21, 20], [range(75, 76), 49, 52], [range(77, 78), 15, 12], [`${GE}${temp(79)}`, 4, 3]],
  den: [[`${LE}${temp(68)}`, 10, 12], [range(69, 70), 26, 29], [range(71, 72), 36, 29], [range(73, 74), 20, 22], [`${GE}${temp(75)}`, 8, 8]],
  bos: [[`${LE}${temp(76)}`, 8, 10], [range(77, 78), 25, 26], [range(79, 80), 52, 44], [range(81, 82), 12, 16], [`${GE}${temp(83)}`, 3, 4]],
  miaRain: [["YES", 78, 71], ["NO", 22, 29]],
  ausHeat: [["YES", 60, 64], ["NO", 40, 36]],
};

let markets = [
  { id: "NYC-88", source: "sample", city: "NYC", eventType: "temperature", ticker: "HIGHNY-26JUN18-B88.5", title: `NYC ${MID} Daily High`, bracket: range(88, 89), last: 24, bid: 23, ask: 25, model: 33, vol: "142K", volumeNumber: 142000, ch: 2, conf: 82, dist: "nyc", timestamp: null },
  { id: "NYC-90", source: "sample", city: "NYC", eventType: "temperature", ticker: "HIGHNY-26JUN18-B90.5", title: `NYC ${MID} Daily High`, bracket: range(90, 91), last: 31, bid: 30, ask: 32, model: 28, vol: "118K", volumeNumber: 118000, ch: -1, conf: 64, dist: "nyc", timestamp: null },
  { id: "NYC-86", source: "sample", city: "NYC", eventType: "temperature", ticker: "HIGHNY-26JUN18-B86.5", title: `NYC ${MID} Daily High`, bracket: range(86, 87), last: 16, bid: 15, ask: 17, model: 18, vol: "74K", volumeNumber: 74000, ch: 1, conf: 55, dist: "nyc", timestamp: null },
  { id: "CHI-84", source: "sample", city: "CHI", eventType: "temperature", ticker: "HIGHCHI-26JUN18-B84.5", title: `Chicago ${MID} Daily High`, bracket: range(84, 85), last: 38, bid: 37, ask: 39, model: 41, vol: "96K", volumeNumber: 96000, ch: 1, conf: 61, dist: "chi", timestamp: null },
  { id: "MIA-RN", source: "sample", city: "MIA", eventType: "rain", ticker: "RAINMIA-26JUN18-YES", title: `Miami ${MID} Rain Today`, bracket: "YES", last: 71, bid: 70, ask: 72, model: 78, vol: "63K", volumeNumber: 63000, ch: 3, conf: 77, dist: "miaRain", timestamp: null },
  { id: "LAX-75", source: "sample", city: "LAX", eventType: "temperature", ticker: "HIGHLA-26JUN18-B75.5", title: `Los Angeles ${MID} Daily High`, bracket: range(75, 76), last: 52, bid: 51, ask: 53, model: 49, vol: "58K", volumeNumber: 58000, ch: -2, conf: 58, dist: "lax", timestamp: null },
  { id: "DEN-71", source: "sample", city: "DEN", eventType: "temperature", ticker: "HIGHDEN-26JUN18-B71.5", title: `Denver ${MID} Daily High`, bracket: range(71, 72), last: 29, bid: 28, ask: 30, model: 36, vol: "47K", volumeNumber: 47000, ch: -1, conf: 69, dist: "den", timestamp: null },
  { id: "AUS-100", source: "sample", city: "AUS", eventType: "heat", ticker: "HEATAUS-26JUN18-YES", title: `Austin ${MID} High ${GE} 100${DEG}F`, bracket: "YES", last: 64, bid: 63, ask: 65, model: 60, vol: "81K", volumeNumber: 81000, ch: -2, conf: 60, dist: "ausHeat", timestamp: null },
  { id: "BOS-79", source: "sample", city: "BOS", eventType: "temperature", ticker: "HIGHBOS-26JUN18-B79.5", title: `Boston ${MID} Daily High`, bracket: range(79, 80), last: 44, bid: 43, ask: 45, model: 52, vol: "39K", volumeNumber: 39000, ch: 2, conf: 74, dist: "bos", timestamp: null },
].map(withEdge);

let positions = [
  [`NYC ${range(88, 89)}`, "YES", 300, `19${CENT}`, `24${CENT}`, "+$15.00", "+26.3%", true],
  ["MIA Rain", "YES", 150, `64${CENT}`, `71${CENT}`, "+$10.50", "+10.9%", true],
  [`CHI ${range(84, 85)}`, "YES", 200, `35${CENT}`, `38${CENT}`, "+$6.00", "+8.6%", true],
  [`AUS ${GE}100${DEG}`, "NO", 180, `33${CENT}`, `36${CENT}`, "+$5.40", "+9.1%", true],
  [`DEN ${range(71, 72)}`, "YES", 120, `33${CENT}`, `29${CENT}`, `${MINUS}$4.80`, `${MINUS}12.1%`, false],
  [`LAX ${range(75, 76)}`, "YES", 90, `55${CENT}`, `52${CENT}`, `${MINUS}$2.70`, `${MINUS}5.5%`, false],
];

const state = {
  selectedId: "NYC-88",
  side: "BUY",
  qty: 240,
  limit: 25,
  filters: {
    city: "",
    signal: "",
    eventType: "",
    minEdge: "",
    minConfidence: "",
  },
  artifacts: {
    dashboard: { status: "loading", text: "Dashboard payload loading" },
    backtest: { status: "loading", text: "Backtest artifact loading" },
  },
  dataMode: "sample",
  generatedAt: null,
  freshestMarketAt: null,
  risk: null,
  backtest: null,
  paper: null,
  opportunities: [],
  fills: [],
};

function withEdge(market) {
  return { ...market, edge: market.model - market.last };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value;
}

function setHtml(id, value) {
  const el = $(id);
  if (el) el.innerHTML = value;
}

function setMetric(id, value, className = "") {
  const el = $(id);
  if (!el) return;
  el.textContent = value;
  el.className = className;
}

function cents(value) {
  if (!Number.isFinite(Number(value))) return "N/A";
  return `${Number(value).toFixed(Number.isInteger(Number(value)) ? 0 : 1)}${CENT}`;
}

function usd(value) {
  if (!Number.isFinite(Number(value))) return "N/A";
  return `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatPercent(value, digits = 1, signed = false) {
  if (!Number.isFinite(Number(value))) return "N/A";
  const sign = signed && value > 0 ? "+" : "";
  return `${sign}${(Number(value) * 100).toFixed(digits)}%`;
}

function formatPercentMaybeRatio(value, digits = 1, signed = false) {
  if (!Number.isFinite(Number(value))) return "N/A";
  const normalized = Math.abs(Number(value)) > 1 ? Number(value) / 100 : Number(value);
  return formatPercent(normalized, digits, signed);
}

function formatRatio(value) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(2) : "N/A";
}

function formatMetricEdge(value) {
  if (!Number.isFinite(Number(value))) return "N/A";
  const centsValue = Number(value) * 100;
  return `${centsValue > 0 ? "+" : ""}${centsValue.toFixed(1)}${CENT}`;
}

function edgeText(value) {
  if (!Number.isFinite(Number(value))) return "N/A";
  return `${Number(value) > 0 ? "+" : ""}${Number(value).toFixed(0)}${CENT}`;
}

function edgeClass(value) {
  return Number(value) > 0 ? "positive" : Number(value) < 0 ? "negative" : "";
}

function signalFor(edge) {
  return edge >= 5 ? "BUY" : edge <= -4 ? "SELL" : "HOLD";
}

function signalClass(signal) {
  return `signal-badge signal-${String(signal).toLowerCase()}`;
}

function normalizeProbabilityPercent(value, fallback = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.round(number <= 1 ? number * 100 : number);
}

function parseVolume(value) {
  if (Number.isFinite(Number(value))) return Number(value);
  const text = String(value || "").trim().toUpperCase();
  if (!text) return 0;
  const parsed = Number.parseFloat(text);
  if (!Number.isFinite(parsed)) return 0;
  if (text.endsWith("M")) return parsed * 1000000;
  if (text.endsWith("K")) return parsed * 1000;
  return parsed;
}

function formatVolume(value) {
  const number = Number(value || 0);
  if (number >= 1000000) return `${(number / 1000000).toFixed(1)}M`;
  if (number >= 1000) return `${Math.round(number / 1000)}K`;
  return number ? String(number) : "N/A";
}

function formatTimestamp(value) {
  if (!value) return "N/A";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "N/A";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

function selectedMarket() {
  return markets.find((market) => market.id === state.selectedId) ?? markets[0];
}

function filteredMarkets() {
  const minEdge = Number(state.filters.minEdge);
  const minConfidence = Number(state.filters.minConfidence);
  return markets.filter((market) => {
    if (state.filters.city && market.city !== state.filters.city) return false;
    if (state.filters.signal && signalFor(market.edge) !== state.filters.signal) return false;
    if (state.filters.eventType && market.eventType !== state.filters.eventType) return false;
    if (Number.isFinite(minEdge) && state.filters.minEdge !== "" && market.edge < minEdge) return false;
    if (Number.isFinite(minConfidence) && state.filters.minConfidence !== "" && market.conf < minConfidence) return false;
    return true;
  });
}

function colorCity(el, city) {
  if (!el) return;
  el.textContent = city;
  el.style.color = cityColors[city] ?? "#475569";
}

function seed(n, last) {
  const x = Math.sin(n * 97.13 + last * 1.7) * 10000;
  return Math.abs(x - Math.floor(x));
}

function createBookRows(market) {
  const asks = [];
  const bids = [];
  for (let i = 0; i < 6; i += 1) {
    const askPx = market.ask + i;
    const bidPx = market.bid - i;
    if (askPx <= 99) asks.push({ px: askPx, sz: Math.round(30 + seed(i + 1, market.last) * 440), side: "ask" });
    if (bidPx >= 1) bids.push({ px: bidPx, sz: Math.round(30 + seed(i + 40, market.last) * 440), side: "bid" });
  }
  const maxSize = Math.max(...asks.map((row) => row.sz), ...bids.map((row) => row.sz), 1);
  return { asks: asks.reverse(), bids, maxSize };
}

function renderClock() {
  const now = new Date();
  setText("clock", new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "America/New_York",
  }).format(now));
}

function renderArtifactStates() {
  const dashboard = state.artifacts.dashboard;
  const backtest = state.artifacts.backtest;
  const freshnessParts = [];
  if (state.generatedAt) freshnessParts.push(`PAYLOAD ${formatTimestamp(state.generatedAt)}`);
  if (state.freshestMarketAt) freshnessParts.push(`MARKET ${formatTimestamp(state.freshestMarketAt)}`);
  if (state.dataMode === "generated" && !markets.some((market) => market.source === "generated")) freshnessParts.push("MARKETS SAMPLE");
  setText("data-mode-label", state.dataMode === "generated" ? "GENERATED DATA" : "SAMPLE DATA");
  setText("freshness-label", freshnessParts.length ? freshnessParts.join(" / ") : "NO GENERATED PAYLOAD");
  setText("dashboard-artifact-state", dashboard.text);
  setText("backtest-artifact-state", backtest.text);
  $("dashboard-artifact-state").className = stateClass(dashboard.status);
  $("backtest-artifact-state").className = stateClass(backtest.status);
  $("data-mode-pill").className = `data-mode-pill ${state.dataMode === "generated" ? "state-ok" : "state-warn"}`;
  setText("backtest-panel-state", backtest.text);
  $("backtest-panel-state").className = `artifact-status ${stateClass(backtest.status)}`;
}

function stateClass(status) {
  if (status === "loaded") return "state-ok";
  if (status === "error") return "state-error";
  return "state-warn";
}

function renderFilters() {
  syncSelectOptions("filter-city", [...new Set(markets.map((market) => market.city).filter(Boolean))].sort(), "All");
  syncSelectOptions("filter-event", [...new Set(markets.map((market) => market.eventType).filter(Boolean))].sort(), "All");
  $("filter-city").value = state.filters.city;
  $("filter-signal").value = state.filters.signal;
  $("filter-event").value = state.filters.eventType;
  $("filter-edge").value = state.filters.minEdge;
  $("filter-confidence").value = state.filters.minConfidence;
}

function syncSelectOptions(id, values, allLabel) {
  const select = $(id);
  const current = select.value;
  select.replaceChildren(option("", allLabel), ...values.map((value) => option(value, value.toUpperCase())));
  select.value = values.includes(current) ? current : "";
}

function option(value, label) {
  const el = document.createElement("option");
  el.value = value;
  el.textContent = label;
  return el;
}

function renderMarkets() {
  const visible = filteredMarkets();
  $("open-count").textContent = `${visible.length}/${markets.length} OPEN`;
  $("market-empty-state").classList.toggle("hidden", visible.length > 0);
  $("market-list").replaceChildren(...visible.map((market) => {
    const signal = signalFor(market.edge);
    const row = document.createElement("button");
    row.type = "button";
    row.className = `market-row${market.id === state.selectedId ? " active" : ""}`;
    row.innerHTML = `
      <div>
        <span class="city-badge" style="color:${cityColors[market.city] ?? "#475569"}">${escapeHtml(market.city)}</span>
        <strong>${escapeHtml(market.bracket)}</strong>
        <span class="${signalClass(signal)}">${signal}</span>
      </div>
      <div class="meta">
        <span class="label">LAST</span>
        <strong>${cents(market.last)}</strong>
        <span class="label">EDGE</span>
        <strong class="${edgeClass(market.edge)}">${edgeText(market.edge)}</strong>
        <span class="volume">${market.source === "generated" ? "" : "SAMPLE · "}${escapeHtml(market.vol)}</span>
      </div>
    `;
    row.addEventListener("click", () => selectMarket(market));
    return row;
  }));
}

function selectMarket(market) {
  state.selectedId = market.id;
  state.limit = state.side === "BUY" ? market.ask : Math.max(1, 100 - market.bid);
  render();
}

function renderDetail() {
  const market = selectedMarket();
  if (!market) return;
  const signal = signalFor(market.edge);
  setText("selected-ticker", market.ticker);
  colorCity($("selected-city"), market.city);
  setText("selected-title", market.title);
  $("selected-signal").className = signalClass(signal);
  setText("selected-signal", `${signal} SIGNAL`);
  setText("selected-contract-label", `CONTRACT ${MID} ${market.bracket}`);
  setText("selected-last", cents(market.last));
  setText("selected-change", `${market.ch > 0 ? `${UP} +` : market.ch < 0 ? `${DOWN} ${MINUS}` : ""}${Math.abs(market.ch)}${CENT} 24h`);
  $("selected-change").className = market.ch >= 0 ? "positive" : "negative";
  setText("selected-bid", cents(market.bid));
  setText("selected-ask", cents(market.ask));
  setText("selected-spread", cents(market.ask - market.bid));
  setText("selected-volume", market.vol);
  setText("selected-edge", edgeText(market.edge));
  $("selected-edge").className = edgeClass(market.edge);
  setText("selected-model", `${market.model}%`);
  setText("selected-market", `${market.last}%`);
  setText("selected-fair", cents(market.model));
  setText("selected-confidence", `${market.conf}%`);
  $("confidence-bar").style.width = `${Math.max(0, Math.min(market.conf, 100))}%`;
  setText("model-refresh-label", market.timestamp ? `market snapshot ${formatTimestamp(market.timestamp)}` : "sample model refresh");
}

function renderDistribution() {
  const market = selectedMarket();
  if (!market) return;
  const rows = distributions[market.dist] ?? [[market.bracket, market.model, market.last]];
  const maxValue = Math.max(...rows.map((row) => Math.max(row[1], row[2])), 1);
  $("distribution-list").replaceChildren(...rows.map(([label, model, marketValue]) => {
    const active = label === market.bracket;
    const row = document.createElement("div");
    row.className = `dist-row${active ? " active" : ""}`;
    row.innerHTML = `
      <span>${escapeHtml(label)}</span>
      <div class="dist-bar">
        <div class="dist-fill" style="width:${(model / maxValue * 100).toFixed(1)}%"></div>
        <div class="dist-tick" style="left:${(marketValue / maxValue * 100).toFixed(1)}%"></div>
      </div>
      <span class="dist-model">${model}%</span>
      <span class="dist-market">${marketValue}%</span>
    `;
    return row;
  }));
}

function renderOrderbook() {
  const market = selectedMarket();
  if (!market) return;
  const { asks, bids, maxSize } = createBookRows(market);
  const rows = [];
  for (const row of asks) rows.push(bookRow(row, maxSize));
  const last = document.createElement("div");
  last.className = "last-trade";
  last.innerHTML = `<strong>${cents(market.last)}</strong><span>LAST TRADE</span>`;
  rows.push(last);
  for (const row of bids) rows.push(bookRow(row, maxSize));
  setText("book-spread", `SPREAD ${cents(market.ask - market.bid)}`);
  $("orderbook").replaceChildren(...rows);
}

function bookRow(row, maxSize) {
  const el = document.createElement("div");
  el.className = "book-row";
  el.innerHTML = `
    <div class="depth ${row.side}-depth" style="width:${(row.sz / maxSize * 100).toFixed(0)}%"></div>
    <span class="px ${row.side === "ask" ? "negative" : "positive"}">${cents(row.px)}</span>
    <span class="sz">${row.sz.toLocaleString()}</span>
  `;
  return el;
}

function renderTicket() {
  const market = selectedMarket();
  if (!market) return;
  const buy = state.side === "BUY";
  const cost = state.qty * state.limit / 100;
  const maxProfit = state.qty * (100 - state.limit) / 100;
  $("buy-button").className = buy ? "active buy" : "";
  $("sell-button").className = buy ? "" : "active sell";
  setText("ticket-contract", `${market.city} ${market.bracket}`);
  setText("ticket-ticker", market.ticker);
  setText("ticket-qty", state.qty.toLocaleString());
  setText("ticket-limit", cents(state.limit));
  setText("ticket-r1-label", buy ? "EST. COST" : "EST. CREDIT");
  setText("ticket-r1-value", usd(cost));
  setText("ticket-payout", usd(state.qty));
  setText("ticket-r3-label", buy ? "MAX PROFIT" : "MAX LOSS");
  setText("ticket-r3-value", usd(maxProfit));
  $("ticket-r3-value").className = buy ? "positive" : "negative";
  $("ticket-submit").className = `submit-order ${buy ? "buy" : "sell"}`;
  setText("ticket-submit", `SIMULATE ${state.side} ${state.qty} ${market.bracket} @ ${state.limit}${CENT}`);
  renderTicketPreview(market, cost);
}

function renderTicketPreview(market, exposure) {
  const spread = market.ask - market.bid;
  const fillRisk = spread >= 5 ? "HIGH" : spread >= 3 ? "MED" : "LOW";
  const feeAdjustedEdge = state.side === "BUY" ? market.model - state.limit - 1 : 100 - market.model - state.limit - 1;
  const reasons = [];
  if (market.source !== "generated") reasons.push(["warn", "SAMPLE_MARKET"]);
  if (feeAdjustedEdge < 0) reasons.push(["danger", "NEGATIVE_AFTER_FEES"]);
  if (market.conf < 60) reasons.push(["warn", "LOW_CONFIDENCE"]);
  if (spread > 3) reasons.push(["warn", "WIDE_SPREAD"]);
  if (state.risk?.overexposed_clusters?.length) reasons.push(["warn", "CHECK_CORRELATION"]);
  if (!market.timestamp && state.dataMode === "generated") reasons.push(["warn", "NO_MARKET_TIMESTAMP"]);
  if (!reasons.length) reasons.push(["", "REVIEW_OK"]);

  const riskImpact = state.risk
    ? `${usd(exposure)} / ${formatPercentMaybeRatio(state.risk.exposure_pct_of_bankroll ?? 0)} current exposure`
    : `${usd(exposure)} exposure, no risk payload`;

  setHtml("ticket-preview", `
    <strong>PRE-ORDER REVIEW</strong>
    <div class="preview-grid">
      <div><span>FEE-ADJ EDGE</span><b class="${edgeClass(feeAdjustedEdge)}">${edgeText(feeAdjustedEdge)}</b></div>
      <div><span>FILL RISK</span><b>${fillRisk} / ${cents(spread)} spread</b></div>
      <div><span>EXPOSURE IMPACT</span><b>${escapeHtml(riskImpact)}</b></div>
      <div><span>MARKET DATA</span><b>${market.source === "generated" ? "GENERATED" : "SAMPLE"}</b></div>
    </div>
    <div class="reason-list">${reasons.map(([kind, label]) => `<b class="${kind}">${label}</b>`).join("")}</div>
  `);
}

function renderPositions() {
  const totalPnl = positions.reduce((sum, position) => {
    const raw = String(position[5]).replace(/[$,+]/g, "").replace(MINUS, "-");
    const parsed = Number.parseFloat(raw);
    return Number.isFinite(parsed) ? sum + parsed : sum;
  }, 0);
  setHtml("positions-summary", `UNREALIZED <b class="${totalPnl >= 0 ? "positive" : "negative"}">${totalPnl >= 0 ? "+" : ""}${usd(totalPnl)}</b>`);
  $("positions-list").replaceChildren(...positions.map((position) => {
    const [contract, side, qty, avg, mark, pnl, pct, profitable] = position;
    const row = document.createElement("div");
    row.className = "position-row";
    row.innerHTML = `
      <span>${escapeHtml(contract)} <b class="${side === "NO" ? "negative" : "positive"}">${escapeHtml(side)}</b></span>
      <span>${Number(qty).toLocaleString()}</span>
      <span>${escapeHtml(avg)}</span>
      <span>${escapeHtml(mark)}</span>
      <span class="${profitable ? "positive" : "negative"}">${escapeHtml(pnl)}<br><b>${escapeHtml(pct)}</b></span>
    `;
    return row;
  }));
}

function renderRisk() {
  const risk = state.risk;
  if (!risk) {
    setText("risk-state", "NO RISK PAYLOAD");
    setText("risk-exposure", "N/A");
    setText("risk-bankroll", "N/A");
    setText("risk-worst", "N/A");
    setText("risk-likely", "N/A");
    setHtml("risk-clusters", `<div class="risk-row"><div><strong>Sample mode</strong><small>Generate dashboard data to inspect exposure clusters.</small></div></div>`);
    setHtml("hedge-candidates", "");
    return;
  }

  const clusters = Array.isArray(risk.overexposed_clusters) ? risk.overexposed_clusters : [];
  const hedges = Array.isArray(risk.hedge_candidates) ? risk.hedge_candidates : [];
  setText("risk-state", clusters.length ? `${clusters.length} WARNINGS` : "IN LIMITS");
  setText("risk-exposure", usd(risk.total_exposure ?? 0));
  setText("risk-bankroll", formatPercentMaybeRatio(risk.exposure_pct_of_bankroll ?? 0));
  setText("risk-worst", usd(risk.worst_case_pnl ?? 0));
  setMetric("risk-likely", usd(risk.likely_case_pnl ?? 0), Number(risk.likely_case_pnl) >= 0 ? "positive" : "negative");

  const clusterRows = clusters.slice(0, 4).map((cluster) => `
    <div class="risk-row warn">
      <div>
        <span class="label">${escapeHtml(cluster.category || "cluster")}</span>
        <strong>${escapeHtml(cluster.key || "unknown")}</strong>
        <small>${escapeHtml((cluster.reason_codes || []).join(", "))}</small>
      </div>
      <b>${usd(cluster.exposure ?? 0)}</b>
    </div>
  `).join("");
  setHtml("risk-clusters", clusterRows || `<div class="risk-row"><div><strong>No overexposed clusters</strong><small>Current generated positions are inside configured correlated limits.</small></div></div>`);

  const hedgeRows = hedges.slice(0, 3).map((hedge) => `
    <div class="risk-row">
      <div>
        <span class="label">HEDGE</span>
        <strong>${escapeHtml(hedge.long_ticker)} / ${escapeHtml(hedge.short_ticker)}</strong>
        <small>${escapeHtml(hedge.shared_group || "shared risk bucket")}</small>
      </div>
      <b>${usd(hedge.hedged_exposure ?? 0)}</b>
    </div>
  `).join("");
  setHtml("hedge-candidates", hedgeRows);
}

function renderOpportunityQueue() {
  const ranked = (state.opportunities.length ? state.opportunities : markets.map(derivedOpportunity))
    .sort((left, right) => right.score - left.score)
    .slice(0, 6);

  setText("opportunity-count", `${ranked.length} RANKED`);
  $("opportunity-list").replaceChildren(...ranked.map((item, index) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "opportunity-row";
    row.innerHTML = `
      <span class="rank">${index + 1}</span>
      <span><strong>${escapeHtml(item.title)}</strong><small>${escapeHtml(item.reasons.join(", "))}</small></span>
      <span class="score ${edgeClass(item.edge)}">${edgeText(item.edge)}</span>
    `;
    row.addEventListener("click", () => {
      const market = markets.find((candidate) => candidate.id === item.marketId || candidate.ticker === item.ticker);
      if (market) selectMarket(market);
    });
    return row;
  }));
}

function derivedOpportunity(market) {
  const spreadPenalty = Math.max(0, market.ask - market.bid - 2);
  const confidenceBonus = (market.conf - 50) / 10;
  const volumeBonus = Math.min(parseVolume(market.vol) / 50000, 4);
  const score = market.edge + confidenceBonus + volumeBonus - spreadPenalty;
  const reasons = [];
  if (market.edge >= 5) reasons.push("EDGE_OK");
  if (market.edge < 0) reasons.push("NEGATIVE_EDGE");
  if (market.conf < 60) reasons.push("LOW_CONFIDENCE");
  if (market.ask - market.bid > 3) reasons.push("WIDE_SPREAD");
  if (!reasons.length) reasons.push("WATCH");
  return {
    marketId: market.id,
    ticker: market.ticker,
    title: `${signalFor(market.edge)} ${market.city} ${market.bracket}`,
    edge: market.edge,
    score,
    reasons,
  };
}

function renderWeather() {
  const weather = state.weather;
  if (!weather) {
    setText("weather-title", "WEATHER FEED · SAMPLE");
    setText("weather-station", "NO PAYLOAD");
    setText("weather-location", "SAMPLE · CENTRAL PARK");
    setText("weather-current", `84${DEG}F`);
    setText("weather-dew", `61${DEG}`);
    setText("weather-wind", "SW 9");
    setText("weather-rh", "46%");
    setText("weather-change", "SAMPLE TREND");
    setText("weather-ensemble", "SAMPLE ENSEMBLE · NOT LIVE");
    setText("weather-alert", "SAMPLE");
    return;
  }

  setText("weather-title", `WEATHER FEED · ${weather.city || weather.location || "GENERATED"}`);
  setText("weather-station", `${weather.station || "PAYLOAD"} · ${formatTimestamp(weather.updated_at || weather.timestamp)}`);
  setText("weather-location", weather.label || weather.location || "GENERATED WEATHER");
  setText("weather-current", Number.isFinite(Number(weather.current_temp)) ? `${weather.current_temp}${DEG}F` : "N/A");
  setText("weather-dew", Number.isFinite(Number(weather.dewpoint)) ? `${weather.dewpoint}${DEG}` : "N/A");
  setText("weather-wind", weather.wind || "N/A");
  setText("weather-rh", Number.isFinite(Number(weather.relative_humidity)) ? `${weather.relative_humidity}%` : "N/A");
  setText("weather-change", weather.trend || "GENERATED");
  renderGuidance(weather.guidance);
  setText("weather-ensemble", weather.ensemble || "Generated weather payload");
  setText("weather-alert", weather.alert || "NO ALERT");
}

function renderGuidance(guidance) {
  if (!guidance || typeof guidance !== "object") return;
  const entries = Object.entries(guidance).slice(0, 5);
  $("guidance-row").replaceChildren(...entries.map(([name, value]) => {
    const el = document.createElement("div");
    el.innerHTML = `<span>${escapeHtml(name)}</span><strong>${escapeHtml(value)}${Number.isFinite(Number(value)) ? DEG : ""}</strong>`;
    return el;
  }));
}

function renderVenue() {
  const venue = state.venue;
  if (!venue) {
    setText("venue-name", "KALSHI");
    setText("venue-latency", state.dataMode === "generated" ? "NO HEALTH" : "SAMPLE");
    $("venue-status-dot").style.background = state.dataMode === "generated" ? "#d97706" : "#94a3b8";
    return;
  }
  setText("venue-name", venue.name || "KALSHI");
  setText("venue-latency", Number.isFinite(Number(venue.latency_ms)) ? `${venue.latency_ms}ms` : (venue.status || "PAYLOAD"));
  $("venue-status-dot").style.background = venue.ok === false ? "#c0392b" : "#16a34a";
}

function renderFills() {
  const feed = state.fills;
  if (feed.length) {
    setText("fills-label", "GENERATED FILLS");
    setHtml("fills-feed", feed.slice(0, 8).map((fill) => {
      const action = String(fill.action || fill.side || "fill").toUpperCase();
      const className = action.includes("SELL") || action.includes("SLD") ? "negative" : "positive";
      return `${formatTimestamp(fill.timestamp)} <b class="${className}">${escapeHtml(action)}</b> ${escapeHtml(fill.quantity ?? "")} ${escapeHtml(fill.ticker || fill.contract || "")} @${cents(fill.price ?? fill.fill_price ?? fill.average_price ?? 0)}`;
    }).join(` ${MID} `));
    return;
  }
  if (state.paper?.event_count) {
    setText("fills-label", "PAPER LEDGER");
    setText("fills-feed", `${state.paper.event_count} paper events · ${state.paper.open_positions?.length || 0} open positions · realized ${usd(state.paper.realized_pnl || 0)}`);
    return;
  }
  setText("fills-label", state.dataMode === "generated" ? "NO FILLS" : "SAMPLE FILLS");
  setText("fills-feed", state.dataMode === "generated" ? "Generated dashboard payload did not include recent fills." : "No generated fills payload loaded.");
}

function renderBacktestSummary(summary) {
  state.backtest = summary;
  setText("backtest-strategy-label", "ENGINE OUTPUT");
  setMetric("backtest-sharpe", formatRatio(summary.sharpe_like));
  setMetric("backtest-win-rate", formatPercent(summary.win_rate, 1));
  setMetric("backtest-return", formatPercent(summary.return_pct, 1, true), edgeClass(summary.return_pct));
  setMetric("backtest-max-dd", `${MINUS}${formatPercent(summary.max_drawdown, 1)}`, summary.max_drawdown > 0 ? "negative" : "");
  setMetric("backtest-profit-factor", formatRatio(summary.profit_factor));
  setMetric("backtest-avg-edge", formatMetricEdge(summary.average_edge), edgeClass(summary.average_edge));
  setText("backtest-equity-label", "EQUITY CURVE " + MID + " GENERATED BACKTEST");
  setText("backtest-trade-count", `${Number(summary.total_trades || 0).toLocaleString()} TRADES`);

  const points = pointsFromEquityCurve(summary.equity_curve);
  if (points) {
    $("backtest-equity-line").setAttribute("points", points);
    $("backtest-equity-area").setAttribute("points", `${points} 400,56 0,56`);
  }
  renderBacktestDiagnostics(summary);
}

function pointsFromEquityCurve(equityCurve) {
  if (!Array.isArray(equityCurve) || equityCurve.length === 0) return null;
  const equities = equityCurve.map((point) => Number(point.equity)).filter(Number.isFinite);
  if (!equities.length) return null;
  const minEquity = Math.min(...equities);
  const maxEquity = Math.max(...equities);
  const span = Math.max(maxEquity - minEquity, 1);
  const lastIndex = Math.max(equityCurve.length - 1, 1);

  return equityCurve.map((point, index) => {
    const x = index / lastIndex * 400;
    const y = 52 - ((Number(point.equity) - minEquity) / span * 48);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function renderBacktestDiagnostics(summary) {
  const trades = Array.isArray(summary.trades) ? summary.trades : [];
  if (!trades.length) {
    setHtml("backtest-diagnostics", `<div class="diagnostic-row"><span>No trade drilldown</span><b>EMPTY</b></div>`);
    return;
  }

  const best = [...trades].sort((a, b) => Number(b.net_pnl || 0) - Number(a.net_pnl || 0))[0];
  const worst = [...trades].sort((a, b) => Number(a.net_pnl || 0) - Number(b.net_pnl || 0))[0];
  const feeDrag = trades.reduce((sum, trade) => sum + Number(trade.fees || 0), 0);
  const drawdown = [...(summary.equity_curve || [])].sort((a, b) => Number(b.drawdown_pct || 0) - Number(a.drawdown_pct || 0))[0];
  const byTicker = trades.reduce((acc, trade) => {
    const key = trade.ticker || "UNKNOWN";
    acc[key] = (acc[key] || 0) + Number(trade.net_pnl || 0);
    return acc;
  }, {});
  const topTicker = Object.entries(byTicker).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))[0];

  setHtml("backtest-diagnostics", [
    diagnostic("BEST TRADE", best?.ticker, usd(best?.net_pnl || 0), "positive"),
    diagnostic("WORST TRADE", worst?.ticker, usd(worst?.net_pnl || 0), "negative"),
    diagnostic("FEE DRAG", `${trades.length} trades`, usd(feeDrag), "negative"),
    diagnostic("MAX DRAWDOWN", drawdown ? formatTimestamp(drawdown.timestamp) : "N/A", formatPercent(drawdown?.drawdown_pct || 0)),
    diagnostic("LARGEST TICKER", topTicker?.[0] || "N/A", usd(topTicker?.[1] || 0), Number(topTicker?.[1]) >= 0 ? "positive" : "negative"),
  ].join(""));
}

function diagnostic(label, detail, value, className = "") {
  return `<div class="diagnostic-row"><span>${escapeHtml(label)} · ${escapeHtml(detail || "N/A")}</span><b class="${className}">${escapeHtml(value)}</b></div>`;
}

function normalizeDashboardMarket(market, index) {
  const last = Math.round(Number(market.last ?? market.last_price ?? market.yes_ask ?? 0));
  const bid = Math.round(Number(market.bid ?? market.yes_bid ?? Math.max(last - 1, 1)));
  const ask = Math.round(Number(market.ask ?? market.yes_ask ?? Math.min(last + 1, 99)));
  const rawModel = market.model ?? (market.model_probability != null ? market.model_probability : last);
  const model = normalizeProbabilityPercent(rawModel, last);
  const city = market.city || cityFromTicker(market.ticker);
  const volumeNumber = Number(market.volume ?? market.volume_24h ?? 0);
  return withEdge({
    id: market.id || market.ticker || `generated-${index}`,
    source: "generated",
    city,
    eventType: String(market.event_type || market.weather_event_type || inferEventType(market.ticker || market.title || "")).toLowerCase(),
    ticker: market.ticker || `GENERATED-${index}`,
    title: market.title || `${city} ${MID} Generated Market`,
    bracket: market.bracket || "YES",
    last,
    bid,
    ask,
    model,
    vol: formatVolume(volumeNumber),
    volumeNumber,
    ch: Number(market.change_24h ?? 0),
    conf: normalizeProbabilityPercent(market.confidence ?? market.conf, 0),
    dist: market.dist || "generated",
    timestamp: market.timestamp || market.updated_at || null,
  });
}

function normalizeDashboardPosition(position) {
  const side = String(position.side || "yes").toUpperCase();
  const quantity = Number(position.quantity || 0);
  const average = Number(position.average_price ?? position.entry_price ?? 0);
  const mark = Number(position.mark_price ?? position.exit_price ?? average);
  const pnlValue = Number(position.realized_pnl ?? position.unrealized_pnl ?? 0);
  const pct = average > 0 && quantity > 0 ? pnlValue / (average * quantity / 100) : 0;
  return [
    position.title || position.ticker,
    side,
    quantity,
    cents(average),
    cents(mark),
    usd(pnlValue),
    formatPercent(pct, 1, true),
    pnlValue >= 0,
  ];
}

function normalizeOpportunity(item, index) {
  const ticker = item.ticker || item.market_ticker || item.id || `opportunity-${index}`;
  const market = markets.find((candidate) => candidate.ticker === ticker || candidate.id === ticker);
  const edge = Number(item.edge_cents ?? item.edge ?? item.fee_adjusted_edge ?? market?.edge ?? 0);
  return {
    marketId: market?.id || ticker,
    ticker,
    title: item.title || `${String(item.action || signalFor(edge)).toUpperCase()} ${ticker}`,
    edge: Math.abs(edge) <= 1 ? edge * 100 : edge,
    score: Number(item.score ?? edge),
    reasons: Array.isArray(item.reason_codes) ? item.reason_codes : Array.isArray(item.reasons) ? item.reasons : ["PAYLOAD"],
  };
}

function inferEventType(text) {
  const upper = String(text).toUpperCase();
  if (upper.includes("RAIN")) return "rain";
  if (upper.includes("HEAT")) return "heat";
  if (upper.includes("WIND")) return "wind";
  return "temperature";
}

function cityFromTicker(ticker = "") {
  const upper = ticker.toUpperCase();
  return Object.keys(cityColors).find((city) => upper.includes(city)) || "MKT";
}

function applyAccount(account = {}) {
  if (Number.isFinite(account.bankroll)) setText("account-equity", usd(account.bankroll));
  if (Number.isFinite(account.mtd_pnl)) {
    setText("account-pnl", `${account.mtd_pnl >= 0 ? "+" : ""}${usd(account.mtd_pnl)}`);
    $("account-pnl").className = account.mtd_pnl >= 0 ? "positive" : "negative";
  } else if (state.dataMode === "generated") {
    setText("account-pnl", "N/A");
    $("account-pnl").className = "";
  }
  if (Number.isFinite(account.available_cash)) setText("account-buying-power", usd(account.available_cash));
}

function applyDashboardPayload(payload) {
  state.dataMode = "generated";
  state.generatedAt = payload.generated_at || null;
  state.risk = payload.risk || null;
  state.paper = payload.paper || null;
  state.venue = payload.venue || payload.venue_health || null;
  state.weather = payload.weather || payload.weather_feed || null;
  state.fills = normalizeFills(payload);
  state.opportunities = Array.isArray(payload.opportunities) ? payload.opportunities.map(normalizeOpportunity) : [];

  if (Array.isArray(payload.markets) && payload.markets.length) {
    markets = payload.markets.map(normalizeDashboardMarket);
    state.selectedId = markets[0].id;
    state.limit = markets[0].ask;
    state.freshestMarketAt = freshestTimestamp(markets.map((market) => market.timestamp));
  }

  const generatedPositions = [];
  if (Array.isArray(payload.positions)) generatedPositions.push(...payload.positions);
  if (payload.paper && Array.isArray(payload.paper.open_positions)) generatedPositions.push(...payload.paper.open_positions);
  if (generatedPositions.length) positions = generatedPositions.map(normalizeDashboardPosition);

  if (payload.account) applyAccount(payload.account);
  if (payload.backtest) {
    state.artifacts.backtest = { status: "loaded", text: "Backtest embedded in dashboard payload" };
    renderBacktestSummary(payload.backtest);
  }
}

function normalizeFills(payload) {
  const candidates = payload.fills || payload.executions || payload.recent_fills || payload.paper?.fills || payload.paper?.events || payload.paper?.recent_events || [];
  return Array.isArray(candidates) ? candidates : [];
}

function freshestTimestamp(values) {
  const dates = values.map((value) => new Date(value)).filter((date) => !Number.isNaN(date.getTime()));
  if (!dates.length) return null;
  return new Date(Math.max(...dates.map((date) => date.getTime()))).toISOString();
}

function bindControls() {
  $("market-filters").addEventListener("submit", (event) => event.preventDefault());
  $("buy-button").addEventListener("click", () => { state.side = "BUY"; state.limit = selectedMarket()?.ask ?? state.limit; renderTicket(); });
  $("sell-button").addEventListener("click", () => { state.side = "SELL"; state.limit = Math.max(1, 100 - (selectedMarket()?.bid ?? 1)); renderTicket(); });
  $("qty-down").addEventListener("click", () => { state.qty = Math.max(20, state.qty - 20); renderTicket(); });
  $("qty-up").addEventListener("click", () => { state.qty += 20; renderTicket(); });
  $("limit-down").addEventListener("click", () => { state.limit = Math.max(1, state.limit - 1); renderTicket(); });
  $("limit-up").addEventListener("click", () => { state.limit = Math.min(99, state.limit + 1); renderTicket(); });
  $("ticket-submit").addEventListener("click", () => {
    $("ticket-submit").textContent = "DRY RUN RECORDED";
    window.setTimeout(renderTicket, 900);
  });

  $("filter-city").addEventListener("change", (event) => { state.filters.city = event.target.value; ensureSelectedVisible(); render(); });
  $("filter-signal").addEventListener("change", (event) => { state.filters.signal = event.target.value; ensureSelectedVisible(); render(); });
  $("filter-event").addEventListener("change", (event) => { state.filters.eventType = event.target.value; ensureSelectedVisible(); render(); });
  $("filter-edge").addEventListener("input", (event) => { state.filters.minEdge = event.target.value; ensureSelectedVisible(); render(); });
  $("filter-confidence").addEventListener("input", (event) => { state.filters.minConfidence = event.target.value; ensureSelectedVisible(); render(); });
  $("reset-filters").addEventListener("click", () => {
    state.filters = { city: "", signal: "", eventType: "", minEdge: "", minConfidence: "" };
    ensureSelectedVisible();
    render();
  });
}

function ensureSelectedVisible() {
  const visible = filteredMarkets();
  if (visible.length && !visible.some((market) => market.id === state.selectedId)) {
    state.selectedId = visible[0].id;
    state.limit = visible[0].ask;
  }
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) return { ok: false, missing: true };
  return { ok: true, payload: await response.json() };
}

async function loadDashboardPayload() {
  try {
    const result = await loadJson("./data/dashboard.json");
    if (!result.ok) {
      state.artifacts.dashboard = { status: "missing", text: "No dashboard payload; sample data active" };
      return;
    }
    state.artifacts.dashboard = { status: "loaded", text: "Generated dashboard payload loaded" };
    applyDashboardPayload(result.payload);
  } catch (error) {
    state.artifacts.dashboard = { status: "error", text: "Dashboard payload error" };
    console.warn("Failed to load dashboard payload", error);
  } finally {
    render();
  }
}

async function loadBacktestSummary() {
  try {
    const result = await loadJson("./data/backtest-summary.json");
    if (!result.ok) {
      if (state.backtest) return;
      state.artifacts.backtest = { status: "missing", text: "No backtest artifact; sample metrics active" };
      return;
    }
    state.artifacts.backtest = { status: "loaded", text: "Generated backtest artifact loaded" };
    renderBacktestSummary(result.payload);
  } catch (error) {
    state.artifacts.backtest = { status: "error", text: "Backtest artifact error" };
    console.warn("Failed to load backtest artifact", error);
  } finally {
    render();
  }
}

function render() {
  renderArtifactStates();
  renderFilters();
  renderMarkets();
  renderDetail();
  renderDistribution();
  renderOrderbook();
  renderTicket();
  renderPositions();
  renderRisk();
  renderOpportunityQueue();
  renderWeather();
  renderVenue();
  renderFills();
}

bindControls();
renderClock();
render();
loadDashboardPayload();
loadBacktestSummary();
window.setInterval(renderClock, 1000);
