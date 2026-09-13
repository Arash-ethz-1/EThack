/* S&P 500 Sustainability - dashboard/static/app.js
   Start page (pillar weights + which indicators) -> pipeline (each step a real server call) -> results.
   Only displays. Scores come from POST /api/score (common/score.py), the fund from
   /api/portfolio (portfolio/allocate.py), evidence from /api/evidence (checks/*.py run live on
   the chosen weights), the net-zero answer from /api/netzero (portfolio/transition.py).
   Nothing here ranks, scores or calls a model. */

const CATS = [["economic", "Economic", "--econ"], ["social", "Social", "--soc"], ["environmental", "Environmental", "--env"]];
const HOME_ORDER = [["environmental", "Planet"], ["social", "People"], ["economic", "Economic base"]];
const SHORT = {
  tax_rate_gap: "Tax paid", revenue_volatility: "Stable revenue", employment_growth: "Job growth",
  federal_contract_exposure: "Gov. dependence", median_worker_pay: "Worker pay",
  labor_litigation_intensity: "Worker lawsuits", political_alignment: "Political money", shareholder_payout_ratio: "Payouts",
  ceo_pay_ratio: "CEO pay gap", employer_retirement_contribution: "Retirement", human_capital_disclosure: "Workforce reporting",
  workplace_injury_rate: "Injuries", resource_supply_risk: "Scarce materials", ghg_intensity: "Emissions",
  sbti_climate_target: "Climate target", epa_penalty_intensity: "EPA fines", critical_material_disclosure: "Materials reporting",
};
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const f1 = v => v == null ? '<span class="muted">–</span>' : v.toFixed(1);
const isNum = v => typeof v === "number" && Number.isFinite(v);
const fmtVal = (v, unit) => v == null ? "–" : unit === "pct_points" ? (v * 100).toFixed(1) + " pp" : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-US") : String(+v.toFixed(3));
const signed = (v, d = 1) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(d);
const short = id => SHORT[id] || (state.meta.indicators.find(m => m.id === id) || {}).name || id;

const state = {
  meta: null, profileId: "balanced", categoryWeights: { economic: 1, social: 1, environmental: 1 }, off: new Set(),
  score: null, checks: null, evidence: {}, netzero: null, q: "", sector: "", limit: 50, ex: "A", view: "ranking",
};

async function getJSON(path) { const r = await fetch(path); return r.json(); }
async function postJSON(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-EThack": "1" }, body: JSON.stringify(body) });
  return r.json();
}
const body = extra => ({
  profile: state.profileId, category_weights: state.categoryWeights,
  indicator_weights: Object.fromEntries([...state.off].map(id => [id, 0])), ...extra,
});
function META(id) { return (state.meta.indicators.find(m => m.id === id)) || { name: id, category: "" }; }
function colOf(id) { const m = META(id); return `var(${(CATS.find(c => c[0] === m.category) || CATS[0])[2]})`; }
function weightsText() {
  return HOME_ORDER.map(([id, n]) => `${n} ${state.categoryWeights[id] || 0}`).join(" · ")
    + (state.off.size ? ` · ${state.meta.indicators.length - state.off.size}/${state.meta.indicators.length} indicators` : "")
    + (state.profileId === "net_zero" ? " · net-zero emphasis" : "");
}

/* ---------- 1. start page ---------- */
function renderChoose() {
  const w = state.categoryWeights, sum = Object.values(w).reduce((a, b) => a + b, 0) || 1;
  $("#choose").innerHTML = HOME_ORDER.map(([id, name]) => {
    const col = CATS.find(c => c[0] === id)[2];
    const inds = state.meta.indicators.filter(m => m.category === id), on = inds.filter(m => !state.off.has(m.id)).length;
    return `<div class="pick ${w[id] ? "" : "zero"}">
      <div class="pick-t"><span class="sw" style="background:var(${col})"></span><b>${name}</b><span class="pick-n num">${on}/${inds.length}</span></div>
      <div class="pick-c" role="radiogroup" aria-label="${name} weight">${[0, 1, 2, 3].map(k =>
        `<button type="button" role="radio" data-id="${id}" data-k="${k}" aria-checked="${w[id] === k}">${k}</button>`).join("")}</div>
      <div class="pick-share"><span class="pick-bar"><i style="width:${(w[id] / sum * 100).toFixed(1)}%;background:var(${col})"></i></span><span class="num">${Math.round(w[id] / sum * 100)}%</span></div>
      <div class="pick-i">${inds.map(m => `<button type="button" data-ind="${m.id}" data-cat="${id}" aria-pressed="${!state.off.has(m.id)}" title="${esc(m.name)}">${esc(short(m.id))}</button>`).join("")}</div>
    </div>`;
  }).join("") + `<div class="emph"><span class="label">Emphasis</span>
      <div class="seg" role="radiogroup" aria-label="Indicator emphasis">
        <button type="button" role="radio" data-p="balanced" aria-checked="${state.profileId === "balanced"}">Equal</button>
        <button type="button" role="radio" data-p="net_zero" aria-checked="${state.profileId === "net_zero"}" title="Emissions and climate targets count 3×">Net zero</button>
      </div></div>`;
  $$("#choose .pick-c button").forEach(b => b.onclick = () => {
    const next = { ...state.categoryWeights, [b.dataset.id]: +b.dataset.k };
    if (Object.values(next).every(x => !x)) return;
    if (+b.dataset.k > 0) state.meta.indicators.filter(m => m.category === b.dataset.id).forEach(m => state.off.delete(m.id));
    state.categoryWeights = next; renderChoose();
  });
  $$("#choose .pick-i button").forEach(b => b.onclick = () => {
    const id = b.dataset.ind, cat = b.dataset.cat;
    if (state.off.has(id)) { state.off.delete(id); if (!state.categoryWeights[cat]) state.categoryWeights = { ...state.categoryWeights, [cat]: 1 }; }
    else {
      const left = state.meta.indicators.filter(m => m.category === cat && !state.off.has(m.id) && m.id !== id).length;
      const others = Object.entries(state.categoryWeights).some(([c, x]) => c !== cat && x > 0);
      if (!left && !others) return;  // something has to count
      state.off.add(id);
      if (!left) state.categoryWeights = { ...state.categoryWeights, [cat]: 0 };
    }
    renderChoose();
  });
  $$("#choose .emph button").forEach(b => b.onclick = () => {
    state.profileId = b.dataset.p;
    const p = state.meta.profiles.find(x => x.id === state.profileId);
    if (p) state.categoryWeights = { ...p.category_weights };
    renderChoose();
  });
}

function show(screen) {
  $("#home").hidden = screen !== "home";
  $("#run").hidden = screen !== "run";
  $("#app").hidden = screen !== "app";
  window.scrollTo(0, 0);
}

/* ---------- 2. the pipeline: every line is a real server call, timed ---------- */
const STEPS = [
  { label: "Score every company against its sector", run: async () => {
      state.score = await postJSON("/api/score", body());
      if (state.score.error) throw new Error(state.score.error);
      const top = state.score.rows[0];
      return `${state.score.scored} scored · #1 ${esc(top.name)} ${top.total_score.toFixed(1)}`;
    } },
  { label: "Build a $1 billion fund", run: async () => {
      PF.settings = {}; PF.data = await postJSON("/api/portfolio", body({ settings: {} }));
      if (PF.data.error) { const e = PF.data.error; PF.data = null; throw new Error(e); }
      const t = PF.data.summary.scores.total_score, c = PF.data.summary.climate.waci_tco2e_per_musd;
      return `${signed(t.portfolio - t.benchmark)} points · ${signed((c.portfolio / c.benchmark - 1) * 100, 0)}% carbon vs the index`;
    } },
  { label: "Replay 2021 against later EPA fines", run: async () => {
      const r = state.evidence.caught_later = await postJSON("/api/evidence", body({ check: "caught_later" }));
      if (r.error) throw new Error(r.error);
      const q = r.numbers.total_score;
      return `worst fifth fined ${Math.round(q[0].share * 100)}% · best fifth ${Math.round(q[q.length - 1].share * 100)}%`;
    } },
  { label: "Try 1,000 other weightings", run: async () => {
      const r = state.evidence.weight_robustness = await postJSON("/api/evidence", body({ check: "weight_robustness" }));
      if (r.error) throw new Error(r.error);
      return `rank correlation ${r.numbers.median_rho.toFixed(2)} · ranking holds`;
    } },
  { label: "Put a price on carbon", run: async () => {
      const r = state.netzero = await postJSON("/api/netzero", {});
      if (r.error) throw new Error(r.error);
      const at = r.stress.curve.find(p => p.price === r.stress.reference["2030"]);
      return `$${at.price}/t takes ${(at.fund * 100).toFixed(1)}% of profit · index ${(at.index * 100).toFixed(1)}%`;
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
  state.meta.indicators.filter(m => !state.off.has(m.id)).forEach(m => {
    if (prev && m.category !== prev) out += `<i class="sp"></i>`;
    prev = m.category;
    const pts = fp[m.id];
    out += pts != null
      ? `<i title="${esc(short(m.id))}: ${pts}"><b style="height:${Math.max(1, pts * .2)}px;background:${colOf(m.id)}"></b></i>`
      : `<i class="gap" title="${esc(short(m.id))}: no data"></i>`;
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
      <td class="r num">${f1(r.environmental_score)}</td><td class="r num">${f1(r.social_score)}</td><td class="r num">${f1(r.economic_score)}</td>
      <td class="r tot num">${f1(r.total_score)}</td></tr>`).join("");
  $("#more").hidden = rows.length <= state.limit;
  $("#more").textContent = `Show all ${rows.length}`;
  $$("#rows tr").forEach(tr => { tr.onclick = () => openCompany(tr.dataset.t); tr.onkeydown = e => e.key === "Enter" && openCompany(tr.dataset.t); });
}

function renderOverview() {
  const fig = (go_, label, value, text) => `<button type="button" class="fig-n" data-go="${go_}"><span class="label">${label}</span><span class="v num">${value}</span><span class="t">${text}</span></button>`;
  const pf = PF.data, a = state.evidence.caught_later, b = state.evidence.weight_robustness, nz = state.netzero;
  const t = pf ? pf.summary.scores.total_score : null, c = pf ? pf.summary.climate.waci_tco2e_per_musd : null;
  const at = nz && !nz.error ? nz.stress.curve.find(p => p.price === nz.stress.reference["2030"]) : null;
  $("#overview").innerHTML = [
    fig("portfolio", "Fund", t ? signed(t.portfolio - t.benchmark) : "–", "points vs index"),
    fig("portfolio", "Carbon", c && c.benchmark ? `${signed((c.portfolio / c.benchmark - 1) * 100, 0)}%` : "–", "intensity vs index"),
    fig("netzero", "Carbon price", at ? `${(at.fund * 100).toFixed(1)}%` : "–", at ? `profit hit at $${at.price}/t · index ${(at.index * 100).toFixed(1)}%` : ""),
    fig("evidence/A", "Caught later", a && a.numbers && a.numbers.worst_to_best_ratio ? `${a.numbers.worst_to_best_ratio.toFixed(1)}×` : "–", "EPA fines, worst vs best"),
    fig("evidence/B", "Robust", b && b.numbers ? b.numbers.median_rho.toFixed(2) : "–", "1,000 other weightings"),
  ].join("");
  $$("#overview .fig-n").forEach(x => x.onclick = () => { const [v, s] = x.dataset.go.split("/"); go(v, s); });
  $("#legend").innerHTML = HOME_ORDER.map(([id, n]) => `<span><span class="sw" style="background:var(${CATS.find(c => c[0] === id)[2]})"></span>${n}</span>`).join("") + `<span>bar height = rank in sector · hatched = no data</span>`;
}

/* ---------- company drawer ---------- */
async function openCompany(ticker) {
  const detail = await postJSON("/api/explain", body({ ticker }));
  const c = detail.company;
  const rows = detail.indicators.map(x => `<tr>
      <td><span class="sw" style="background:${colOf(x.indicator_id)}"></span>${esc(short(x.indicator_id))}</td>
      <td class="r num">${fmtVal(x.value, x.unit)}</td>
      <td class="bar-c"><span class="hbar"><i style="width:${x.rank != null ? Math.round(x.rank * 100) : 0}%;background:${colOf(x.indicator_id)}"></i></span></td>
      <td class="r num">${x.rank != null ? Math.round(x.rank * 100) : "–"}</td>
      <td class="r">${x.source_url ? `<a href="${esc(x.source_url)}" target="_blank" rel="noopener" title="${esc(x.source || "source")}">↗</a>` : ""}</td></tr>`).join("");
  $("#drawer").innerHTML = `<header><div><p class="eyebrow">${c.ticker} · ${esc(c.sector || "")}</p><h2>${esc(c.name || c.ticker)}</h2></div>
      <button type="button" class="ghost" id="close" aria-label="Close">✕</button></header>
    <div class="scores">${[["total", "Total", null], ...HOME_ORDER.map(([id, n]) => [id, n, CATS.find(k => k[0] === id)[2]])].map(([id, n, col]) => `<div><span class="label">${col ? `<span class="sw" style="background:var(${col})"></span>` : ""}${n}</span><span class="v num">${f1(c[`${id}_score`])}</span></div>`).join("")}</div>
    <div class="drawer-actions"><button type="button" class="ghost" id="trace-co">How it's calculated →</button><button type="button" class="ghost" id="audit-co">Audit →</button></div>
    <table class="ledger"><thead><tr><th>Indicator</th><th class="r">Value</th><th>Rank in sector</th><th></th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
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
  $("#sector").innerHTML = `<option value="">All sectors</option>` + state.meta.sectors.map(s => `<option>${esc(s)}</option>`).join("");
  $("#sector").onchange = e => { state.sector = e.target.value; renderRows(); };
  $("#q").oninput = e => { state.q = e.target.value; renderRows(); };
  $("#more").onclick = () => { state.limit += 100000; renderRows(); };
  renderChoose();

  // deep links for the pitch (#netzero, #portfolio, #evidence/B, #evidence/C/NUE, #method/NUE): run with defaults, then open
  const [view, sub, ticker] = location.hash.slice(1).split("/");
  if (["ranking", "portfolio", "netzero", "evidence", "method"].includes(view)) {
    if (view === "evidence" && sub) state.ex = sub.toUpperCase();
    if (view === "method" && sub) TRACE.ticker = sub.toUpperCase();
    await compute(view);
    if (view === "evidence" && ticker) runAudit(ticker.toUpperCase());
  } else show("home");
}

init();
