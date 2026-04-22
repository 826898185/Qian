import "./styles.css";
import * as echarts from "echarts";

document.querySelector("#app").innerHTML = `
  <div class="container">
    <div class="header">
      <div class="title">K线 1+3 模型可视化看板（MVP）</div>
      <div class="controls">
        <select id="symbolSelect"></select>
        <button id="reloadBtn">刷新</button>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <h3>今日动量信号榜</h3>
        <p class="muted">按 score 从高到低排序</p>
        <div id="signalList"></div>
      </div>

      <div class="card">
        <div class="risk-row">
          <span id="riskBadge" class="risk-tag">N/A</span>
          <span id="riskMessage" class="muted">暂无风险信息</span>
        </div>
        <p id="summary" class="summary">加载中...</p>
        <div id="chart" class="chart-box"></div>
      </div>
    </div>

    <div class="card table-card">
      <h3>历史 1+3 结构记录</h3>
      <table>
        <thead>
          <tr>
            <th>核心1日期</th>
            <th>3确认日期</th>
            <th>确认时长</th>
            <th>得分</th>
            <th>核心1收盘</th>
            <th>3收盘</th>
          </tr>
        </thead>
        <tbody id="patternTableBody"></tbody>
      </table>
    </div>
  </div>
`;

const state = {
  symbols: [],
  symbol: "",
  signals: [],
  candles: [],
  patterns: [],
  risk: null,
  chart: null,
};

const dom = {
  symbolSelect: document.getElementById("symbolSelect"),
  reloadBtn: document.getElementById("reloadBtn"),
  signalList: document.getElementById("signalList"),
  riskBadge: document.getElementById("riskBadge"),
  riskMessage: document.getElementById("riskMessage"),
  summary: document.getElementById("summary"),
  chart: document.getElementById("chart"),
  patternTableBody: document.getElementById("patternTableBody"),
};

function riskClass(level) {
  if (level === "HOLD") return "risk-HOLD";
  if (level === "WARN") return "risk-WARN";
  if (level === "REDUCE") return "risk-REDUCE";
  return "risk-SELL";
}

function fmt2(v) {
  return Number(v).toFixed(2);
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`请求失败 ${res.status}: ${text}`);
  }
  return await res.json();
}

function renderSymbols() {
  dom.symbolSelect.innerHTML = state.symbols
    .map((s) => `<option value="${s}" ${s === state.symbol ? "selected" : ""}>${s}</option>`)
    .join("");
}

function renderSignalList() {
  if (!state.signals.length) {
    dom.signalList.innerHTML = `<p class="muted">暂无触发信号</p>`;
    return;
  }

  dom.signalList.innerHTML = state.signals
    .map(
      (row) => `
      <div class="signal-item">
        <h4>${row.symbol}</h4>
        <div class="muted">核心1: ${row.core1_date} / 3确认: ${row.three_date}</div>
        <div class="muted">score: ${fmt2(row.score)} | 时长: ${row.days_from_low}天</div>
        <div class="risk-tag ${riskClass(row.risk_level)}">${row.risk_level}</div>
      </div>
    `
    )
    .join("");
}

function renderPatternTable() {
  const rows = [...state.patterns].reverse();
  if (!rows.length) {
    dom.patternTableBody.innerHTML = `<tr><td colspan="6" class="muted">暂无记录</td></tr>`;
    return;
  }
  dom.patternTableBody.innerHTML = rows
    .map(
      (p) => `
      <tr>
        <td>${p.core1_date}</td>
        <td>${p.three_date}</td>
        <td>${p.days_from_low}</td>
        <td>${fmt2(p.score)}</td>
        <td>${fmt2(p.core1_close)}</td>
        <td>${fmt2(p.three_close)}</td>
      </tr>`
    )
    .join("");
}

function markerSeries(points) {
  return points.map((x) => ({
    coord: [x.idx, x.price],
    value: x.label,
    itemStyle: { color: x.color },
    label: {
      show: true,
      formatter: x.label,
      color: x.color,
      fontWeight: "bold",
      backgroundColor: "#fff",
      borderRadius: 4,
      padding: [2, 4],
    },
  }));
}

function buildSupportLines(p) {
  return [
    { name: "3开盘支撑", yAxis: p.three_open, lineStyle: { color: "#ff8f00", type: "dashed" } },
    { name: "3收盘支撑", yAxis: p.three_close, lineStyle: { color: "#f4511e", type: "dashed" } },
    { name: "1开盘支撑", yAxis: p.core1_open, lineStyle: { color: "#5e35b1", type: "dotted" } },
    { name: "1收盘支撑", yAxis: p.core1_close, lineStyle: { color: "#3949ab", type: "dotted" } },
    { name: "1最低点", yAxis: p.core1_low, lineStyle: { color: "#1e88e5", type: "solid" } },
  ];
}

function renderChart() {
  const xData = state.candles.map((r) => r.date);
  const kData = state.candles.map((r) => [r.open, r.close, r.low, r.high]);

  const latestPattern = state.patterns.length ? state.patterns[state.patterns.length - 1] : null;
  const markerPoints = [];
  if (latestPattern) {
    markerPoints.push(
      { idx: latestPattern.core1_idx, price: latestPattern.core1_close, label: "核心1", color: "#2962ff" },
      { idx: latestPattern.one_idx, price: state.candles[latestPattern.one_idx]?.close, label: "1", color: "#00c853" },
      { idx: latestPattern.two_idx, price: state.candles[latestPattern.two_idx]?.close, label: "2", color: "#00c853" },
      { idx: latestPattern.three_idx, price: latestPattern.three_close, label: "3", color: "#d50000" }
    );
  }

  if (!state.chart) {
    state.chart = echarts.init(dom.chart);
    window.addEventListener("resize", () => state.chart && state.chart.resize());
  }

  const option = {
    animation: false,
    title: { text: `${state.symbol} K线与1+3标注`, left: "center" },
    tooltip: { trigger: "axis" },
    grid: { left: 60, right: 24, top: 60, bottom: 70 },
    xAxis: { type: "category", data: xData, scale: true, boundaryGap: false },
    yAxis: { scale: true },
    dataZoom: [{ type: "inside" }, { type: "slider" }],
    series: [
      {
        name: "K线",
        type: "candlestick",
        data: kData,
        itemStyle: {
          color: "#ef5350",
          color0: "#26a69a",
          borderColor: "#ef5350",
          borderColor0: "#26a69a",
        },
        markPoint: {
          symbolSize: 62,
          data: markerSeries(markerPoints.filter((m) => Number.isFinite(m.price))),
        },
        markLine: latestPattern
          ? {
              symbol: ["none", "none"],
              label: { formatter: "{b}: {c}" },
              data: buildSupportLines(latestPattern),
            }
          : undefined,
      },
    ],
  };
  state.chart.setOption(option, true);
}

function renderSummary() {
  const latest = state.patterns.length ? state.patterns[state.patterns.length - 1] : null;
  if (!latest) {
    dom.summary.textContent = "当前无确认的 1+3 结构。";
    return;
  }
  dom.summary.textContent = `最新结构：核心1 ${latest.core1_date}，3确认 ${latest.three_date}，确认时长 ${latest.days_from_low} 天，动量分 ${fmt2(latest.score)}。`;
}

function renderRisk() {
  if (!state.risk) {
    dom.riskBadge.className = "risk-tag";
    dom.riskBadge.textContent = "N/A";
    dom.riskMessage.textContent = "暂无风险信息";
    return;
  }
  dom.riskBadge.className = `risk-tag ${riskClass(state.risk.level)}`;
  dom.riskBadge.textContent = state.risk.level;
  dom.riskMessage.textContent = state.risk.message;
}

async function loadSignals() {
  const res = await fetchJson("/api/signals");
  state.signals = res.signals || [];
  renderSignalList();
}

async function loadSymbol(symbol) {
  state.symbol = symbol.trim().toUpperCase();
  renderSymbols();

  const [patternRes, riskRes] = await Promise.all([
    fetchJson(`/api/stocks/${state.symbol}/patterns?lookback=220`),
    fetchJson(`/api/stocks/${state.symbol}/risk?lookback=220`),
  ]);

  state.candles = patternRes.candles || [];
  state.patterns = patternRes.patterns || [];
  state.risk = riskRes.risk || null;

  renderRisk();
  renderSummary();
  renderPatternTable();
  renderChart();
}

async function init() {
  const res = await fetchJson("/api/symbols");
  state.symbols = res.symbols || [];
  state.symbol = state.symbols[0] || "";
  renderSymbols();
  await Promise.all([loadSignals(), loadSymbol(state.symbol)]);
}

dom.reloadBtn.addEventListener("click", async () => {
  try {
    await Promise.all([loadSignals(), loadSymbol(dom.symbolSelect.value)]);
  } catch (err) {
    alert(err.message);
  }
});

dom.symbolSelect.addEventListener("change", async () => {
  try {
    await loadSymbol(dom.symbolSelect.value);
  } catch (err) {
    alert(err.message);
  }
});

init().catch((err) => {
  dom.summary.textContent = `加载失败：${err.message}`;
});
