/* S&P 500 Sustainability - dashboard/static/app.js
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
    $("#view-method").hidden = b.dataset.view !== "method";
    if (b.dataset.view === "portfolio") renderPortfolio();
    if (b.dataset.view === "evidence") { renderIndex(); renderExhibit(); }
    if (b.dataset.view === "method") renderMethod();
    history.replaceState(null, "", b.dataset.view === "ranking" ? location.pathname : "#" + b.dataset.view);
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
  if (typeof PF !== "undefined") { PF.data = null; if (!$("#view-portfolio").hidden) loadPortfolio(); }
  if (state.checks) renderOverview();
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
  $("#drawer").innerHTML = `<header><div><span class="label mono">${c.ticker} · ${esc(c.sector || "")}</span><h2>${esc(c.name || c.ticker)}</h2></div><div class="tools"><button type="button" class="btn" id="audit-co">Audit this company</button><button type="button" class="btn" id="close">Close</button></div></header>
    <div class="score-line"><div><span class="label">Total</span><span class="v">${f1(c.total_score)}</span></div>${CATS.map(([id, n, col]) => `<div><span class="label"><span class="sw" style="background:var(${col})"></span>${n}</span><span class="v">${f1(c[`${id}_score`])}</span></div>`).join("")}</div>
    <div class="chain-h"><h3>Chain of evidence</h3><span class="muted" style="font-size:12px">Line width = points</span></div>
    ${flow(ticker, cats, detail.indicators)}
    <div class="ledger">${rows || '<p class="muted">No ready indicator has a value for this company.</p>'}</div>`;
  $("#drawer").hidden = $("#scrim").hidden = false; $("#close").onclick = closeCompany; $("#close").focus();
  $("#audit-co").onclick = () => { closeCompany(); state.ex = "C"; $('nav.tabs button[data-view="evidence"]').click(); runAudit(ticker); };
}
function closeCompany() { $("#drawer").hidden = $("#scrim").hidden = true; }
$("#scrim").onclick = closeCompany;
document.addEventListener("keydown", e => e.key === "Escape" && closeCompany());

/* ---------- portfolio: see portfolio.js ---------- */

/* ---------- overview strip: headline results, each a door into its tab ---------- */
async function renderOverview() {
  const el = $("#overview");
  const chk = id => (state.checks.checks || []).find(c => c.id === id);
  const a = chk("caught_later"), b = chk("weight_robustness");
  const tile = (view, label, value, text) => `<button type="button" class="ov" data-go="${view}"><span class="label">${label}</span><span class="v">${value}</span><span class="t">${text}</span></button>`;
  const draw = pf => {
    const c = pf && pf.summary ? pf.summary.climate : null, t = pf && pf.summary ? pf.summary.scores.total_score : null;
    const cut = c && c.waci_tco2e_per_musd.benchmark ? 1 - c.waci_tco2e_per_musd.portfolio / c.waci_tco2e_per_musd.benchmark : null;
    el.innerHTML = [
      tile("portfolio", "Our fund vs the index", t ? `+${(t.portfolio - t.benchmark).toFixed(1)}` : "…", "sustainability points, sector mix unchanged"),
      tile("portfolio", "Carbon intensity", cut != null ? `−${Math.round(cut * 100)}%` : "…", "tCO₂e per $M revenue vs the index"),
      tile("evidence/A", "Low scores get caught", a && a.numbers.worst_to_best_ratio ? `${a.numbers.worst_to_best_ratio.toFixed(1)}×` : "–", "more EPA fines for the worst-rated fifth, 2022–25"),
      tile("evidence/B", "Robust to weights", b && b.numbers.median_rho ? b.numbers.median_rho.toFixed(2) : "–", "rank correlation across 1,000 random weightings"),
    ].join("");
    $$("#overview .ov").forEach(x => x.onclick = () => {
      const [view, sub] = x.dataset.go.split("/");
      if (sub) state.ex = sub;
      $(`nav.tabs button[data-view="${view}"]`).click();
    });
  };
  draw(null);
  const pf = await postJSON("/api/portfolio", { profile: state.profileId, category_weights: state.categoryWeights });
  if (!pf.error) draw(pf);
}

/* ---------- evidence: see evidence.js ---------- */

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
  const [view, sub, auditTicker] = location.hash.slice(1).split("/");  // #portfolio, #evidence/B, #evidence/C/AAPL
  if (view === "evidence" && sub) state.ex = sub.toUpperCase();
  const deep = $(`nav.tabs button[data-view="${view}"]`);
  if (deep) deep.click();
  if (view === "evidence" && auditTicker && typeof runAudit === "function") runAudit(auditTicker.toUpperCase());
  $("#legend").innerHTML = `<span>Fingerprint: one bar per indicator, height = points (0–100), hatched = no data.</span>` + CATS.map(([, n, c]) => `<span><span class="sw" style="background:var(${c})"></span>${n}</span>`).join("");
}

init();
