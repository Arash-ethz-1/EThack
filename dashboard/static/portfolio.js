/* Fund tab - dashboard/static/portfolio.js (loaded after app.js, uses its helpers).
   Only displays. Weights, fund-vs-benchmark numbers, climate numbers and risk all come
   from POST /api/portfolio (portfolio/allocate.py + portfolio/risk.py). Changing a control
   re-runs the allocation on the server for this view only - nothing is saved. */

const PF = { data: null, settings: {}, q: "", limit: 25, busy: false, error: null };
const pct = (v, d = 1) => v == null ? "–" : (v * 100).toFixed(d) + "%";
const pp = v => v == null ? "–" : (v >= 0 ? "+" : "−") + Math.abs(v * 100).toFixed(2) + " pp";
const FOSSIL = ["Integrated Oil & Gas", "Oil & Gas Equipment & Services", "Oil & Gas Exploration & Production",
  "Oil & Gas Refining & Marketing", "Oil & Gas Storage & Transportation", "Tobacco"];
const svg = (w, h, g, label) => `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="${label}">${g}</svg>`;
const usd = v => v == null ? "–" : Math.abs(v) >= 1e9 ? `$${(v / 1e9).toFixed(2)}bn` : Math.abs(v) >= 1e6 ? `$${(v / 1e6).toFixed(Math.abs(v) < 1e7 ? 2 : 1)}m` : Math.abs(v) >= 1e3 ? `$${Math.round(v / 1e3)}k` : `$${Math.round(v)}`;

async function loadPortfolio(previous) {
  PF.busy = true;
  $("#view-portfolio").classList.add("busy");
  const res = await postJSON("/api/portfolio", body({ settings: PF.settings }));
  PF.busy = false;
  if (res.error) { PF.settings = previous || {}; PF.error = res.error; } else { PF.data = res; PF.error = null; }
  if (!PF.data) { $("#view-portfolio").innerHTML = `<p class="muted">${esc(PF.error)}</p>`; return; }
  renderPortfolio();
}

function seg(name, options, current) {
  return `<div class="seg" role="group" aria-label="${esc(name)}">${options.map(([v, l]) =>
    `<button type="button" data-set="${esc(name)}" data-v='${JSON.stringify(v)}' aria-pressed="${JSON.stringify(v) === JSON.stringify(current)}">${l}</button>`).join("")}</div>`;
}

function kpi(label, fund, bench, note, good) {
  return `<div class="kpi"><span class="label">${label}</span><span class="v num">${fund}</span>
    <span class="vs">index ${bench}</span>${note ? `<span class="delta ${good ? "good" : ""}">${note}</span>` : ""}</div>`;
}

function barsScores(scores) {
  const rows = [["total_score", "Total"], ...CATS.map(([id, n]) => [`${id}_score`, n])];
  const W = 560, L = 110, R = 50, rowH = 44, H = rows.length * rowH + 24, x = v => L + (W - L - R) * v / 100;
  let g = "";
  [0, 25, 50, 75, 100].forEach(v => g += `<line class="grid" x1="${x(v)}" x2="${x(v)}" y1="0" y2="${H - 20}"/><text x="${x(v)}" y="${H - 6}" text-anchor="middle">${v}</text>`);
  rows.forEach(([k, n], i) => {
    const s = scores[k] || {}, y = i * rowH + 6;
    g += `<text class="strong" x="${L - 12}" y="${y + 17}" text-anchor="end">${n}</text>`;
    if (isNum(s.benchmark)) g += `<rect class="b-bench" x="${L}" y="${y + 21}" width="${x(s.benchmark) - L}" height="6"><title>Index ${s.benchmark.toFixed(1)}</title></rect>`;
    if (isNum(s.portfolio)) g += `<rect class="b-fund" x="${L}" y="${y + 9}" width="${x(s.portfolio) - L}" height="10"><title>Fund ${s.portfolio.toFixed(1)}</title></rect>
      <text class="strong" x="${x(s.portfolio) + 6}" y="${y + 18}">${s.portfolio.toFixed(1)}</text>`;
  });
  return svg(W, H, g, "Weighted scores, fund vs index");
}

function barsSectors(sectors) {
  const max = Math.max(...sectors.map(s => Math.max(s.portfolio, s.benchmark)), 0.01);
  const W = 560, L = 170, R = 60, rowH = 28, H = sectors.length * rowH + 6, x = v => L + (W - L - R) * v / max;
  let g = "";
  sectors.forEach((s, i) => {
    const y = i * rowH + 4;
    g += `<text class="strong" x="${L - 12}" y="${y + 13}" text-anchor="end">${esc(s.sector)}</text>
      <rect class="b-bench" x="${L}" y="${y + 13}" width="${Math.max(0, x(s.benchmark) - L)}" height="4"><title>Index ${pct(s.benchmark)}</title></rect>
      <rect class="b-fund" x="${L}" y="${y + 4}" width="${Math.max(0, x(s.portfolio) - L)}" height="8"><title>Fund ${pct(s.portfolio)}</title></rect>
      <text x="${Math.max(x(s.portfolio), x(s.benchmark)) + 6}" y="${y + 13}">${pct(s.portfolio)}</text>`;
  });
  return svg(W, H, g, "Sector weights, fund vs index");
}

function lineGrowth(risk) {
  const pts = risk.growth, W = 1120, H = 280, L = 48, R = 80, T = 12, B = 28;
  const lo = Math.min(...pts.map(p => Math.min(p.fund, p.benchmark)), 1), hi = Math.max(...pts.map(p => Math.max(p.fund, p.benchmark)), 1);
  const x = i => L + (W - L - R) * i / (pts.length - 1), y = v => T + (H - T - B) * (hi - v) / (hi - lo || 1);
  let g = "";
  for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4; g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 8}" y="${y(v) + 3}" text-anchor="end">${v.toFixed(2)}</text>`; }
  pts.forEach((p, i) => { if (i % 12 === 0 || i === pts.length - 1) g += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${p.month}</text>`; });
  const path = k => pts.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p[k])}`).join("");
  g += `<path class="l-bench" d="${path("benchmark")}"/><path class="l-fund" d="${path("fund")}"/>`;
  const last = pts[pts.length - 1];
  let yf = y(last.fund), yb = y(last.benchmark);
  if (Math.abs(yf - yb) < 14) { const mid = (yf + yb) / 2, up = last.fund >= last.benchmark; yf = mid + (up ? -8 : 8); yb = mid + (up ? 8 : -8); }
  g += `<text class="strong" x="${W - R + 8}" y="${yf + 4}">Fund</text><text x="${W - R + 8}" y="${yb + 4}">Index</text>`;
  pts.forEach((p, i) => g += `<rect class="hit" x="${x(i) - (W - L - R) / pts.length / 2}" y="${T}" width="${(W - L - R) / pts.length}" height="${H - T - B}"><title>${p.month}: fund ${p.fund.toFixed(3)}, index ${p.benchmark.toFixed(3)}</title></rect>`);
  return svg(W, H, g, "Growth of 1 dollar, fund vs index");
}

function moverTable(rows, title) {
  return `<div><h3 class="h3">${title}</h3><table class="mini"><tbody>${rows.map(r => `<tr>
    <td class="co"><b>${esc(r.name || r.ticker)}</b><span class="tk">${r.ticker} · ${esc(r.sector || "")}</span></td>
    <td class="r num">${f1(r.total_score)}</td><td class="r num">${pp(r.active_weight)}</td></tr>`).join("")}</tbody></table></div>`;
}

function holdingsTable() {
  const q = PF.q.toLowerCase();
  let rows = PF.data.holdings;
  if (q) rows = rows.filter(r => r.ticker.toLowerCase().includes(q) || (r.name || "").toLowerCase().includes(q));
  const bodyRows = rows.slice(0, PF.limit).map(r => `<tr class="${r.status !== "held" ? "out" : ""}">
    <td class="co"><b>${esc(r.name || r.ticker)}</b><span class="tk">${r.ticker}</span></td>
    <td class="muted">${esc(r.sector || "")}</td><td class="r num">${f1(r.total_score)}</td>
    <td class="r num">${pct(r.benchmark_weight, 2)}</td><td class="r num"><b>${pct(r.weight, 2)}</b></td>
    <td class="r num">${usd(r.weight * 1e9)}</td>
    <td class="reason">${esc(r.reason)}</td></tr>`).join("");
  return `<div class="table-wrap"><table class="rank holdings"><thead><tr><th>Company</th><th>Sector</th><th class="r">Score</th><th class="r">Index</th><th class="r">Fund</th><th class="r">of $1bn</th><th>Why</th></tr></thead>
    <tbody>${bodyRows}</tbody></table></div>${rows.length > PF.limit ? `<button type="button" class="ghost more" id="pf-more">Show all ${rows.length}</button>` : ""}`;
}

function renderPortfolio() {
  if (!PF.data) return loadPortfolio();
  $("#view-portfolio").classList.remove("busy");
  const d = PF.data, s = d.settings, sm = d.summary, c = sm.climate, t = sm.scores.total_score;
  const waciCut = c.waci_tco2e_per_musd.benchmark ? 1 - c.waci_tco2e_per_musd.portfolio / c.waci_tco2e_per_musd.benchmark : null;
  const fossilOn = FOSSIL.every(x => s.exclude_sub_industries.includes(x));
  const bench = s.benchmark === "cap" ? "market-cap weighted S&P 500" : "equal-weighted S&P 500";
  const r = d.risk;

  $("#view-portfolio").innerHTML = `
    <div class="head"><p class="eyebrow">Fund · ${esc(weightsText())}</p>
      <h2>A sustainability-tilted S&amp;P 500 fund.</h2>
      <p class="lead">Every company stays investable except the excluded sub-industries. Better-scoring companies get more weight, worse ones less;
      each sector keeps its size; no company above ${pct(s.max_weight, 0)}. Compared with the ${bench}.</p></div>

    <div class="controls">
      <div><span class="label">Method</span>${seg("method", [["tilt", "Tilt"], ["exclude", "Exclude worst"]], s.method)}</div>
      ${s.method === "tilt"
        ? `<div><span class="label">Tilt strength</span>${seg("tilt_strength", [[0, "0"], [0.3, "0.3"], [0.6, "0.6"], [1, "1.0"]], s.tilt_strength)}</div>`
        : `<div><span class="label">Drop worst</span>${seg("exclude_bottom_pct", [[0.1, "10%"], [0.2, "20%"], [0.3, "30%"]], s.exclude_bottom_pct)}</div>`}
      <div><span class="label">Sectors</span>${seg("sector_neutral", [[true, "Neutral"], [false, "Free"]], s.sector_neutral)}</div>
      <div><span class="label">Benchmark</span>${seg("benchmark", [["equal", "Equal"], ["cap", "Market cap"]], s.benchmark)}</div>
      <div><span class="label">Fossil fuels &amp; tobacco</span>${seg("exclude_sub_industries", [[FOSSIL, "Excluded"], [[], "Allowed"]], fossilOn ? FOSSIL : (s.exclude_sub_industries.length ? null : []))}</div>
    </div>

    ${PF.error ? `<p class="note" role="status">${esc(PF.error)}</p>` : ""}
    ${s.benchmark === "cap" && d.market && d.market.available ? `<p class="note" role="status">Market caps at ${esc(d.market.month)} month-end for ${d.market.with_cap} of ${d.market.companies} companies (SEC share counts × closing price). The ${d.market.companies - d.market.with_cap} without one are not in the benchmark and not held - nothing is estimated.</p>` : ""}
    <div class="kpis">
      ${kpi("Sustainability score", f1(t.portfolio), f1(t.benchmark), isNum(t.portfolio) && isNum(t.benchmark) ? `${signed(t.portfolio - t.benchmark)} points` : "", t.portfolio > t.benchmark)}
      ${kpi("Carbon intensity", c.waci_tco2e_per_musd.portfolio == null ? "–" : c.waci_tco2e_per_musd.portfolio.toFixed(0), c.waci_tco2e_per_musd.benchmark == null ? "–" : c.waci_tco2e_per_musd.benchmark.toFixed(0) + " tCO₂e/$M", waciCut == null ? "" : `${waciCut >= 0 ? "−" : "+"}${Math.abs(waciCut * 100).toFixed(0)}%`, waciCut > 0)}
      ${kpi("Science-based target", pct(c.sbti_target_share.portfolio, 0), pct(c.sbti_target_share.benchmark, 0), "of the money", c.sbti_target_share.portfolio > c.sbti_target_share.benchmark)}
      ${kpi("Holdings", sm.holdings, sm.companies, `${sm.excluded_policy} excluded by sub-industry${sm.excluded_score ? `, ${sm.excluded_score} by score` : ""}`, false)}
      ${r ? kpi("Tracking error", pct(r.tracking_error), "0%", `${r.months} months · correlation ${r.correlation.toFixed(2)}`, false)
          : kpi("Active share", pct(sm.active_share, 0), "0%", "how different from the index", false)}
    </div>

    <div class="grid2">
      <figure class="fig"><h3 class="h3">Scores, weighted by the fund</h3>${barsScores(sm.scores)}
        <figcaption><span class="key fund"></span>Fund <span class="key bench"></span>Index · 0–100, ranked within sector</figcaption></figure>
      <figure class="fig"><h3 class="h3">Sector weights</h3>${barsSectors(d.sectors)}
        <figcaption><span class="key fund"></span>Fund <span class="key bench"></span>Index${s.sector_neutral ? " · sector-neutral: differences come only from exclusions" : ""}</figcaption></figure>
    </div>

    ${r ? `<figure class="fig"><h3 class="h3">Hypothetical: today's fund over the last ${r.months} months</h3>${lineGrowth(r)}
      <figcaption>Fund ${pct(r.fund.annual_return)} a year (volatility ${pct(r.fund.volatility)}) · index ${pct(r.benchmark.annual_return)} (${pct(r.benchmark.volatility)}) ·
      tracking error ${pct(r.tracking_error)}. ${esc(r.caveat)}. ${pct(r.covered_weight, 0)} of the fund has a full price history.</figcaption></figure>`
      : `<p class="muted">Risk and return need price data: <code>python portfolio/marketdata.py</code></p>`}

    <div class="grid2">
      ${moverTable(sm.overweights, "Largest overweights")}
      ${moverTable(sm.underweights, "Largest underweights")}
    </div>

    <div class="row-h"><h3 class="h3">All ${d.holdings.length} companies</h3><input type="search" id="pf-q" placeholder="Search company or ticker" aria-label="Search holdings" value="${esc(PF.q)}"></div>
    <div id="pf-holdings">${holdingsTable()}</div>`;

  $$("#view-portfolio .seg button").forEach(b => b.onclick = () => {
    const v = JSON.parse(b.dataset.v), previous = PF.settings;
    PF.settings = { ...PF.settings, [b.dataset.set]: v };
    loadPortfolio(previous);
  });
  const bindHoldings = () => { const m = $("#pf-more"); if (m) m.onclick = () => { PF.limit = 1e6; $("#pf-holdings").innerHTML = holdingsTable(); bindHoldings(); }; };
  $("#pf-q").oninput = e => { PF.q = e.target.value; $("#pf-holdings").innerHTML = holdingsTable(); bindHoldings(); };
  bindHoldings();
}
