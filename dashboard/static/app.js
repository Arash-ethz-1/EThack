/* S&P 500 Sustainability - dashboard/static/app.js
   Start page (weights) -> pipeline (each step a real server call) -> results.
   Only displays. Scores come from POST /api/score (common/score.py), the fund from
   /api/portfolio (portfolio/allocate.py), evidence from /api/evidence (checks/*.py run live on
   the chosen weights), the net-zero answer from /api/netzero (portfolio/transition.py).
   Nothing here ranks, scores or calls a model. */

const CATS = [["economic", "Economic", "--econ"], ["social", "Social", "--soc"], ["environmental", "Environmental", "--env"]];
const HOME_ORDER = [
  ["environmental", "Planet", "Emissions, pollution fines, climate targets, scarce materials"],
  ["social", "People", "Pay fairness, lawsuits by workers, retirement, how people are counted"],
  ["economic", "Economic base", "Tax, stable revenue, jobs, dependence on government contracts"],
];
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const f1 = v => v == null ? '<span class="muted">–</span>' : v.toFixed(1);
const isNum = v => typeof v === "number" && Number.isFinite(v);
const fmtVal = (v, unit) => v == null ? "–" : unit === "pct_points" ? (v * 100).toFixed(1) + " pp" : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-US") : String(+v.toFixed(3));
const signed = (v, d = 1) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(d);

const state = {
  meta: null, profileId: "balanced", categoryWeights: { economic: 1, social: 1, environmental: 1 },
  score: null, checks: null, evidence: {}, netzero: null, q: "", sector: "", limit: 50, ex: "A", view: "ranking",
};

async function getJSON(path) { const r = await fetch(path); return r.json(); }
async function postJSON(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-EThack": "1" }, body: JSON.stringify(body) });
  return r.json();
}
const body = extra => ({ profile: state.profileId, category_weights: state.categoryWeights, ...extra });
function META(id) { return (state.meta.indicators.find(m => m.id === id)) || { name: id, category: "" }; }
function colOf(id) { const m = META(id); return `var(${(CATS.find(c => c[0] === m.category) || CATS[0])[2]})`; }
function weightsText() {
  return HOME_ORDER.map(([id, n]) => `${n} ${state.categoryWeights[id] || 0}`).join(" · ") + (state.profileId === "net_zero" ? " · net-zero emphasis" : "");
}

/* ---------- 1. start page ---------- */
function renderChoose() {
  const w = state.categoryWeights, sum = Object.values(w).reduce((a, b) => a + b, 0) || 1;
  $("#choose").innerHTML = HOME_ORDER.map(([id, name, what]) => {
    const col = CATS.find(c => c[0] === id)[2];
    return `<div class="pick">
      <div class="pick-t"><span class="sw" style="background:var(${col})"></span><b>${name}</b><span class="pick-what">${what}</span></div>
      <div class="pick-c" role="radiogroup" aria-label="${name} weight">${[0, 1, 2, 3].map(k =>
        `<button type="button" role="radio" data-id="${id}" data-k="${k}" aria-checked="${w[id] === k}">${k}</button>`).join("")}</div>
      <div class="pick-share"><span class="pick-bar"><i style="width:${(w[id] / sum * 100).toFixed(1)}%;background:var(${col})"></i></span><span class="num">${Math.round(w[id] / sum * 100)}%</span></div>
    </div>`;
  }).join("") + `<div class="emph"><span class="label">Indicator weights</span>
      <div class="seg" role="radiogroup" aria-label="Indicator weights">
        <button type="button" role="radio" data-p="balanced" aria-checked="${state.profileId === "balanced"}">Equal</button>
        <button type="button" role="radio" data-p="net_zero" aria-checked="${state.profileId === "net_zero"}">Net-zero emphasis</button>
      </div>
      <span class="emph-note">${state.profileId === "net_zero" ? "emissions and science-based targets count three times" : "every indicator counts the same inside its pillar"}</span></div>`;
  $$("#choose .pick-c button").forEach(b => b.onclick = () => {
    const next = { ...state.categoryWeights, [b.dataset.id]: +b.dataset.k };
    if (Object.values(next).every(x => !x)) return;
    state.categoryWeights = next; renderChoose();
  });
  $$("#choose .emph button").forEach(b => b.onclick = () => {
    state.profileId = b.dataset.p;
    const p = state.meta.profiles.find(x => x.id === state.profileId);
    if (p) state.categoryWeights = { ...p.category_weights };
    renderChoose();
  });
  $("#go").disabled = false;
}

function show(screen) {
  $("#home").hidden = screen !== "home";
  $("#run").hidden = screen !== "run";
  $("#app").hidden = screen !== "app";
  window.scrollTo(0, 0);
}

/* ---------- 2. the pipeline: every line is a real server call, timed ---------- */
const STEPS = [
  { label: "Rank every company against its own sector, indicator by indicator, and combine the ranks into scores", run: async () => {
      state.score = await postJSON("/api/score", body());
      if (state.score.error) throw new Error(state.score.error);
      const top = state.score.rows[0];
      return `${state.score.scored} companies scored on ${state.meta.indicators.length} indicators · highest: ${esc(top.name)} ${top.total_score.toFixed(1)}`;
    } },
  { label: "Build a $1 billion fund: drop fossil fuels and tobacco, tilt every weight by the score", run: async () => {
      PF.settings = {}; PF.data = await postJSON("/api/portfolio", body({ settings: {} }));
      if (PF.data.error) { const e = PF.data.error; PF.data = null; throw new Error(e); }
      const t = PF.data.summary.scores.total_score, c = PF.data.summary.climate.waci_tco2e_per_musd;
      return `${PF.data.summary.holdings} holdings · ${signed(t.portfolio - t.benchmark)} points vs the index · carbon intensity ${signed((c.portfolio / c.benchmark - 1) * 100, 0)}%`;
    } },
  { label: "Go back to 2021: score with only the data known then, and compare with the EPA fines that came after", run: async () => {
      const r = state.evidence.caught_later = await postJSON("/api/evidence", body({ check: "caught_later" }));
      if (r.error) throw new Error(r.error);
      const q = r.numbers.total_score;
      return `worst-rated fifth fined ${Math.round(q[0].share * 100)}%, best fifth ${Math.round(q[q.length - 1].share * 100)}%` + (r.numbers.worst_to_best_ratio ? ` · ${r.numbers.worst_to_best_ratio.toFixed(1)}×` : "");
    } },
  { label: "Re-rank all companies under 1,000 random weightings", run: async () => {
      const r = state.evidence.weight_robustness = await postJSON("/api/evidence", body({ check: "weight_robustness" }));
      if (r.error) throw new Error(r.error);
      return `median rank correlation with yours ${r.numbers.median_rho.toFixed(2)} · ${Math.round(r.numbers.top50_stay_share * 100)}% of the top 50 stay on top`;
    } },
  { label: "Net zero tomorrow: stress the fund with a carbon price", run: async () => {
      const r = state.netzero = await postJSON("/api/netzero", {});
      if (r.error) throw new Error(r.error);
      const at = r.stress.curve.find(p => p.price === r.stress.reference["2030"]);
      return `at $${at.price}/t a carbon bill takes ${(at.fund * 100).toFixed(1)}% of profit in the net-zero fund, ${(at.index * 100).toFixed(1)}% in the index`;
    } },
];

async function compute(thenView) {
  show("run");
  $("#run-weights").textContent = weightsText();
  $("#see").hidden = true;
  PF.data = null; state.evidence = {}; AUD.data = null; AUD.ticker = null; TRACE.data = null;
  $("#steps").innerHTML = STEPS.map((s, i) => `<li data-i="${i}" class="wait"><span class="n num">${String(i + 1).padStart(2, "0")}</span>
    <div><p class="s-l">${s.label}</p><p class="s-r"></p></div><span class="s-t num"></span></li>`).join("");
  for (let i = 0; i < STEPS.length; i++) {
    const li = $(`#steps li[data-i="${i}"]`), t0 = performance.now();
    li.className = "busy";
    const tick = setInterval(() => li.querySelector(".s-t").textContent = ((performance.now() - t0) / 1000).toFixed(1) + " s", 100);
    try {
      li.querySelector(".s-r").innerHTML = await STEPS[i].run();
      li.className = "done";
    } catch (e) {
      li.querySelector(".s-r").textContent = "failed: " + e.message;
      li.className = "fail";
    }
    clearInterval(tick);
    li.querySelector(".s-t").textContent = ((performance.now() - t0) / 1000).toFixed(1) + " s";
  }
  $("#see").hidden = false;
  $("#see").focus();
  $("#see").onclick = () => openApp(thenView || "ranking");
  if (thenView) openApp(thenView);
}

/* ---------- 3. results ---------- */
function openApp(view) {
  show("app");
  $("#weights-chip").textContent = weightsText();
  $("#summary").textContent = `${state.score.scored} of ${state.meta.companies} companies scored on ${state.meta.indicators.length} indicators from SEC filings, the EPA, the Department of Labor and the Science Based Targets initiative. A company is ranked only against its own GICS sector; values from 2022 on. Data retrieved ${state.meta.retrieved || "–"}.`;
  renderOverview();
  renderRows();
  go(view);
}

function go(view, sub) {
  state.view = view;
  $$("nav.tabs button").forEach(x => x.setAttribute("aria-selected", String(x.dataset.view === view)));
  ["ranking", "portfolio", "netzero", "evidence", "method"].forEach(v => $(`#view-${v}`).hidden = v !== view);
  if (view === "portfolio") renderPortfolio();
  if (view === "netzero") renderNetZero();
  if (view === "evidence") { if (sub) state.ex = sub; renderEvidence(); }
  if (view === "method") renderMethod();
  history.replaceState(null, "", "#" + view + (view === "evidence" ? "/" + state.ex : ""));
  window.scrollTo(0, 0);
}

function bindChrome() {
  $$("nav.tabs button").forEach(b => b.onclick = () => go(b.dataset.view));
  $("#home-link").onclick = $("#weights-chip").onclick = () => { renderChoose(); show("home"); history.replaceState(null, "", location.pathname); };
  $("#go").onclick = () => compute();
}

function fingerprint(ticker) {
  const fp = (state.score.fingerprints || {})[ticker] || {};
  let prev = null, out = "";
  state.meta.indicators.forEach(m => {
    if (prev && m.category !== prev) out += `<i class="sp"></i>`;
    prev = m.category;
    const pts = fp[m.id];
    out += pts != null
      ? `<i title="${esc(m.name)}: ${pts}"><b style="height:${Math.max(1, pts * .2)}px;background:${colOf(m.id)}"></b></i>`
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
      <td class="r pos num">${r.position ?? "–"}</td>
      <td class="co"><b>${esc(r.name || r.ticker)}</b><span class="tk">${r.ticker}</span></td>
      <td class="muted">${esc(r.sector || "")}</td>
      <td>${fingerprint(r.ticker)}</td>
      <td class="r num">${f1(r.economic_score)}</td><td class="r num">${f1(r.social_score)}</td><td class="r num">${f1(r.environmental_score)}</td>
      <td class="r tot num">${f1(r.total_score)}</td></tr>`).join("");
  $("#more").hidden = rows.length <= state.limit;
  $("#more").textContent = `Show all ${rows.length}`;
  $$("#rows tr").forEach(tr => { tr.onclick = () => openCompany(tr.dataset.t); tr.onkeydown = e => e.key === "Enter" && openCompany(tr.dataset.t); });
}

function renderOverview() {
  const fig = (go_, label, value, text) => `<button type="button" class="fig-n" data-go="${go_}"><span class="label">${label}</span><span class="v num">${value}</span><span class="t">${text}</span></button>`;
  const pf = PF.data, a = state.evidence.caught_later, b = state.evidence.weight_robustness;
  const t = pf ? pf.summary.scores.total_score : null, c = pf ? pf.summary.climate.waci_tco2e_per_musd : null;
  $("#overview").innerHTML = [
    fig("portfolio", "Fund vs index", t ? signed(t.portfolio - t.benchmark) : "–", "sustainability points, same sector mix"),
    fig("portfolio", "Carbon intensity", c && c.benchmark ? `${signed((c.portfolio / c.benchmark - 1) * 100, 0)}%` : "–", "tCO₂e per $M revenue, fund vs index"),
    fig("evidence/A", "Caught later", a && a.numbers && a.numbers.worst_to_best_ratio ? `${a.numbers.worst_to_best_ratio.toFixed(1)}×` : "–", "EPA fines, worst vs best fifth, 2022–25"),
    fig("evidence/B", "Robust to weights", b && b.numbers ? b.numbers.median_rho.toFixed(2) : "–", "rank correlation, 1,000 random weightings"),
  ].join("");
  $$("#overview .fig-n").forEach(x => x.onclick = () => { const [v, s] = x.dataset.go.split("/"); go(v, s); });
  $("#legend").innerHTML = `<span>Indicators: one bar per indicator, height = rank in sector, hatched = no data</span>` + CATS.map(([, n, c]) => `<span><span class="sw" style="background:var(${c})"></span>${n}</span>`).join("");
}

/* ---------- company drawer: the ledger ---------- */
async function openCompany(ticker) {
  const detail = await postJSON("/api/explain", body({ ticker }));
  const c = detail.company;
  const rows = detail.indicators.map(x => `<tr>
      <td><span class="sw" style="background:${colOf(x.indicator_id)}"></span>${esc(META(x.indicator_id).name)}<div class="sub">FY ${x.year ?? "–"} · ${x.source_url ? `<a href="${esc(x.source_url)}" target="_blank" rel="noopener">${esc(x.source || "source")} ↗</a>` : "no data"}</div></td>
      <td class="r num">${fmtVal(x.value, x.unit)}<div class="sub">${esc(x.unit || "")}</div></td>
      <td class="r num">${x.rank != null ? Math.round(x.rank * 100) : "–"}</td></tr>`).join("");
  $("#drawer").innerHTML = `<header><div><p class="eyebrow">${c.ticker} · ${esc(c.sector || "")}</p><h2>${esc(c.name || c.ticker)}</h2></div>
      <button type="button" class="ghost" id="close" aria-label="Close">Close</button></header>
    <div class="scores">${[["total", "Total", null], ...CATS].map(([id, n, col]) => `<div><span class="label">${col ? `<span class="sw" style="background:var(${col})"></span>` : ""}${n}</span><span class="v num">${f1(c[`${id}_score`])}</span></div>`).join("")}</div>
    <div class="drawer-actions"><button type="button" class="ghost" id="trace-co">See the full calculation →</button><button type="button" class="ghost" id="audit-co">Audit this company →</button></div>
    <table class="ledger"><thead><tr><th>Indicator</th><th class="r">Value</th><th class="r">Rank in sector</th></tr></thead><tbody>${rows}</tbody></table>`;
  $("#drawer").hidden = $("#scrim").hidden = false; $("#close").onclick = closeCompany; $("#close").focus();
  $("#audit-co").onclick = () => { closeCompany(); go("evidence", "C"); runAudit(ticker); };
  $("#trace-co").onclick = () => { closeCompany(); TRACE.ticker = ticker; TRACE.data = null; go("method"); };
}
function closeCompany() { $("#drawer").hidden = $("#scrim").hidden = true; }
$("#scrim").onclick = closeCompany;
document.addEventListener("keydown", e => e.key === "Escape" && closeCompany());

/* ---------- boot ---------- */
async function init() {
  bindChrome();
  state.meta = await getJSON("/api/meta");
  state.checks = await getJSON("/api/checks");
  const def = state.meta.profiles.find(p => p.id === state.meta.default_profile) || state.meta.profiles[0];
  state.profileId = def.id;
  state.categoryWeights = { ...def.category_weights };
  $("#home-foot").textContent = `${state.meta.indicators.length} indicators from SEC filings, the EPA, the Department of Labor and SBTi · every number links to its source`;
  $("#sector").innerHTML = `<option value="">All sectors</option>` + state.meta.sectors.map(s => `<option>${esc(s)}</option>`).join("");
  $("#sector").onchange = e => { state.sector = e.target.value; renderRows(); };
  $("#q").oninput = e => { state.q = e.target.value; renderRows(); };
  $("#more").onclick = () => { state.limit += 100000; renderRows(); };
  renderChoose();

  // deep links for the pitch (#portfolio, #netzero, #evidence/B, #evidence/C/NUE, #method/NUE): run with defaults, then open
  const [view, sub, ticker] = location.hash.slice(1).split("/");
  if (["ranking", "portfolio", "netzero", "evidence", "method"].includes(view)) {
    if (view === "evidence" && sub) state.ex = sub.toUpperCase();
    if (view === "method" && sub) TRACE.ticker = sub.toUpperCase();
    await compute(view);
    if (view === "evidence" && ticker) runAudit(ticker.toUpperCase());
  } else show("home");
}

init();
