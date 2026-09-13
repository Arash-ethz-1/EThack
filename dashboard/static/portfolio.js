/* Portfolio tab - dashboard/static/portfolio.js (loaded after app.js, uses its helpers).
   Only displays. Weights, fund-vs-benchmark numbers, climate numbers and risk all come
   from POST /api/portfolio (portfolio/allocate.py + portfolio/risk.py). Changing a control
   re-runs the allocation on the server for this view only - nothing is saved. */

const PF = { data: null, settings: {}, q: "", limit: 25, busy: false };
const pct = (v, d = 1) => v == null ? "–" : (v * 100).toFixed(d) + "%";
const pp = v => v == null ? "–" : (v >= 0 ? "+" : "−") + Math.abs(v * 100).toFixed(2) + " pp";
const FOSSIL = ["Integrated Oil & Gas", "Oil & Gas Equipment & Services", "Oil & Gas Exploration & Production",
  "Oil & Gas Refining & Marketing", "Oil & Gas Storage & Transportation", "Tobacco"];

async function loadPortfolio(previous) {
  PF.busy = true; renderPortfolioShell();
  const res = await postJSON("/api/portfolio", { profile: state.profileId, category_weights: state.categoryWeights, settings: PF.settings });
  PF.busy = false;
  if (res.error) { PF.settings = previous || {}; PF.error = res.error; } else { PF.data = res; PF.error = null; }
  if (!PF.data) { $("#view-portfolio").innerHTML = `<p class="muted">${esc(PF.error)}</p>`; return; }
  renderPortfolio();
}

function renderPortfolioShell() {
  const el = $("#view-portfolio");
  if (!PF.data) el.innerHTML = `<div class="lede"><div><h2>Building the fund…</h2><p>Allocating on the server.</p></div></div>`;
  else el.classList.toggle("busy", PF.busy);
}

function seg(name, options, current) {
  return `<div class="seg" role="group" aria-label="${esc(name)}">${options.map(([v, l]) =>
    `<button type="button" data-set="${esc(name)}" data-v='${JSON.stringify(v)}' aria-pressed="${JSON.stringify(v) === JSON.stringify(current)}">${l}</button>`).join("")}</div>`;
}

function kpi(label, fund, bench, note, good) {
  return `<div class="kpi"><span class="label">${label}</span><span class="v">${fund}</span>
    <span class="vs">benchmark ${bench}</span>${note ? `<span class="delta ${good ? "good" : ""}">${note}</span>` : ""}</div>`;
}

function barsScores(scores) {
  const rows = [["total_score", "Total"], ...CATS.map(([id, n]) => [`${id}_score`, n])];
  const W = 560, L = 110, R = 50, rowH = 44, H = rows.length * rowH + 24, x = v => L + (W - L - R) * v / 100;
  let g = "";
  [0, 25, 50, 75, 100].forEach(v => g += `<line class="grid" x1="${x(v)}" x2="${x(v)}" y1="0" y2="${H - 20}"/><text x="${x(v)}" y="${H - 6}" text-anchor="middle">${v}</text>`);
  rows.forEach(([k, n], i) => {
    const s = scores[k] || {}, y = i * rowH + 6;
    g += `<text class="strong" x="${L - 10}" y="${y + 17}" text-anchor="end">${n}</text>`;
    if (isNum(s.benchmark)) g += `<rect class="b-bench" x="${L}" y="${y + 20}" width="${x(s.benchmark) - L}" height="10" rx="2"><title>Benchmark ${s.benchmark.toFixed(1)}</title></rect>`;
    if (isNum(s.portfolio)) g += `<rect class="b-fund" x="${L}" y="${y + 6}" width="${x(s.portfolio) - L}" height="12" rx="2"><title>Fund ${s.portfolio.toFixed(1)}</title></rect>
      <text x="${x(s.portfolio) + 6}" y="${y + 16}">${s.portfolio.toFixed(1)}</text>`;
  });
  return svg(W, H, g, "Weighted scores, fund vs benchmark");
}

function barsSectors(sectors) {
  const max = Math.max(...sectors.map(s => Math.max(s.portfolio, s.benchmark)), 0.01);
  const W = 560, L = 170, R = 70, rowH = 30, H = sectors.length * rowH + 10, x = v => L + (W - L - R) * v / max;
  let g = "";
  sectors.forEach((s, i) => {
    const y = i * rowH + 4;
    g += `<text class="strong" x="${L - 10}" y="${y + 14}" text-anchor="end">${esc(s.sector)}</text>
      <rect class="b-bench" x="${L}" y="${y + 13}" width="${Math.max(0, x(s.benchmark) - L)}" height="6" rx="2"><title>Benchmark ${pct(s.benchmark)}</title></rect>
      <rect class="b-fund" x="${L}" y="${y + 3}" width="${Math.max(0, x(s.portfolio) - L)}" height="9" rx="2"><title>Fund ${pct(s.portfolio)}</title></rect>
      <text x="${Math.max(x(s.portfolio), x(s.benchmark)) + 6}" y="${y + 13}">${pct(s.portfolio)}</text>`;
  });
  return svg(W, H, g, "Sector weights, fund vs benchmark");
}

function lineGrowth(risk) {
  const pts = risk.growth, W = 560, H = 220, L = 44, R = 70, T = 10, B = 26;
  const lo = Math.min(...pts.map(p => Math.min(p.fund, p.benchmark)), 1), hi = Math.max(...pts.map(p => Math.max(p.fund, p.benchmark)), 1);
  const x = i => L + (W - L - R) * i / (pts.length - 1), y = v => T + (H - T - B) * (hi - v) / (hi - lo || 1);
  let g = "";
  for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4; g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 3}" text-anchor="end">${v.toFixed(2)}</text>`; }
  pts.forEach((p, i) => { if (i % 12 === 0 || i === pts.length - 1) g += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${p.month}</text>`; });
  const path = k => pts.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p[k])}`).join("");
  g += `<path class="l-bench" d="${path("benchmark")}"/><path class="l-fund" d="${path("fund")}"/>`;
  const last = pts[pts.length - 1];
  g += `<text class="strong" x="${W - R + 6}" y="${y(last.fund) + 4}">Fund</text><text x="${W - R + 6}" y="${y(last.benchmark) + 4}">Benchmark</text>`;
  pts.forEach((p, i) => g += `<rect class="hit" x="${x(i) - (W - L - R) / pts.length / 2}" y="${T}" width="${(W - L - R) / pts.length}" height="${H - T - B}"><title>${p.month}: fund ${p.fund.toFixed(3)}, benchmark ${p.benchmark.toFixed(3)}</title></rect>`);
  return svg(W, H, g, "Growth of 1 dollar, fund vs benchmark");
}

function moverTable(rows, title) {
  return `<div class="movers"><h3>${title}</h3><table class="mini"><tbody>${rows.map(r => `<tr>
    <td class="co"><b>${esc(r.name || r.ticker)}</b><span class="mono">${r.ticker} · ${esc(r.sector || "")}</span></td>
    <td class="r num">${f1(r.total_score)}</td><td class="r num">${pp(r.active_weight)}</td></tr>`).join("")}</tbody></table></div>`;
}

function holdingsTable() {
  const q = PF.q.toLowerCase();
  let rows = PF.data.holdings;
  if (q) rows = rows.filter(r => r.ticker.toLowerCase().includes(q) || (r.name || "").toLowerCase().includes(q));
  const body = rows.slice(0, PF.limit).map(r => `<tr class="${r.status !== "held" ? "out" : ""}">
    <td class="co"><b>${esc(r.name || r.ticker)}</b><span class="mono">${r.ticker}</span></td>
    <td class="muted">${esc(r.sector || "")}</td><td class="r num">${f1(r.total_score)}</td>
    <td class="r num">${pct(r.benchmark_weight, 2)}</td><td class="r num"><b>${pct(r.weight, 2)}</b></td>
    <td class="reason">${esc(r.reason)}</td></tr>`).join("");
  return `<div class="table-wrap"><table class="rank holdings"><thead><tr><th>Company</th><th>Sector</th><th class="r">Score</th><th class="r">Benchmark</th><th class="r">Fund</th><th>Why</th></tr></thead>
    <tbody>${body}</tbody></table></div>${rows.length > PF.limit ? `<button type="button" class="btn more" id="pf-more">Show all ${rows.length}</button>` : ""}`;
}

function renderPortfolio() {
  if (!PF.data) return loadPortfolio();
  $("#view-portfolio").classList.remove("busy");
  const d = PF.data, s = d.settings, sm = d.summary, c = sm.climate, t = sm.scores.total_score;
  const profile = state.meta.profiles.find(p => p.id === state.profileId);
  const waciCut = c.waci_tco2e_per_musd.benchmark ? 1 - c.waci_tco2e_per_musd.portfolio / c.waci_tco2e_per_musd.benchmark : null;
  const fossilOn = FOSSIL.every(x => s.exclude_sub_industries.includes(x));
  const bench = s.benchmark === "cap" ? "market-cap weighted S&P 500" : "equal-weighted S&P 500";
  const r = d.risk;

  $("#view-portfolio").innerHTML = `
    <div class="lede"><div><span class="label">Profile · ${esc(profile ? profile.name : state.profileId)}</span>
      <h2>A sustainability-tilted S&amp;P 500 fund.</h2>
      <p>Every company stays investable except the excluded sub-industries. Better-scoring companies get more weight, worse ones less,
      each sector keeps its size, no company above ${pct(s.max_weight, 0)}. Compared with the ${bench}.</p></div></div>

    <div class="pf-controls">
      <div><span class="label">Method</span>${seg("method", [["tilt", "Tilt"], ["exclude", "Exclude worst"]], s.method)}</div>
      ${s.method === "tilt"
        ? `<div><span class="label">Tilt strength</span>${seg("tilt_strength", [[0, "0"], [0.3, "0.3"], [0.6, "0.6"], [1, "1.0"]], s.tilt_strength)}</div>`
        : `<div><span class="label">Drop worst</span>${seg("exclude_bottom_pct", [[0.1, "10%"], [0.2, "20%"], [0.3, "30%"]], s.exclude_bottom_pct)}</div>`}
      <div><span class="label">Sectors</span>${seg("sector_neutral", [[true, "Neutral"], [false, "Free"]], s.sector_neutral)}</div>
      <div><span class="label">Benchmark</span>${seg("benchmark", [["equal", "Equal"], ["cap", "Market cap"]], s.benchmark)}</div>
      <div><span class="label">Fossil fuels &amp; tobacco</span>${seg("exclude_sub_industries", [[FOSSIL, "Excluded"], [[], "Allowed"]], fossilOn ? FOSSIL : (s.exclude_sub_industries.length ? null : []))}</div>
    </div>

    ${PF.error ? `<p class="pf-error" role="status">${esc(PF.error)}</p>` : ""}
    ${s.benchmark === "cap" && d.market && d.market.available ? `<p class="pf-error" role="status">Market caps at ${esc(d.market.month)} month-end for ${d.market.with_cap} of ${d.market.companies} companies (SEC share counts x closing price). The ${d.market.companies - d.market.with_cap} without one are not in the benchmark and not held - nothing is estimated.</p>` : ""}
    <div class="kpis">
      ${kpi("Sustainability score", f1(t.portfolio), f1(t.benchmark), isNum(t.portfolio) && isNum(t.benchmark) ? `${(t.portfolio - t.benchmark >= 0 ? "+" : "")}${(t.portfolio - t.benchmark).toFixed(1)} points` : "", t.portfolio > t.benchmark)}
      ${kpi("Carbon intensity", c.waci_tco2e_per_musd.portfolio == null ? "–" : c.waci_tco2e_per_musd.portfolio.toFixed(0), c.waci_tco2e_per_musd.benchmark == null ? "–" : c.waci_tco2e_per_musd.benchmark.toFixed(0) + " tCO₂e/$M", waciCut == null ? "" : `${waciCut >= 0 ? "−" : "+"}${Math.abs(waciCut * 100).toFixed(0)}% vs benchmark`, waciCut > 0)}
      ${kpi("Science-based climate target", pct(c.sbti_target_share.portfolio, 0), pct(c.sbti_target_share.benchmark, 0), "of weight in companies with a validated SBTi target", c.sbti_target_share.portfolio > c.sbti_target_share.benchmark)}
      ${kpi("Holdings", sm.holdings, sm.companies, `${sm.excluded_policy} excluded by sub-industry${sm.excluded_score ? `, ${sm.excluded_score} by score` : ""}`, false)}
      ${r ? kpi("Tracking error", pct(r.tracking_error), "0%", `${r.months} months, correlation ${r.correlation.toFixed(2)}`, false)
          : kpi("Active share", pct(sm.active_share, 0), "0%", "how different from the benchmark", false)}
    </div>

    <div class="pf-grid">
      <figure class="fig"><h3>Scores, weighted by the fund</h3>${barsScores(sm.scores)}
        <figcaption><span class="key fund"></span>Fund <span class="key bench"></span>Benchmark · 0–100, ranked within sector</figcaption></figure>
      <figure class="fig"><h3>Sector weights</h3>${barsSectors(d.sectors)}
        <figcaption><span class="key fund"></span>Fund <span class="key bench"></span>Benchmark${s.sector_neutral ? " · sector-neutral: differences come only from exclusions" : ""}</figcaption></figure>
    </div>

    ${r ? `<figure class="fig wide"><h3>Hypothetical: today's fund over the last ${r.months} months</h3>${lineGrowth(r)}
      <figcaption>Fund ${pct(r.fund.annual_return)} a year (volatility ${pct(r.fund.volatility)}) · benchmark ${pct(r.benchmark.annual_return)} (${pct(r.benchmark.volatility)}) ·
      tracking error ${pct(r.tracking_error)}. ${esc(r.caveat)}. ${pct(r.covered_weight, 0)} of the fund has a full price history.</figcaption></figure>`
      : `<p class="muted pf-note">Risk and return need price data: <code>python portfolio/marketdata.py</code></p>`}

    <div class="pf-grid">
      ${moverTable(sm.overweights, "Largest overweights")}
      ${moverTable(sm.underweights, "Largest underweights")}
    </div>

    <div class="chain-h"><h3>All ${d.holdings.length} companies</h3><input type="search" id="pf-q" placeholder="Company or ticker" aria-label="Search holdings" value="${esc(PF.q)}"></div>
    <div id="pf-holdings">${holdingsTable()}</div>

    <div class="cube-card">
      <div class="chain-h"><h3>Where the fund leans</h3><span class="muted" style="font-size:12px">every company by its three pillar scores · red = overweight · drag to rotate</span></div>
      <canvas id="cube" height="320"></canvas>
    </div>`;

  $$("#view-portfolio .seg button").forEach(b => b.onclick = () => {
    const v = JSON.parse(b.dataset.v), previous = PF.settings;
    PF.settings = { ...PF.settings, [b.dataset.set]: v };
    loadPortfolio(previous);
  });
  const bindHoldings = () => { const m = $("#pf-more"); if (m) m.onclick = () => { PF.limit = 1e6; $("#pf-holdings").innerHTML = holdingsTable(); bindHoldings(); }; };
  $("#pf-q").oninput = e => { PF.q = e.target.value; $("#pf-holdings").innerHTML = holdingsTable(); bindHoldings(); };
  bindHoldings();
  initCube();
}

/* ---------- 3D cube: every company by its three pillar scores, overweights highlighted ---------- */
const CUBE = { yaw: -0.6, pitch: -0.35, drag: null, raf: null, spin: true };
const CUBE_AXES = ["economic_score", "social_score", "environmental_score"];

function cubeRows() {
  if (!state.score) return [];
  const active = PF.data ? Object.fromEntries(PF.data.holdings.map(h => [h.ticker, h.active_weight])) : {};
  return state.score.rows.filter(r => CUBE_AXES.every(k => isNum(r[k]))).map(r => ({ ...r, active: active[r.ticker] }));
}
function cubeProject(v, w, h) {
  const cy = Math.cos(CUBE.yaw), sy = Math.sin(CUBE.yaw), cp = Math.cos(CUBE.pitch), sp = Math.sin(CUBE.pitch);
  const x1 = v[0] * cy + v[2] * sy, z1 = -v[0] * sy + v[2] * cy;
  const y1 = v[1] * cp - z1 * sp, z2 = v[1] * sp + z1 * cp;
  const d = 4.2, k = d / (d + z2), scale = Math.min(w, h) * 0.34;
  return [w / 2 + x1 * scale * k, h / 2 - y1 * scale * k, z2];
}
function drawCube() {
  const c = $("#cube");
  if (!c) return;
  const dpr = window.devicePixelRatio || 1, w = c.clientWidth, h = 320;
  if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr; }
  const g = c.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h);
  const css = getComputedStyle(document.body);
  const line = css.getPropertyValue("--rule").trim() || "#ccc", muted = css.getPropertyValue("--muted").trim() || "#888";
  const accent = css.getPropertyValue("--accent").trim() || "#d52b1e";
  const C = [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]];
  const E = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]];
  g.strokeStyle = line; g.lineWidth = 1;
  E.forEach(([a, b]) => { const p = cubeProject(C[a], w, h), q = cubeProject(C[b], w, h); g.beginPath(); g.moveTo(p[0], p[1]); g.lineTo(q[0], q[1]); g.stroke(); });
  g.fillStyle = muted; g.font = "11px sans-serif";
  [[[1, -1, -1], "Economic"], [[-1, 1, -1], "Social"], [[-1, -1, 1], "Environmental"]].forEach(([v, t]) => { const p = cubeProject(v, w, h); g.fillText(t, p[0] + 4, p[1] - 4); });
  cubeRows().map(r => ({ p: cubeProject(CUBE_AXES.map(k => r[k] / 50 - 1), w, h), a: r.active }))
    .sort((a, b) => b.p[2] - a.p[2])
    .forEach(d => { g.globalAlpha = d.a > 0 ? .9 : .35; g.fillStyle = d.a > 0 ? accent : muted; g.beginPath(); g.arc(d.p[0], d.p[1], d.a > 0 ? 3 : 2.2, 0, 7); g.fill(); });
  g.globalAlpha = 1;
}
function initCube() {
  const c = $("#cube");
  if (!c) return;
  drawCube();
  const move = e => {
    if (!CUBE.drag) return;
    const t = e.touches ? e.touches[0] : e;
    CUBE.yaw += (t.clientX - CUBE.drag.x) * 0.01; CUBE.pitch = Math.max(-1.3, Math.min(1.3, CUBE.pitch + (t.clientY - CUBE.drag.y) * 0.01));
    CUBE.drag = { x: t.clientX, y: t.clientY }; drawCube();
  };
  const down = e => { CUBE.spin = false; const t = e.touches ? e.touches[0] : e; CUBE.drag = { x: t.clientX, y: t.clientY }; };
  c.addEventListener("mousedown", down); c.addEventListener("touchstart", down, { passive: true });
  if (!CUBE.bound) {
    window.addEventListener("mousemove", move); window.addEventListener("touchmove", move, { passive: true });
    window.addEventListener("mouseup", () => { CUBE.drag = null; }); window.addEventListener("touchend", () => { CUBE.drag = null; });
    window.addEventListener("resize", drawCube); CUBE.bound = true;
  }
  if (CUBE.raf) cancelAnimationFrame(CUBE.raf);
  const tick = () => { if (CUBE.spin && !CUBE.drag && $("#cube")) { CUBE.yaw += 0.0035; drawCube(); } CUBE.raf = requestAnimationFrame(tick); };
  tick();
}
