/* S&P 500 Impact - dashboard/static/app.js
   Only displays. Every score comes from POST /api/score (common/score.py); every
   check result comes from GET /api/checks (checks/results/*.json, written by
   `python run.py verify`). Nothing here ranks, scores or calls a model. */

const CATS = [["economic", "Economic", "--econ"], ["social", "Social", "--soc"], ["environmental", "Environmental", "--env"]];
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const f1 = v => v == null ? '<span class="muted">–</span>' : v.toFixed(1);
const isNum = v => typeof v === "number" && Number.isFinite(v);
const fmtVal = (v, unit) => v == null ? "–" : unit === "pct_points" ? (v * 100).toFixed(1) + " pp" : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-US") : String(+v.toFixed(3));

const state = {
  meta: null, profileId: null, categoryWeights: { economic: 1, social: 1, environmental: 1 },
  score: null, checks: null, q: "", sector: "", limit: 50, ex: "A",
};

async function getJSON(path) {
  const r = await fetch(path);
  return r.json();
}
async function postJSON(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-EThack": "1" }, body: JSON.stringify(body) });
  return r.json();
}
function META(id) { return (state.meta.indicators.find(m => m.id === id)) || { name: id, cat: "" }; }
function colOf(id) { const m = META(id); return `var(${(CATS.find(c => c[0] === m.category) || CATS[0])[2]})`; }

/* ---------- tabs ---------- */
function bindTabs() {
  $$("nav.tabs button").forEach(b => b.addEventListener("click", () => {
    $$("nav.tabs button").forEach(x => x.setAttribute("aria-selected", String(x === b)));
    $("#view-ranking").hidden = b.dataset.view !== "ranking";
    $("#view-portfolio").hidden = b.dataset.view !== "portfolio";
    $("#view-evidence").hidden = b.dataset.view !== "evidence";
    if (b.dataset.view === "portfolio") renderPortfolio();
    if (b.dataset.view === "evidence") { renderIndex(); renderExhibit(); }
  }));
}

/* ---------- ranking ---------- */
function renderWeights() {
  $("#weights").innerHTML = CATS.map(([id, n, c]) => `<div class="w"><span><span class="sw" style="background:var(${c})"></span>${n}</span>
      <div class="seg" role="group" aria-label="${n} weight">${["Off", "1×", "2×"].map((l, k) =>
    `<button type="button" data-id="${id}" data-k="${k}" aria-pressed="${state.categoryWeights[id] === k}">${l}</button>`).join("")}</div></div>`).join("")
    + `<small>Adjusting a weight re-scores on the server via common/score.py - nothing is computed in the browser, and nothing is saved.</small>`;
  $$("#weights button").forEach(b => b.addEventListener("click", async () => {
    const w = { ...state.categoryWeights }; w[b.dataset.id] = +b.dataset.k;
    if (Object.values(w).every(x => !x)) return;
    state.categoryWeights = w; renderWeights();
    await loadScore();
  }));
}
$("#wbtn")?.addEventListener("click", () => { const o = $("#weights").hidden; $("#weights").hidden = !o; $("#wbtn").setAttribute("aria-expanded", String(o)); });

function fingerprint(ticker) {
  const fp = (state.score.fingerprints || {})[ticker] || {};
  let prev = null, out = "";
  state.meta.indicators.forEach(m => {
    if (prev && m.category !== prev) out += `<i class="sp"></i>`;
    prev = m.category;
    const pts = fp[m.id];
    out += pts != null
      ? `<i title="${esc(m.name)}: ${pts}"><b style="height:${Math.max(2, pts * .26)}px;background:${colOf(m.id)}"></b></i>`
      : `<i class="gap" title="${esc(m.name)}: no data"></i>`;
  });
  return `<span class="print">${out}</span>`;
}

function renderRows() {
  if (!state.score) return;
  let rows = state.score.rows;
  const q = state.q.toLowerCase();
  if (q) rows = rows.filter(r => r.ticker.toLowerCase().includes(q) || r.name.toLowerCase().includes(q));
  if (state.sector) rows = rows.filter(r => r.sector === state.sector);
  $("#rows").innerHTML = rows.slice(0, state.limit).map(r => `<tr tabindex="0" data-t="${r.ticker}">
      <td class="pos num">${r.position ?? "–"}</td>
      <td class="co"><b>${esc(r.name || r.ticker)}</b><span class="mono">${r.ticker}</span></td>
      <td class="muted">${esc(r.sector || "")}</td>
      <td>${fingerprint(r.ticker)}</td>
      <td class="r num">${f1(r.economic_score)}</td><td class="r num">${f1(r.social_score)}</td><td class="r num">${f1(r.environmental_score)}</td>
      <td class="r tot">${f1(r.total_score)}</td></tr>`).join("");
  $("#more").hidden = rows.length <= state.limit;
  $("#more").textContent = `Show all ${rows.length}`;
  $$("#rows tr").forEach(tr => { tr.onclick = () => openCompany(tr.dataset.t); tr.onkeydown = e => e.key === "Enter" && openCompany(tr.dataset.t); });
}

async function loadScore() {
  state.score = await postJSON("/api/score", { profile: state.profileId, category_weights: state.categoryWeights });
  renderRows();
}

/* ---------- company drawer: chain of evidence ---------- */
function flow(ticker, cats, inds) {
  const srcOf = x => x.source || "no data for this company";
  const srcs = [...new Set(inds.map(srcOf))];
  const W = 700, rowH = 46, H = Math.max(inds.length, srcs.length, 3) * rowH + 30;
  const X = [0, 230, 470, 620], NW = [180, 180, 110, 80];
  const yOf = (i, n) => 24 + (H - 24) / n * (i + .5);
  const curve = (x1, y1, x2, y2) => `M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`;
  let links = "", nodes = "";
  ["Source", "Indicator · points", "Category", "Total"].forEach((t, i) => nodes += `<text class="sub" x="${X[i]}" y="10">${t.toUpperCase()}</text>`);
  srcs.forEach((s, i) => { const y = yOf(i, srcs.length); nodes += `<rect class="node" x="0" y="${y - 16}" width="${NW[0]}" height="32"/><text x="10" y="${y + 4}">${esc(String(s).length > 26 ? s.slice(0, 25) + "…" : s)}</text>`; });
  inds.forEach((x, i) => {
    const y = yOf(i, inds.length), sy = yOf(srcs.indexOf(srcOf(x)), srcs.length);
    const ci = cats.findIndex(k => k[0] === x.category), cy = yOf(ci, cats.length), col = colOf(x.indicator_id);
    links += `<g class="hov"><path class="link" style="stroke:${col};stroke-opacity:.45" stroke-width="2" d="${curve(NW[0], sy, X[1], y)}"/>
      <path class="link" style="stroke:${col};stroke-opacity:.45" stroke-width="${1 + (x.points || 0) / 12}" d="${curve(X[1] + NW[1], y, X[2], cy)}"/></g>`;
    nodes += `<rect class="node" x="${X[1]}" y="${y - 16}" width="${NW[1]}" height="32" style="stroke:${col}"/><text x="${X[1] + 10}" y="${y + 4}">${esc(META(x.indicator_id).name)}</text>
      <text class="sub" x="${X[1] + NW[1] - 8}" y="${y + 4}" text-anchor="end">${x.points != null ? Math.round(x.points) : "–"}</text>`;
  });
  const ty = yOf(0, 1);
  cats.forEach(([id, n, col], i) => {
    const y = yOf(i, cats.length), val = state.currentCompany[`${id}_score`];
    links += `<path class="link" style="stroke:var(${col});stroke-opacity:.45" stroke-width="${1 + (val || 0) / 10}" d="${curve(X[2] + NW[2], y, X[3], ty)}"/>`;
    nodes += `<rect class="node" x="${X[2]}" y="${y - 16}" width="${NW[2]}" height="32" style="stroke:var(${col})"/><text x="${X[2] + 10}" y="${y + 4}">${n.slice(0, 5)}.</text>
      <text class="sub" x="${X[2] + NW[2] - 8}" y="${y + 4}" text-anchor="end">${val == null ? "–" : val.toFixed(0)}</text>`;
  });
  return `<svg class="flow" viewBox="0 0 ${W} ${H}" role="img" aria-label="Chain from source documents to total score">${links}${nodes}</svg>`;
}

async function openCompany(ticker) {
  const detail = await postJSON("/api/explain", { profile: state.profileId, category_weights: state.categoryWeights, ticker });
  const c = detail.company;
  state.currentCompany = c;
  const cats = CATS.filter(([id]) => detail.indicators.some(x => x.category === id));
  const rows = detail.indicators.map(x => `<div class="row"><div><b>${esc(META(x.indicator_id).name)}</b><div class="cat"><span class="sw" style="background:${colOf(x.indicator_id)}"></span>${x.category} · FY ${x.year}</div></div>
      <div class="num">${fmtVal(x.value, x.unit)}<div class="cat">${esc(x.unit || "")}</div></div><div class="pts">${x.points != null ? Math.round(x.points) : "–"}</div>
      <div class="src">${x.source_url ? `<a href="${esc(x.source_url)}" target="_blank" rel="noopener">${esc(x.source || "source")} ↗</a>` : '<span class="muted">no link on record</span>'}</div>
      <div class="note">${esc(x.note || "")}</div></div>`).join("");
  $("#drawer").innerHTML = `<header><div><span class="label mono">${c.ticker} · ${esc(c.sector || "")}</span><h2>${esc(c.name || c.ticker)}</h2></div><button type="button" class="btn" id="close">Close</button></header>
    <div class="score-line"><div><span class="label">Total</span><span class="v">${f1(c.total_score)}</span></div>${CATS.map(([id, n, col]) => `<div><span class="label"><span class="sw" style="background:var(${col})"></span>${n}</span><span class="v">${f1(c[`${id}_score`])}</span></div>`).join("")}</div>
    <div class="chain-h"><h3>Chain of evidence</h3><span class="muted" style="font-size:12px">Line width = points</span></div>
    ${flow(ticker, cats, detail.indicators)}
    <div class="ledger">${rows || '<p class="muted">No ready indicator has a value for this company.</p>'}</div>`;
  $("#drawer").hidden = $("#scrim").hidden = false; $("#close").onclick = closeCompany; $("#close").focus();
}
function closeCompany() { $("#drawer").hidden = $("#scrim").hidden = true; }
$("#scrim").onclick = closeCompany;
document.addEventListener("keydown", e => e.key === "Escape" && closeCompany());

/* ---------- portfolio: phase-3 preview + 3D impact cube ---------- */
const CUBE = { yaw: -0.6, pitch: -0.35, drag: null, raf: null, spin: true };
const CUBE_AXES = [["economic_score", "--econ"], ["social_score", "--soc"], ["environmental_score", "--env"]];

function cubeRows() {
  if (!state.score) return [];
  return state.score.rows.filter(r => CUBE_AXES.every(([k]) => isNum(r[k])));
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
  const line = css.getPropertyValue("--rule").trim() || "#ccc", ink = css.getPropertyValue("--muted").trim() || "#888";
  const accent = css.getPropertyValue("--accent").trim() || "#d52b1e";
  const C = [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]];
  const E = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]];
  g.strokeStyle = line; g.lineWidth = 1;
  E.forEach(([a, b]) => { const p = cubeProject(C[a], w, h), q = cubeProject(C[b], w, h); g.beginPath(); g.moveTo(p[0], p[1]); g.lineTo(q[0], q[1]); g.stroke(); });
  const hi = cubeProject([1, 1, 1], w, h);
  g.fillStyle = accent + "2e"; g.beginPath(); g.arc(hi[0], hi[1], 26, 0, 7); g.fill();
  g.fillStyle = ink; g.font = "11px Archivo, sans-serif";
  [[[1, -1, -1], "Economic"], [[-1, 1, -1], "Social"], [[-1, -1, 1], "Environmental"]].forEach(([v, t]) => { const p = cubeProject(v, w, h); g.fillText(t, p[0] + 4, p[1] - 4); });
  const pts = cubeRows().map(r => {
    const v = CUBE_AXES.map(([k]) => r[k] / 50 - 1);
    return { p: cubeProject(v, w, h), total: isNum(r.total_score) ? r.total_score : 50 };
  }).sort((a, b) => b.p[2] - a.p[2]);
  pts.forEach(d => { g.fillStyle = `hsl(${Math.round(8 + 1.42 * d.total)} 62% 45% / .82)`; g.beginPath(); g.arc(d.p[0], d.p[1], 2.6, 0, 7); g.fill(); });
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
  const up = () => { CUBE.drag = null; };
  c.addEventListener("mousedown", down); c.addEventListener("touchstart", down, { passive: true });
  window.addEventListener("mousemove", move); window.addEventListener("touchmove", move, { passive: true });
  window.addEventListener("mouseup", up); window.addEventListener("touchend", up); window.addEventListener("resize", drawCube);
  if (CUBE.raf) cancelAnimationFrame(CUBE.raf);
  const tick = () => { if (CUBE.spin && !CUBE.drag && $("#cube")) { CUBE.yaw += 0.0035; drawCube(); } CUBE.raf = requestAnimationFrame(tick); };
  tick();
}
function renderPortfolio() {
  const rows = cubeRows();
  const missing = CUBE_AXES.filter(([k]) => !state.score.rows.some(r => isNum(r[k])));
  const label = k => (CATS.find(c => k.startsWith(c[0])) || [, k])[1];
  const note = missing.length
    ? `<p class="sub muted">No data yet on ${missing.map(a => label(a[0])).join(" / ")} - that axis stays empty until those indicators are ready.</p>`
    : `<p class="sub muted">${rows.length} companies with all three category scores. Drag to rotate.</p>`;
  $("#view-portfolio").innerHTML = `
    <div class="lede"><div><h2>Turning a score into a portfolio.</h2>
      <p>Phase 3 (not built yet): a profile's scores weight an allocation across the S&amp;P 500. This previews the idea -
      every company plotted by its three category scores. The corner where all three are high is where a score-tilted
      portfolio overweights.</p></div></div>
    <div class="steps">
      <div class="card"><div class="n">1</div><h4>Scores in</h4><p>Total and category scores per company, from the profile selected in Ranking.</p></div>
      <div class="card"><div class="n">2</div><h4>Allocation rule</h4><p>Tilt toward high scores, or exclude the bottom X%, with a cap per company and optional sector neutrality.</p></div>
      <div class="card"><div class="n">3</div><h4>Weights out</h4><p>Portfolio weights that sum to 100% of the fund. Not implemented - see <code>portfolio/allocate.py</code>.</p></div>
    </div>
    <div class="cube-card">
      <div class="chain-h"><h3>Impact cube</h3><span class="muted" style="font-size:12px">high / high / high = overweight</span></div>
      ${note}
      <canvas id="cube" height="320"></canvas>
      <div class="cube-legend">${CATS.map(([, n, c]) => `<span><i style="background:var(${c})"></i>${n}</span>`).join("")}</div>
    </div>`;
  initCube();
}

/* ---------- evidence ---------- */
const sc = (d0, d1, r0, r1) => v => r0 + (v - d0) / (d1 - d0) * (r1 - r0);
const svg = (w, h, g, label) => `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="${label}">${g}</svg>`;
const pending = (what, cmd) => `<div class="pend"><p style="margin:0 0 6px">${esc(what)}</p><code style="font-size:12px">${esc(cmd)}</code></div>`;
function check(id) { return (state.checks.checks || []).find(c => c.id === id); }
function statusLabel(s) { return s === "not_run" ? "not run" : s; }

function chartSourced(perInd) {
  const W = 720, L = 190, R = 90, rowH = 34, H = perInd.length * rowH + 30, x = sc(0, state.meta.companies, L, W - R);
  let g = "";
  const n5 = state.meta.companies;
  [0, n5 * .25, n5 * .5, n5 * .75, n5].forEach(v => g += `<line class="grid" x1="${x(v)}" x2="${x(v)}" y1="4" y2="${H - 22}"/><text x="${x(v)}" y="${H - 6}" text-anchor="middle">${Math.round(v)}</text>`);
  perInd.forEach((p, i) => {
    const y = 8 + i * rowH, name = META(p.indicator_id).name;
    g += `<text class="strong" x="${L - 12}" y="${y + 15}" text-anchor="end">${esc(name)}</text><rect x="${L}" y="${y + 4}" width="${x(p.companies) - L}" height="16" style="fill:${colOf(p.indicator_id)}"/><text x="${x(p.companies) + 8}" y="${y + 16}">${p.companies} / ${n5}</text>`;
  });
  return svg(W, H, g, "Companies with a sourced value per indicator");
}

function chartOutlierCounts(rows) {
  const counts = {};
  rows.forEach(r => { counts[r.indicator_id] = (counts[r.indicator_id] || 0) + 1; });
  const ids = Object.keys(counts).sort((a, b) => counts[b] - counts[a]);
  const W = 720, L = 190, R = 60, rowH = 30, H = ids.length * rowH + 20, max = Math.max(...ids.map(i => counts[i]), 1);
  const x = sc(0, max, L, W - R);
  let g = "";
  ids.forEach((id, i) => {
    const y = 8 + i * rowH, name = id.includes(" & ") ? id : META(id).name;
    g += `<text class="strong" x="${L - 12}" y="${y + 15}" text-anchor="end">${esc(name)}</text><rect x="${L}" y="${y + 4}" width="${Math.max(1, x(counts[id]) - L)}" height="16" style="fill:var(--flag)"/><text x="${x(counts[id]) + 8}" y="${y + 16}">${counts[id]}</text>`;
  });
  return svg(W, H, g, "Flagged rows per indicator");
}

function chartStability(series) {
  const ids = Object.keys(series).filter(k => series[k].length >= 1);
  if (!ids.length) return "";
  const years = ids.flatMap(id => series[id].map(p => p.year));
  const y0 = Math.min(...years), y1 = Math.max(...years);
  const W = 720, H = 280, L = 36, R = 150, T = 16, B = 30;
  const x = sc(y0 - 0.5, y1 + 0.5, L, W - R), y = sc(0, 1, H - B, T);
  let g = "";
  [0, .25, .5, .75, 1].forEach(v => g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 3}" text-anchor="end">${v}</text>`);
  for (let yr = y0; yr <= y1; yr++) g += `<text x="${x(yr)}" y="${H - 8}" text-anchor="middle">${yr}</text>`;
  const labs = [];
  ids.forEach(id => {
    const p = series[id], col = colOf(id), l = p[p.length - 1];
    g += `<polyline class="line" style="stroke:${col}" points="${p.map(q => `${x(q.year)},${y(q.rho)}`).join(" ")}"/><circle cx="${x(l.year)}" cy="${y(l.rho)}" r="3.5" style="fill:${col}"/>`;
    labs.push({ y: y(l.rho), t: META(id).name, col });
  });
  labs.sort((a, b) => a.y - b.y).forEach((l, i, a) => { if (i && l.y - a[i - 1].y < 13) l.y = a[i - 1].y + 13; g += `<text class="strong" x="${W - R + 10}" y="${l.y + 4}" style="fill:${l.col}">${esc(l.t)}</text>`; });
  return svg(W, H, g, "Year to year rank stability per indicator");
}

function corrMatrix(pairs) {
  const ids = [...new Set(Object.keys(pairs).flatMap(k => k.split("|")))].sort();
  const m = ids.map((a, i) => ids.map((b, j) => { if (j >= i) return null; const p = pairs[`${b}|${a}`] || pairs[`${a}|${b}`]; return p ? p.rho : null; }));
  return { ids, m };
}
function corrTable(pairs) {
  const { ids, m } = corrMatrix(pairs);
  return `<div class="table-wrap"><table class="corr"><thead><tr><th></th>${ids.map(id => `<th>${esc(META(id).name)}</th>`).join("")}</tr></thead><tbody>
    ${ids.map((id, i) => `<tr><th>${esc(META(id).name)}</th>${m[i].map((v, j) => {
    if (j >= i) return `<td>${i === j ? '<span class="muted">·</span>' : ""}</td>`;
    const a = Math.abs(v ?? 0);
    return `<td style="background:color-mix(in srgb, ${a >= .8 ? "var(--flag)" : "var(--ink)"} ${Math.round(a * 60)}%, var(--bg));color:${a > .45 ? "var(--bg)" : "var(--ink)"}">${v == null ? "–" : v.toFixed(2)}</td>`;
  }).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function chartSectorStrip(bySector) {
  const names = Object.keys(bySector).sort((a, b) => median(bySector[b]) - median(bySector[a]));
  const all = Object.values(bySector).flat();
  const lo = Math.min(...all, 0), hi = Math.max(...all, 1);
  const W = 720, rowH = 26, L = 180, R = 20, T = 6, H = T + names.length * rowH + 28, x = sc(lo, hi, L, W - R);
  let g = "";
  for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4; g += `<line class="grid" x1="${x(v)}" x2="${x(v)}" y1="${T}" y2="${H - 24}"/><text x="${x(v)}" y="${H - 8}" text-anchor="middle">${v.toFixed(2)}</text>`; }
  names.forEach((n, i) => {
    const cy = T + i * rowH + rowH / 2;
    g += `<text class="strong" x="${L - 12}" y="${cy + 4}" text-anchor="end">${esc(n)}</text>`;
    bySector[n].forEach((v, k) => g += `<circle class="dot" style="fill:var(--env)" cx="${x(v)}" cy="${cy + (k * 7) % 11 - 5}" r="3"/>`);
    g += `<line class="med" x1="${x(median(bySector[n]))}" x2="${x(median(bySector[n]))}" y1="${cy - 9}" y2="${cy + 9}"/>`;
  });
  return svg(W, H, g, "Sector distribution of the most tie-heavy indicator");
}
function median(a) { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; }

function chartScatter(xs, ys, label) {
  const W = 320, H = 320, L = 40, R = 12, T = 12, B = 34;
  const all = [...xs, ...ys], lo = Math.min(...all, -0.1), hi = Math.max(...all, 0.5);
  const x = sc(lo, hi, L, W - R), y = sc(lo, hi, H - B, T);
  let g = `<line class="axis" x1="${x(lo)}" y1="${y(hi)}" x2="${x(hi)}" y2="${y(lo)}" style="stroke:var(--rule)"/>`;
  xs.forEach((v, i) => g += `<circle class="dot" style="fill:var(--ink)" cx="${x(v)}" cy="${y(ys[i])}" r="3"/>`);
  g += `<text x="${L}" y="${H - 6}">${label}</text>`;
  return svg(W, H, g, label);
}

const EX = [
  { id: "A", checks: ["traceability"], title: "Every value points to a document" },
  { id: "B", checks: ["agent_quote_verify"], title: "The numbers are in the filings" },
  { id: "C", checks: ["cross_source_tax"], title: "Recomputed independently, same result" },
  { id: "D", checks: ["plausibility"], title: "Outliers are real, not errors" },
  { id: "E", checks: ["stability"], title: "Company traits persist over time" },
  { id: "F", checks: ["redundancy", "sector_pattern"], title: "No two indicators measure the same thing" },
];

function exhibitStatus(ex) {
  const cs = ex.checks.map(check).filter(Boolean);
  if (cs.every(c => c.status === "not_run")) return "not_run";
  if (cs.some(c => c.status === "flagged")) return "flagged";
  return "passed";
}

function renderIndex() {
  $("#index").innerHTML = EX.map(e => {
    const s = exhibitStatus(e);
    return `<li><button type="button" data-ex="${e.id}" aria-current="${state.ex === e.id}"><span class="ex">${e.id}</span><span class="t">${esc(e.title)}</span><span class="st ${s}">${statusLabel(s)}</span></button></li>`;
  }).join("");
  $$("#index button").forEach(b => b.onclick = () => { state.ex = b.dataset.ex; renderIndex(); renderExhibit(); });
}

function renderExhibit() {
  const e = EX.find(x => x.id === state.ex);
  const cs = e.checks.map(check).filter(Boolean);
  const s = exhibitStatus(e);
  let verdict = cs.map(c => c.verdict).filter(v => v && v !== "Not run yet.").join(" ") || "Not run yet.";
  let body = "";

  if (e.id === "A") {
    const c = check("traceability");
    body = c.status === "not_run" ? pending("Counts every value's source link.", "python run.py verify traceability")
      : `<figure class="fig">${chartSourced(c.numbers.per_indicator || [])}<figcaption>Companies with a sourced value, per indicator. Colour = category.</figcaption></figure>
         ${c.rows.length ? `<div class="outs">${c.rows.map(r => `<div><span class="mono">${esc(r.indicator_id)}</span><span></span><span>${esc(r.detail)}</span></div>`).join("")}</div>` : ""}`;
  } else if (e.id === "B") {
    const c = check("agent_quote_verify");
    if (!c || c.status === "not_run") {
      body = `<figure class="fig">${pending("An agent re-reads each filing and checks the value against the document, independently of how we extracted it.", "python run.py verify agent_quote_verify")}
        <figcaption>Needs ANTHROPIC_API_KEY in .env - not committed. Without it this exhibit stays “not run”.</figcaption></figure>`;
    } else {
      const examples = c.rows.slice(0, 3);
      body = `<figure class="fig">${examples.map(r => `<div class="quote"><div><span class="mono">${esc(r.ticker)} · FY ${r.year}</span><span class="n">${fmtVal(r.value, "")}</span><span class="muted">in our data</span></div>
        <q>${esc((r.quote || "").slice(0, 220))}</q><div><a href="${esc(r.url)}" target="_blank" rel="noopener">source ↗</a><br><span class="st ${r.detail === "confirmed" ? "pass" : "flag"}">${esc(r.detail)}</span></div></div>`).join("")}
        <figcaption>${c.numbers.sampled} values sampled (fixed seed), ${c.numbers.confirmed} confirmed.</figcaption></figure>`;
    }
  } else if (e.id === "C") {
    const c = check("cross_source_tax");
    body = !c || c.status === "not_run" ? pending("Compares our effective tax rate to the rate the company reports in XBRL.", "python run.py verify cross_source_tax")
      : `<div class="fig" style="display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr))">
          ${chartScatter(c.numbers.ours || [], c.numbers.theirs || [], "our rate vs. XBRL rate")}
          ${pending("A second agent extracts headcount from the 10-K without seeing ours.", "not built yet - see docs/DASHBOARD.md build order step 4")}
        </div>`;
  } else if (e.id === "D") {
    const c = check("plausibility");
    body = !c || c.status === "not_run" ? pending("Flags future years, unusual year-over-year changes and 3x-IQR outliers.", "python run.py verify plausibility")
      : `<figure class="fig">${chartOutlierCounts(c.rows)}<figcaption>Flagged rows per indicator. Each fence is relative to that indicator's own distribution, not a universal threshold - some are real, expected patterns (e.g. election-cycle swings in political spending), not errors; that classification is what agent_outlier_explain (not built yet) would add.</figcaption></figure>
         <div class="outs">${c.rows.slice(0, 60).map(r => `<div><span class="mono">${esc(r.ticker)}</span><span class="num">${fmtVal(r.value, "")}</span><span>${esc(r.detail)}</span></div>`).join("")}</div>`;
  } else if (e.id === "E") {
    const c = check("stability");
    body = !c || c.status === "not_run" ? pending("Year-to-year rank correlation per indicator.", "python run.py verify stability")
      : `<figure class="fig">${chartStability(c.numbers.series || {})}<figcaption>Rank correlation of each indicator's value with its own previous year (1 = identical order).</figcaption></figure>`;
  } else if (e.id === "F") {
    const red = check("redundancy"), sec = check("sector_pattern");
    const redBody = !red || red.status === "not_run" ? pending("Correlation between every pair of indicators.", "python run.py verify redundancy")
      : `<figure class="fig">${corrTable(red.numbers.pairs || {})}<figcaption>Rank correlation of latest values. 0.8+ would be flagged as a likely duplicate.</figcaption></figure>`;
    const secBody = !sec || sec.status === "not_run" ? pending("Sector distribution of the most tie-heavy indicator.", "python run.py verify sector_pattern")
      : `<figure class="fig" style="margin-top:32px">${chartSectorStrip(sec.numbers.by_sector || {})}<figcaption>${esc(sec.verdict)}</figcaption></figure>`;
    body = redBody + secBody;
  }

  const method = cs.map(c => `<code>python run.py verify ${c.id}</code>`).join(" · ") || "not built yet";
  const kinds = [...new Set(cs.map(c => c.kind))].join(" + ") || "planned";
  $("#exhibit").innerHTML = `<div class="kicker"><span class="label">Exhibit ${e.id}</span><span class="tag">${kinds}</span><span class="st ${s}">${statusLabel(s)}</span></div>
    <h3>${esc(e.title)}</h3><p class="verdict"><mark>${esc(verdict)}</mark></p>${body}
    <details class="method"><summary>How this is checked</summary><p>${method}</p></details>`;
}

/* ---------- boot ---------- */
async function init() {
  bindTabs();
  state.meta = await getJSON("/api/meta");
  state.checks = await getJSON("/api/checks");
  const def = state.meta.profiles.find(p => p.id === state.meta.default_profile) || state.meta.profiles[0];
  state.profileId = def.id;
  state.categoryWeights = { ...def.category_weights };

  $("#profile").innerHTML = state.meta.profiles.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
  $("#profile").value = state.profileId;
  $("#profile").addEventListener("change", async e => {
    state.profileId = e.target.value;
    const p = state.meta.profiles.find(x => x.id === state.profileId);
    state.categoryWeights = { ...p.category_weights };
    renderWeights();
    await loadScore();
  });
  $("#sector").innerHTML = `<option value="">All sectors</option>` + state.meta.sectors.map(s => `<option>${esc(s)}</option>`).join("");
  $("#sector").onchange = e => { state.sector = e.target.value; renderRows(); };
  $("#q").oninput = e => { state.q = e.target.value; renderRows(); };
  $("#more").onclick = () => { state.limit += 100000; renderRows(); };

  renderWeights();
  await loadScore();
  $("#summary").textContent = `${state.score.scored} of ${state.meta.companies} companies scored · ${state.meta.indicators.length} indicators in three categories · every value links to a public document. Data retrieved ${state.meta.retrieved || "–"}.`;
  $("#legend").innerHTML = `<span>Fingerprint: one bar per indicator, height = points (0–100), hatched = no data.</span>` + CATS.map(([, n, c]) => `<span><span class="sw" style="background:var(${c})"></span>${n}</span>`).join("");
}

init();
