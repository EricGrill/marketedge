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
const formatPercent = (value, digits = 1, signed = false) => {
  if (!Number.isFinite(value)) return "N/A";
  const sign = signed && value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(digits)}%`;
};
const formatRatio = (value) => Number.isFinite(value) ? value.toFixed(2) : "N/A";
const formatMetricEdge = (value) => {
  if (!Number.isFinite(value)) return "N/A";
  const centsValue = value * 100;
  return `${centsValue > 0 ? "+" : ""}${centsValue.toFixed(1)}${CENT}`;
};

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
  { id: "NYC-88", city: "NYC", ticker: "HIGHNY-26JUN18-B88.5", title: `NYC ${MID} Daily High`, bracket: range(88, 89), last: 24, bid: 23, ask: 25, model: 33, vol: "142K", ch: 2, conf: 82, dist: "nyc" },
  { id: "NYC-90", city: "NYC", ticker: "HIGHNY-26JUN18-B90.5", title: `NYC ${MID} Daily High`, bracket: range(90, 91), last: 31, bid: 30, ask: 32, model: 28, vol: "118K", ch: -1, conf: 64, dist: "nyc" },
  { id: "NYC-86", city: "NYC", ticker: "HIGHNY-26JUN18-B86.5", title: `NYC ${MID} Daily High`, bracket: range(86, 87), last: 16, bid: 15, ask: 17, model: 18, vol: "74K", ch: 1, conf: 55, dist: "nyc" },
  { id: "CHI-84", city: "CHI", ticker: "HIGHCHI-26JUN18-B84.5", title: `Chicago ${MID} Daily High`, bracket: range(84, 85), last: 38, bid: 37, ask: 39, model: 41, vol: "96K", ch: 1, conf: 61, dist: "chi" },
  { id: "MIA-RN", city: "MIA", ticker: "RAINMIA-26JUN18-YES", title: `Miami ${MID} Rain Today`, bracket: "YES", last: 71, bid: 70, ask: 72, model: 78, vol: "63K", ch: 3, conf: 77, dist: "miaRain" },
  { id: "LAX-75", city: "LAX", ticker: "HIGHLA-26JUN18-B75.5", title: `Los Angeles ${MID} Daily High`, bracket: range(75, 76), last: 52, bid: 51, ask: 53, model: 49, vol: "58K", ch: -2, conf: 58, dist: "lax" },
  { id: "DEN-71", city: "DEN", ticker: "HIGHDEN-26JUN18-B71.5", title: `Denver ${MID} Daily High`, bracket: range(71, 72), last: 29, bid: 28, ask: 30, model: 36, vol: "47K", ch: -1, conf: 69, dist: "den" },
  { id: "AUS-100", city: "AUS", ticker: "HEATAUS-26JUN18-YES", title: `Austin ${MID} High ${GE} 100${DEG}F`, bracket: "YES", last: 64, bid: 63, ask: 65, model: 60, vol: "81K", ch: -2, conf: 60, dist: "ausHeat" },
  { id: "BOS-79", city: "BOS", ticker: "HIGHBOS-26JUN18-B79.5", title: `Boston ${MID} Daily High`, bracket: range(79, 80), last: 44, bid: 43, ask: 45, model: 52, vol: "39K", ch: 2, conf: 74, dist: "bos" },
].map((market) => ({ ...market, edge: market.model - market.last }));

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
};

const $ = (id) => document.getElementById(id);
const cents = (value) => `${value}${CENT}`;
const edgeText = (value) => `${value > 0 ? "+" : ""}${value}${CENT}`;
const edgeClass = (value) => value > 0 ? "positive" : value < 0 ? "negative" : "";
const signalFor = (edge) => edge >= 5 ? "BUY" : edge <= -4 ? "SELL" : "HOLD";
const signalClass = (signal) => `signal-badge signal-${signal.toLowerCase()}`;
const usd = (value) => `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function selectedMarket() {
  return markets.find((market) => market.id === state.selectedId) ?? markets[0];
}

function setText(id, value) {
  $(id).textContent = value;
}

function setMetric(id, value, className = "") {
  const el = $(id);
  el.textContent = value;
  el.className = className;
}

function colorCity(el, city) {
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
  const p = (number) => String(number).padStart(2, "0");
  setText("clock", `${p(now.getHours())}:${p(now.getMinutes())}:${p(now.getSeconds())}`);
}

function renderMarkets() {
  $("open-count").textContent = `${markets.length} OPEN`;
  $("market-list").replaceChildren(...markets.map((market) => {
    const signal = signalFor(market.edge);
    const row = document.createElement("button");
    row.type = "button";
    row.className = `market-row${market.id === state.selectedId ? " active" : ""}`;
    row.innerHTML = `
      <div>
        <span class="city-badge" style="color:${cityColors[market.city]}">${market.city}</span>
        <strong>${market.bracket}</strong>
        <span class="${signalClass(signal)}">${signal}</span>
      </div>
      <div class="meta">
        <span class="label">LAST</span>
        <strong>${cents(market.last)}</strong>
        <span class="label">EDGE</span>
        <strong class="${edgeClass(market.edge)}">${edgeText(market.edge)}</strong>
        <span class="volume">${market.vol}</span>
      </div>
    `;
    row.addEventListener("click", () => {
      state.selectedId = market.id;
      state.limit = market.ask;
      render();
    });
    return row;
  }));
}

function renderDetail() {
  const market = selectedMarket();
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
  $("confidence-bar").style.width = `${market.conf}%`;
}

function renderDistribution() {
  const market = selectedMarket();
  const rows = distributions[market.dist] ?? [[market.bracket, market.model, market.last]];
  const maxValue = Math.max(...rows.map((row) => Math.max(row[1], row[2])));
  $("distribution-list").replaceChildren(...rows.map(([label, model, marketValue]) => {
    const active = label === market.bracket;
    const row = document.createElement("div");
    row.className = `dist-row${active ? " active" : ""}`;
    row.innerHTML = `
      <span>${label}</span>
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
}

function renderPositions() {
  $("positions-list").replaceChildren(...positions.map((position) => {
    const [contract, side, qty, avg, mark, pnl, pct, profitable] = position;
    const row = document.createElement("div");
    row.className = "position-row";
    row.innerHTML = `
      <span>${contract} <b class="${side === "NO" ? "negative" : "positive"}">${side}</b></span>
      <span>${qty}</span>
      <span>${avg}</span>
      <span>${mark}</span>
      <span class="${profitable ? "positive" : "negative"}">${pnl}<br><b>${pct}</b></span>
    `;
    return row;
  }));
}

function normalizeDashboardMarket(market, index) {
  const last = Math.round(Number(market.last ?? market.last_price ?? market.yes_ask ?? 0));
  const bid = Math.round(Number(market.bid ?? market.yes_bid ?? Math.max(last - 1, 1)));
  const ask = Math.round(Number(market.ask ?? market.yes_ask ?? Math.min(last + 1, 99)));
  const rawModel = market.model ?? (market.model_probability != null ? market.model_probability * 100 : last);
  const model = Math.round(Number(rawModel));
  const city = market.city || cityFromTicker(market.ticker);
  return {
    id: market.id || market.ticker || `generated-${index}`,
    city,
    ticker: market.ticker || `GENERATED-${index}`,
    title: market.title || `${city} ${MID} Generated Market`,
    bracket: market.bracket || "YES",
    last,
    bid,
    ask,
    model,
    vol: formatVolume(market.volume ?? market.volume_24h ?? 0),
    ch: Number(market.change_24h ?? 0),
    conf: Math.round(Number(market.confidence ?? market.conf ?? 0) * (Number(market.confidence ?? market.conf ?? 0) <= 1 ? 100 : 1)),
    dist: market.dist || "generated",
  };
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
    cents(average.toFixed(0)),
    cents(mark.toFixed(0)),
    usd(pnlValue),
    formatPercent(pct, 1, true),
    pnlValue >= 0,
  ];
}

function cityFromTicker(ticker = "") {
  const upper = ticker.toUpperCase();
  return Object.keys(cityColors).find((city) => upper.includes(city)) || "MKT";
}

function formatVolume(value) {
  const number = Number(value || 0);
  if (number >= 1000) return `${Math.round(number / 1000)}K`;
  return number ? String(number) : "N/A";
}

function applyAccount(account = {}) {
  const values = document.querySelectorAll(".account-strip strong");
  if (values[0] && Number.isFinite(account.bankroll)) values[0].textContent = usd(account.bankroll);
  if (values[1] && Number.isFinite(account.mtd_pnl)) {
    values[1].textContent = `${account.mtd_pnl >= 0 ? "+" : ""}${usd(account.mtd_pnl)}`;
    values[1].className = account.mtd_pnl >= 0 ? "positive" : "negative";
  }
  if (values[2] && Number.isFinite(account.available_cash)) values[2].textContent = usd(account.available_cash);
}

function applyDashboardPayload(payload) {
  if (Array.isArray(payload.markets) && payload.markets.length) {
    markets = payload.markets.map(normalizeDashboardMarket).map((market) => ({
      ...market,
      edge: market.model - market.last,
    }));
    state.selectedId = markets[0].id;
    state.limit = markets[0].ask;
  }

  const generatedPositions = [];
  if (Array.isArray(payload.positions)) generatedPositions.push(...payload.positions);
  if (payload.paper && Array.isArray(payload.paper.open_positions)) {
    generatedPositions.push(...payload.paper.open_positions);
  }
  if (generatedPositions.length) {
    positions = generatedPositions.map(normalizeDashboardPosition);
  }

  if (payload.account) applyAccount(payload.account);
  if (payload.backtest) renderBacktestSummary(payload.backtest);
  render();
}

function bindControls() {
  $("buy-button").addEventListener("click", () => { state.side = "BUY"; renderTicket(); });
  $("sell-button").addEventListener("click", () => { state.side = "SELL"; renderTicket(); });
  $("qty-down").addEventListener("click", () => { state.qty = Math.max(20, state.qty - 20); renderTicket(); });
  $("qty-up").addEventListener("click", () => { state.qty += 20; renderTicket(); });
  $("limit-down").addEventListener("click", () => { state.limit = Math.max(1, state.limit - 1); renderTicket(); });
  $("limit-up").addEventListener("click", () => { state.limit = Math.min(99, state.limit + 1); renderTicket(); });
  $("ticket-submit").addEventListener("click", () => {
    $("ticket-submit").textContent = "DRY RUN RECORDED";
    window.setTimeout(renderTicket, 900);
  });
}

function pointsFromEquityCurve(equityCurve) {
  if (!Array.isArray(equityCurve) || equityCurve.length === 0) {
    return null;
  }

  const equities = equityCurve.map((point) => point.equity);
  const minEquity = Math.min(...equities);
  const maxEquity = Math.max(...equities);
  const span = Math.max(maxEquity - minEquity, 1);
  const lastIndex = Math.max(equityCurve.length - 1, 1);

  return equityCurve.map((point, index) => {
    const x = index / lastIndex * 400;
    const y = 52 - ((point.equity - minEquity) / span * 48);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function renderBacktestSummary(summary) {
  setText("backtest-strategy-label", "ENGINE OUTPUT");
  setMetric("backtest-sharpe", formatRatio(summary.sharpe_like));
  setMetric("backtest-win-rate", formatPercent(summary.win_rate, 1));
  setMetric("backtest-return", formatPercent(summary.return_pct, 1, true), edgeClass(summary.return_pct));
  setMetric("backtest-max-dd", `${MINUS}${formatPercent(summary.max_drawdown, 1)}`, summary.max_drawdown > 0 ? "negative" : "");
  setMetric("backtest-profit-factor", formatRatio(summary.profit_factor));
  setMetric("backtest-avg-edge", formatMetricEdge(summary.average_edge), edgeClass(summary.average_edge));
  setText("backtest-equity-label", "EQUITY CURVE " + MID + " GENERATED BACKTEST");
  setText("backtest-trade-count", `${summary.total_trades.toLocaleString()} TRADES`);

  const points = pointsFromEquityCurve(summary.equity_curve);
  if (points) {
    $("backtest-equity-line").setAttribute("points", points);
    $("backtest-equity-area").setAttribute("points", `${points} 400,56 0,56`);
  }
}

async function loadBacktestSummary() {
  try {
    const response = await fetch("./data/backtest-summary.json", { cache: "no-store" });
    if (!response.ok) return;
    renderBacktestSummary(await response.json());
  } catch {
    // Keep the static placeholder metrics when no generated summary exists.
  }
}

async function loadDashboardPayload() {
  try {
    const response = await fetch("./data/dashboard.json", { cache: "no-store" });
    if (!response.ok) return;
    applyDashboardPayload(await response.json());
  } catch {
    // Keep the static sample dashboard when no generated payload exists.
  }
}

function render() {
  renderMarkets();
  renderDetail();
  renderDistribution();
  renderOrderbook();
  renderTicket();
  renderPositions();
}

bindControls();
renderClock();
render();
loadDashboardPayload();
loadBacktestSummary();
window.setInterval(renderClock, 1000);
