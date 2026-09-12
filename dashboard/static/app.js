/* EThack dashboard. Shows numbers from the Python API (dashboard/server.py) - computes no scores itself. */
"use strict";

const CATS = ["economic", "social", "environmental"];
const CAT_LABEL = { economic: "Economic", social: "Social", environmental: "Environmental" };
const VIEWS = ["ranking", "sectors", "indicators", "portfolio", "workspace"];

const state = {
  source: "real",
  meta: null,
  base: null,          // profile as loaded from disk
  profile: null,       // profile as edited in the panel
  profileId: null,
  edited: false,
  lastWeight: {},      // indicator -> weight to restore when switched back on
  result: null,
  view: "ranking",
  search: "",
  sector: "",
  limit: 25,
  workspace: null,
  job: null,
};

// ------------------------------------------------------------------ helpers
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const fmt = (v, d = 1) => (isNum(v) ? v.toFixed(d) : "–");
const fmtRaw = (v) => (isNum(v) ? new Intl.NumberFormat("en-US", { maximumSignificantDigits: 4 }).format(v) : "–");
const fmtW = (w) => (Number.isInteger(w) ? String(w) : w.toFixed(1));
const swatch = (c) => `<span class="swatch" style="background:var(--${c})"></span>`;

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-EThack": "1" },
    body: JSON.stringify(body),
  };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({ error: res.statusText }));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function toast(msg, ms = 2600) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (el.hidden = true), ms);
}

function progress(on) {
  $("#progress").classList.toggle("on", on);
}

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

function meter(value, { color = "var(--ink)", cls = "" } = {}) {
  if (!isNum(value)) return `<div class="meter ${cls}"><div class="bar"></div><span class="n na">–</span></div>`;
  return `<div class="meter ${cls}"><div class="bar"><i style="width:${Math.max(1.5, value)}%;background:${color}"></i></div><span class="n">${fmt(value)}</span></div>`;
}

// ------------------------------------------------------------------ theme
function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}
function currentTheme() {
  return document.documentElement.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
try { applyTheme(localStorage.getItem("ethack-theme")); } catch { /* storage blocked */ }

// ------------------------------------------------------------------ profile
function normalizeProfile(raw, previous) {
  const p = structuredClone(raw);
  p.indicator_weights = { ...(raw.indicator_weights || {}) };
  for (const ind of state.meta.indicators) {
    const kept = previous?.indicator_weights?.[ind.id];
    const w = kept ?? p.indicator_weights[ind.id] ?? ind.catalog_weight;
    p.indicator_weights[ind.id] = w;
    state.lastWeight[ind.id] = w > 0 ? w : (state.lastWeight[ind.id] || ind.catalog_weight || 1);
  }
  return p;
}

async function loadProfile(id) {
  const raw = await api(`/api/profile?name=${encodeURIComponent(id)}`);
  state.profileId = id;
  state.base = raw;
  state.profile = normalizeProfile(raw);
  state.edited = false;
  renderPanel();
  scoreNow();
}

function changed() {
  state.edited = true;
  renderProfileDesc();
  renderSplit();
  scoreSoon();
}

// ------------------------------------------------------------------ scoring
let scoreSeq = 0;
async function scoreNow() {
  const seq = ++scoreSeq;
  progress(true);
  try {
    const result = await api("/api/score", { source: state.source, profile: state.profile });
    if (seq !== scoreSeq) return;
    state.result = result;
    if (state.view !== "workspace") renderView();
  } catch (e) {
    toast(e.message);
  } finally {
    if (seq === scoreSeq) progress(false);
  }
}
const scoreSoon = debounce(scoreNow, 140);

// ------------------------------------------------------------------ panel
function renderPanel() {
  const sel = $("#profile-select");
  sel.innerHTML = state.meta.profiles.map((id) => `<option value="${esc(id)}">${esc(id.replace(/_/g, " "))}</option>`).join("");
  sel.value = state.profileId;
  $("#save-name").value = state.profile.name || "";

  $("#category-controls").innerHTML = CATS.map((c) => `
    <div class="slider-row">
      <div class="slider-head">
        <span class="cat-label">${swatch(c)}${CAT_LABEL[c]}</span>
        <span class="value" id="cw-val-${c}"></span>
      </div>
      <input type="range" min="0" max="5" step="0.5" data-cat="${c}" style="--fill:var(--${c})">
    </div>`).join("");
  $$("#category-controls input").forEach((input) => {
    input.value = state.profile.category_weights[input.dataset.cat] ?? 1;
    syncRange(input);
    input.addEventListener("input", () => {
      state.profile.category_weights[input.dataset.cat] = Number(input.value);
      syncRange(input);
      changed();
    });
  });

  const groups = CATS.map((c) => {
    const inds = state.meta.indicators.filter((i) => i.category === c);
    const rows = inds.map((ind) => {
      const w = state.profile.indicator_weights[ind.id];
      const arrow = ind.higher_is_better ? "higher is better" : "lower is better";
      return `
        <div class="ind-row ${w > 0 ? "" : "off"}" data-id="${esc(ind.id)}" title="${esc(ind.description)}\n${esc(ind.unit)} · ${arrow}">
          <input type="checkbox" class="switch" ${w > 0 ? "checked" : ""} aria-label="Use ${esc(ind.name)}">
          <span class="name">${esc(ind.name)}</span>
          <span class="stepper">
            <button data-step="-0.5" aria-label="Less weight">−</button>
            <span>${fmtW(w > 0 ? w : state.lastWeight[ind.id])}×</span>
            <button data-step="0.5" aria-label="More weight">+</button>
          </span>
        </div>`;
    }).join("");
    return `<div class="ind-group">
      <div class="ind-group-title">${swatch(c)}${CAT_LABEL[c]}</div>
      ${rows || `<div class="empty-note">No ready indicators yet</div>`}
    </div>`;
  }).join("");
  $("#indicator-controls").innerHTML = groups;

  $$("#indicator-controls .ind-row").forEach((row) => {
    const id = row.dataset.id;
    $("input", row).addEventListener("change", (e) => {
      state.profile.indicator_weights[id] = e.target.checked ? state.lastWeight[id] : 0;
      row.classList.toggle("off", !e.target.checked);
      renderIndicatorCount();
      changed();
    });
    $$("button", row).forEach((btn) => btn.addEventListener("click", () => {
      const w = Math.min(5, Math.max(0.5, state.lastWeight[id] + Number(btn.dataset.step)));
      state.lastWeight[id] = w;
      state.profile.indicator_weights[id] = w;
      $(".stepper span", row).textContent = `${fmtW(w)}×`;
      changed();
    }));
  });

  $("#sector-relative").checked = !!state.profile.sector_relative;
  const ms = $("#min-share");
  ms.value = state.profile.min_weight_share;
  syncRange(ms);

  renderProfileDesc();
  renderSplit();
  renderIndicatorCount();
}

function renderSummary() {
  const on = state.meta.indicators.filter((i) => state.profile.indicator_weights[i.id] > 0).length;
  $("#panel-summary").textContent = `${state.profile.name}${state.edited ? " (edited)" : ""} · ${on} indicators`;
}

function syncRange(input) {
  const pct = ((input.value - input.min) / (input.max - input.min)) * 100;
  input.style.setProperty("--pct", `${pct}%`);
  if (input.dataset.cat) $(`#cw-val-${input.dataset.cat}`).textContent = `${fmtW(Number(input.value))}×`;
  if (input.id === "min-share") $("#min-share-value").textContent = `${Math.round(input.value * 100)}%`;
}

function activeCategoryWeights() {
  const out = {};
  for (const c of CATS) {
    const hasInd = state.meta.indicators.some((i) => i.category === c && state.profile.indicator_weights[i.id] > 0);
    out[c] = hasInd ? (state.profile.category_weights[c] || 0) : 0;
  }
  return out;
}

function renderSplit() {
  const w = activeCategoryWeights();
  const total = CATS.reduce((s, c) => s + w[c], 0);
  $("#split").innerHTML = total
    ? CATS.filter((c) => w[c] > 0).map((c) => `<span style="flex-grow:${w[c]};background:var(--${c})" title="${CAT_LABEL[c]} ${Math.round((w[c] / total) * 100)}%"></span>`).join("")
    : "";
  $("#split").title = CATS.map((c) => `${CAT_LABEL[c]} ${total ? Math.round((w[c] / total) * 100) : 0}%`).join(" · ");
}

function renderIndicatorCount() {
  const on = state.meta.indicators.filter((i) => state.profile.indicator_weights[i.id] > 0).length;
  $("#indicator-count").textContent = `${on} of ${state.meta.indicators.length} on`;
}

function renderProfileDesc() {
  renderSummary();
  const desc = state.base?.description || "";
  $("#profile-desc").innerHTML = state.edited
    ? `${esc(desc)}${desc ? "<br>" : ""}<span style="color:var(--ink-2)">Edited - save to keep these choices.</span>`
    : esc(desc);
}

// ------------------------------------------------------------------ views
function setView(view) {
  state.view = VIEWS.includes(view) ? view : "ranking";
  $$("#nav button").forEach((b) => b.classList.toggle("active", b.dataset.view === state.view));
  $("#shell").classList.toggle("full", state.view === "workspace" || state.view === "portfolio");
  if (location.hash.slice(1) !== state.view) history.replaceState(null, "", `#${state.view}`);
  renderView();
  window.scrollTo({ top: 0 });
}

function renderView() {
  const main = $("#main");
  if (state.view === "workspace") return renderWorkspace();
  if (!state.result) { main.innerHTML = ""; return; }
  if (state.view === "ranking") main.innerHTML = viewRanking();
  if (state.view === "sectors") main.innerHTML = viewSectors();
  if (state.view === "indicators") main.innerHTML = viewIndicators();
  if (state.view === "portfolio") main.innerHTML = viewPortfolio();
  bindView();
}

function head(title, text, right = "") {
  return `<div class="view-head"><div><h1>${title}</h1><p>${text}</p></div>${right}</div>`;
}

function noIndicators() {
  const live = state.source === "real";
  return `<div class="card empty">
    <h3>${live ? "No indicator is switched on" : "Switch on an indicator"}</h3>
    <p>${live && !state.meta.indicators.length
      ? "The team has no <code>ready</code> indicators yet. Try the demo data in the top right."
      : "Pick at least one indicator in the panel on the left."}</p>
  </div>`;
}

function viewRanking() {
  const r = state.result;
  const n = state.meta.companies;
  const chosen = Object.keys(r.weights);
  let body;
  if (!chosen.length) {
    body = noIndicators();
  } else {
    const q = state.search.trim().toLowerCase();
    const rows = r.rows.filter((row) =>
      (!state.sector || row.sector === state.sector) &&
      (!q || row.ticker.toLowerCase().includes(q) || (row.name || "").toLowerCase().includes(q)));
    const shown = rows.slice(0, state.limit);
    const active = CATS.filter((c) => r.category_weights[c]);
    const tr = shown.map((row) => `
      <tr class="click" data-ticker="${esc(row.ticker)}">
        <td class="pos">${row.position ?? ""}</td>
        <td><div class="co"><b>${esc(row.ticker)}</b><span>${esc(row.name)}</span></div></td>
        <td class="sector-cell hide-sm">${esc(row.sector)}</td>
        <td>${meter(row.total_score, { cls: "total" })}</td>
        ${active.map((c) => `<td class="hide-sm">${meter(row[`${c}_score`], { color: `var(--${c})`, cls: "mini" })}</td>`).join("")}
      </tr>`).join("");
    body = `
      <div class="toolbar">
        <div class="search">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
          <input type="search" id="search" placeholder="Search company or ticker" value="${esc(state.search)}">
        </div>
        ${state.meta.sectors.length ? `<div class="select-wrap"><select id="sector-filter">
          <option value="">All sectors</option>
          ${state.meta.sectors.map((s) => `<option ${s === state.sector ? "selected" : ""}>${esc(s)}</option>`).join("")}
        </select></div>` : ""}
        <span class="count">${rows.length} companies</span>
      </div>
      <div class="card table-wrap">
        <table class="data">
          <thead><tr>
            <th>#</th><th>Company</th><th class="hide-sm">Sector</th><th>Total score</th>
            ${active.map((c) => `<th class="hide-sm"><span class="cat-label">${swatch(c)}${CAT_LABEL[c]}</span></th>`).join("")}
          </tr></thead>
          <tbody>${tr || `<tr><td colspan="8" class="muted" style="text-align:center;padding:40px">No company matches</td></tr>`}</tbody>
        </table>
        ${rows.length > state.limit ? `<div class="more"><button class="btn ghost sm" id="more">Show ${Math.min(50, rows.length - state.limit)} more</button></div>` : ""}
      </div>`;
  }

  const leader = r.rows.find((row) => isNum(row.total_score));
  const perCat = CATS.map((c) => chosen.filter((id) => state.meta.indicators.find((i) => i.id === id)?.category === c).length);
  const stats = `
    <div class="stats">
      <div class="stat"><span class="k">Companies scored</span><span class="v">${r.scored}<small> / ${n}</small></span><span class="s">enough data under the coverage rule</span></div>
      <div class="stat"><span class="k">Median total score</span><span class="v">${fmt(r.median)}</span><span class="s">50 = middle of the pack</span></div>
      <div class="stat"><span class="k">Leader</span><span class="v">${leader ? esc(leader.ticker) : "–"}</span><span class="s">${leader ? `${fmt(leader.total_score)} · ${esc(leader.name || leader.sector || "")}` : "no scores yet"}</span></div>
      <div class="stat"><span class="k">Indicators in use</span><span class="v">${chosen.length}</span><span class="s">${CATS.map((c, i) => `<span class="cat-label" style="gap:5px;font-weight:400" title="${CAT_LABEL[c]}">${swatch(c)}${perCat[i]}</span>`).join("&nbsp;&nbsp;&nbsp;")}</span></div>
    </div>`;

  return head("Ranking", `Companies ordered by total impact score for <b>${esc(state.profile.name)}</b>. Click a company to see what drives its score.`) + stats + body;
}

function viewSectors() {
  const r = state.result;
  if (!Object.keys(r.weights).length) return head("Sectors", "") + noIndicators();
  if (!r.sectors.length) {
    return head("Sectors", "Median scores per GICS sector.") +
      `<div class="card empty"><h3>No sector data yet</h3><p>Sectors appear once <code>universe/sp500.csv</code> exists.</p></div>`;
  }
  const active = CATS.filter((c) => r.category_weights[c]);
  const rows = r.sectors.map((s) => `
    <div class="sector-row">
      <div class="name">${esc(s.sector)}<small>${s.scored} of ${s.companies} scored</small></div>
      ${meter(s.total, { cls: "total" })}
      ${CATS.map((c) => `<span class="cat-val">${active.includes(c) ? `${swatch(c)}${fmt(s[c])}` : ""}</span>`).join("")}
    </div>`).join("");
  const hint = state.profile.sector_relative
    ? "Companies are ranked within their sector, so sector medians sit close to 50 by design."
    : "Big gaps between sectors? Switch on <b>Compare within sector</b> to judge companies against their peers.";
  return head("Sectors", `Median score per GICS sector. ${hint}`) + `
    <div class="card sector-list">
      <div class="sector-row head"><span>Sector</span><span>Median total</span>${CATS.map((c) => `<span class="cat-val">${active.includes(c) ? CAT_LABEL[c] : ""}</span>`).join("")}</div>
      ${rows}
    </div>`;
}

function heatColor(rho) {
  const lerp = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
  const mid = [240, 239, 236], pos = [42, 120, 214], neg = [227, 73, 72];
  const [r, g, b] = lerp(mid, rho >= 0 ? pos : neg, Math.min(1, Math.abs(rho)));
  return { bg: `rgb(${r},${g},${b})`, fg: Math.abs(rho) > 0.55 ? "#fff" : "#0b0b0b" };
}

function viewIndicators() {
  const r = state.result;
  const inds = state.meta.indicators;
  if (!inds.length) {
    return head("Indicators", "The building blocks of every score.") +
      `<div class="card empty"><h3>No ready indicators yet</h3><p>Build them in <b>Workspace</b>, or try the demo data.</p></div>`;
  }
  const sections = CATS.map((c) => {
    const list = inds.filter((i) => i.category === c);
    if (!list.length) return "";
    return `<div class="ind-section">
      <h2>${swatch(c)}${CAT_LABEL[c]}</h2>
      <div class="card">${list.map((ind) => {
        const w = r.weights[ind.id];
        const cov = Math.round(ind.coverage * 100);
        return `<div class="ind-card">
          <div>
            <div class="title">${esc(ind.name)}
              <span class="chip">${ind.higher_is_better ? "↑ higher is better" : "↓ lower is better"}</span>
              ${w ? `<span class="chip on">${fmtW(w)}× weight</span>` : `<span class="chip">off</span>`}
            </div>
            <div class="desc">${esc(ind.description)}</div>
            <div class="meta">${esc(ind.unit)} · ${esc(ind.source)} · ${esc(ind.owner)}</div>
          </div>
          <div class="cov" title="Target: 70% of companies">
            <div class="top"><span>Coverage</span><b>${cov}%</b></div>
            <div class="bar"><i style="width:${cov}%;background:${cov >= 70 ? `var(--${c})` : "var(--ink-3)"}"></i></div>
            <span class="muted small">${ind.companies} companies</span>
          </div>
          <div class="muted small">${ind.year_min ? `${ind.year_min === ind.year_max ? ind.year_max : `${ind.year_min}–${ind.year_max}`}` : ""}<br>latest year</div>
        </div>`;
      }).join("")}</div>
    </div>`;
  }).join("");

  const { ids, matrix } = r.correlation;
  let heat = "";
  if (ids.length >= 2) {
    const name = (id) => inds.find((i) => i.id === id)?.name || id;
    const cells = ids.map((a, i) => `<div class="lab" title="${esc(name(a))}">${esc(name(a))}</div>` +
      matrix[i].map((rho, j) => {
        if (rho === null) return `<div class="cell" style="background:var(--surface-2)">–</div>`;
        const { bg, fg } = heatColor(rho);
        return `<div class="cell" style="background:${bg};color:${fg}" title="${esc(name(a))} × ${esc(name(ids[j]))}: ${rho.toFixed(2)}">${i === j ? "" : rho.toFixed(2)}</div>`;
      }).join("")).join("");
    heat = `<div class="ind-section">
      <div class="card card-pad">
        <h3>Do two indicators measure the same thing?</h3>
        <p class="sub">Rank correlation between the indicators in use. Close to +1 means near-duplicates - consider keeping only one.</p>
        <div class="table-wrap">
          <div class="heat" style="grid-template-columns: minmax(120px, 220px) repeat(${ids.length}, minmax(44px, 72px))">
            ${cells}
            <div></div>${ids.map((id) => `<div class="collab" title="${esc(name(id))}">${esc(name(id))}</div>`).join("")}
          </div>
        </div>
      </div>
    </div>`;
  }
  return head("Indicators", "The building blocks of every score: what they measure, which direction is better, and how many companies they cover.") + sections + heat;
}

/* --- 3D impact cube: the three category scores as one picture. -----------------
   Each company is a point at (economic, social, environmental). The corner where
   all three are high is where a score-tilted portfolio puts its money, so this is
   the allocation rule made visible. Plain canvas, no libraries. */

const CUBE = { yaw: -0.6, pitch: -0.35, drag: null, raf: null, spin: true };
const CUBE_AXES = [
  { key: "economic_score", label: "Economic" },
  { key: "social_score", label: "Social" },
  { key: "environmental_score", label: "Environmental" },
];

function cubeRows() {
  if (!state.result) return [];
  return state.result.rows.filter((r) => CUBE_AXES.every((a) => isNum(r[a.key])));
}

function viewCube() {
  const rows = cubeRows();
  const missing = CUBE_AXES.filter((a) => !state.result.rows.some((r) => isNum(r[a.key])));
  const note = missing.length
    ? `<p class="sub">No data yet on ${missing.map((m) => esc(m.label.toLowerCase())).join(" and ")} -
       those axes stay empty until those indicators are ready.</p>`
    : `<p class="sub">${rows.length} companies with all three scores. Drag to rotate.</p>`;
  return `<div class="card card-pad cube-card">
      <div class="section-head"><h3>Impact cube</h3><span class="muted small">high / high / high = overweight</span></div>
      ${note}
      <canvas id="cube" height="320"></canvas>
      <div class="cube-legend">
        ${CUBE_AXES.map((a) => `<span><i></i>${esc(a.label)}</span>`).join("")}
      </div>
    </div>`;
}

function cubeProject(v, w, h) {
  // v is in -1..1 on each axis. Rotate around Y (yaw) then X (pitch), then project.
  const cy = Math.cos(CUBE.yaw), sy = Math.sin(CUBE.yaw);
  const cp = Math.cos(CUBE.pitch), sp = Math.sin(CUBE.pitch);
  const x1 = v[0] * cy + v[2] * sy;
  const z1 = -v[0] * sy + v[2] * cy;
  const y1 = v[1] * cp - z1 * sp;
  const z2 = v[1] * sp + z1 * cp;
  const d = 4.2;
  const k = d / (d + z2);
  const scale = Math.min(w, h) * 0.34;
  return [w / 2 + x1 * scale * k, h / 2 - y1 * scale * k, z2];
}

function drawCube() {
  const c = $("#cube");
  if (!c) return;
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth, h = 320;
  if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr; }
  const g = c.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);

  const css = getComputedStyle(document.body);
  const line = css.getPropertyValue("--line").trim() || "rgba(128,128,128,.35)";
  const ink = css.getPropertyValue("--muted").trim() || "#888";

  // wireframe
  const C = [[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]];
  const E = [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];
  g.strokeStyle = line; g.lineWidth = 1;
  E.forEach(([a, b]) => {
    const p = cubeProject(C[a], w, h), q = cubeProject(C[b], w, h);
    g.beginPath(); g.moveTo(p[0], p[1]); g.lineTo(q[0], q[1]); g.stroke();
  });

  // the "overweight" corner - all three high
  const hi = cubeProject([1, 1, 1], w, h);
  g.fillStyle = "rgba(70,190,120,.18)";
  g.beginPath(); g.arc(hi[0], hi[1], 26, 0, 7); g.fill();

  // axis labels at the far end of each axis
  g.fillStyle = ink; g.font = "11px system-ui, sans-serif";
  [[[1,-1,-1],"Economic"],[[-1,1,-1],"Social"],[[-1,-1,1],"Environmental"]].forEach(([v, t]) => {
    const p = cubeProject(v, w, h);
    g.fillText(t, p[0] + 4, p[1] - 4);
  });

  // companies, painted back to front so nearer dots sit on top
  const pts = cubeRows().map((r) => {
    const v = CUBE_AXES.map((a) => r[a.key] / 50 - 1);
    const p = cubeProject(v, w, h);
    return { p, total: isNum(r.total_score) ? r.total_score : 50 };
  }).sort((a, b) => b.p[2] - a.p[2]);

  pts.forEach((d) => {
    g.fillStyle = `hsl(${Math.round(8 + 1.42 * d.total)} 62% 52% / .8)`;
    g.beginPath(); g.arc(d.p[0], d.p[1], 2.6, 0, 7); g.fill();
  });
}

function initCube() {
  const c = $("#cube");
  if (!c) return;
  drawCube();
  const move = (e) => {
    if (!CUBE.drag) return;
    const t = e.touches ? e.touches[0] : e;
    CUBE.yaw += (t.clientX - CUBE.drag.x) * 0.01;
    CUBE.pitch += (t.clientY - CUBE.drag.y) * 0.01;
    CUBE.pitch = Math.max(-1.3, Math.min(1.3, CUBE.pitch));
    CUBE.drag = { x: t.clientX, y: t.clientY };
    drawCube();
  };
  const down = (e) => {
    CUBE.spin = false;
    const t = e.touches ? e.touches[0] : e;
    CUBE.drag = { x: t.clientX, y: t.clientY };
  };
  const up = () => { CUBE.drag = null; };
  c.addEventListener("mousedown", down);
  c.addEventListener("touchstart", down, { passive: true });
  window.addEventListener("mousemove", move);
  window.addEventListener("touchmove", move, { passive: true });
  window.addEventListener("mouseup", up);
  window.addEventListener("touchend", up);
  window.addEventListener("resize", drawCube);
  if (CUBE.raf) cancelAnimationFrame(CUBE.raf);
  const tick = () => {
    if (CUBE.spin && !CUBE.drag && $("#cube")) { CUBE.yaw += 0.0035; drawCube(); }
    CUBE.raf = requestAnimationFrame(tick);
  };
  tick();
}

function viewPortfolio() {
  const settings = state.meta.portfolio.settings;
  const p = state.profile.portfolio || {};
  return head("Portfolio", "How a $1B fund would be allocated using the scores of the selected profile.") + `
    <div class="card placeholder">
      <span class="chip warn badge">Phase 3 · placeholder</span>
      <h2>Portfolio allocation is coming next</h2>
      <p>The scores are ready to feed in. How they become weights is a team decision - the interface is already fixed in <code>portfolio/allocate.py</code>.</p>
      <div style="margin-top:22px"><button class="btn" disabled>Build portfolio</button></div>
    </div>
    <div class="steps">
      <div class="card step"><div class="n">1</div><h4>Scores in</h4><p>Total and category scores of <b>${esc(state.profile.name)}</b>, for every company with enough data.</p></div>
      <div class="card step"><div class="n">2</div><h4>Allocation rule</h4><p>Tilt toward high scores or exclude the bottom X%, with a cap per company and optional sector neutrality.</p></div>
      <div class="card step"><div class="n">3</div><h4>Weights out</h4><p><code>${state.meta.portfolio.output_columns.join(", ")}</code> - weights sum to 100% of the fund.</p></div>
    </div>
    ${viewCube()}
    <div class="card card-pad" style="margin-top:16px">
      <h3>Settings a profile can already store</h3>
      <p class="sub">Under <code>[portfolio]</code> in <code>profiles/${esc(state.profileId)}.toml</code></p>
      <div class="kv">
        ${Object.entries(settings).map(([k, v]) => `<code>${esc(k)}</code><span class="muted">${esc(v)}</span><b>${esc(p[k] ?? "")}</b>`).join("")}
      </div>
    </div>`;
}

// ------------------------------------------------------------------ workspace
async function loadWorkspace(fetchRemote = false) {
  try {
    state.workspace = await api(`/api/workspace${fetchRemote ? "?fetch=1" : ""}`);
    const g = state.workspace.git;
    $("#ws-dot").hidden = !(g.changes.length || g.behind || state.workspace.check.errors.length);
    if (state.workspace.job && !state.job) followJob(state.workspace.job);
  } catch (e) {
    toast(e.message);
  }
}

async function renderWorkspace() {
  const main = $("#main");
  if (!state.workspace) {
    main.innerHTML = head("Workspace", "Loading…");
    await loadWorkspace(true);
  }
  const ws = state.workspace;
  if (!ws || state.view !== "workspace") return;
  const g = ws.git;
  const busy = !!state.job?.running;
  const dis = busy ? "disabled" : "";
  const [lastMsg, lastWho, lastWhen] = (g.last_commit || "").split("|");

  const statusChip = (s) => ({ ready: "good", in_progress: "warn" }[s] || "");
  const checks = [
    ...ws.check.errors.map((x) => `<div class="check-item"><span class="icon err">!</span><div>${esc(x.message)}<span class="area">${esc(x.area)}</span></div></div>`),
    ...ws.check.warnings.map((x) => `<div class="check-item"><span class="icon warn">!</span><div>${esc(x.message)}<span class="area">${esc(x.area)}</span></div></div>`),
  ];
  if (!ws.check.errors.length) checks.unshift(`<div class="check-item"><span class="icon ok">✓</span><div>Format check passed<span class="area">every catalog and indicator file</span></div></div>`);

  main.innerHTML = head("Workspace", "Everything the command line does - sync with the team, build and check data, export scores.",
    `<button class="btn ghost" id="ws-refresh" ${dis}>Refresh</button>`) + `
    <div class="ws-grid">
      <div class="card card-pad">
        <h3>Team sync</h3>
        <p class="sub">On <code>${esc(g.branch)}</code> as ${esc(g.user || "unknown")}${lastMsg ? ` · last: ${esc(lastMsg)} (${esc(lastWho)}, ${esc(lastWhen)})` : ""}</p>
        <div class="sync-status">
          <div><b>${g.changes.length}</b><span>unsaved changes</span></div>
          <div><b>${g.ahead}</b><span>not pushed</span></div>
          <div><b>${g.behind}</b><span>new from team</span></div>
        </div>
        ${g.changes.length ? `<div class="files">${g.changes.map((f) => `<div><code title="${esc(f.path)}">${esc(f.path)}</code><span class="muted">${esc(f.owner)}</span></div>`).join("")}</div>` : ""}
        <div class="row-actions" style="margin-bottom:14px">
          <button class="btn ghost" data-run="start" ${dis}>Get latest from team</button>
        </div>
        <div class="save-row">
          <input type="text" id="save-message" placeholder="[area] what you changed, e.g. [social] ceo pay ratio: 412 companies">
          <button class="btn" data-run="save" ${dis}>Save & push</button>
        </div>
        <p class="muted small" style="margin:8px 0 0">Commit → pull → format check → push. Stops safely on conflicts.</p>
      </div>

      <div class="card card-pad">
        <h3>Data health</h3>
        <p class="sub">The format rules from docs/DATA_FORMAT.md</p>
        <div class="checks">${checks.join("")}</div>
        <button class="btn ghost" data-run="check" ${dis}>Run check + tests</button>
      </div>

      <div class="card wide">
        <div class="card-pad" style="padding-bottom:16px">
          <div style="display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:end">
            <div><h3>Indicators</h3><p class="sub" style="margin:0">Every catalog row, including ideas. Only <b>ready</b> ones are scored.</p></div>
            <div class="form-row">
              <div class="select-wrap"><select id="new-cat">${CATS.map((c) => `<option value="${c}">${CAT_LABEL[c]}</option>`).join("")}</select></div>
              <input type="text" id="new-id" placeholder="new_indicator_id">
              <button class="btn ghost" data-run="new-indicator" ${dis}>Add indicator</button>
            </div>
          </div>
        </div>
        <div class="table-wrap">
          <table class="data compact">
            <thead><tr><th>Indicator</th><th class="hide-sm">Owner</th><th>Status</th><th class="right">Companies</th><th class="right hide-sm">Latest year</th><th class="right">Build</th></tr></thead>
            <tbody>
              ${ws.catalog.map((row) => `<tr>
                <td><div class="co"><b><span class="cat-label">${swatch(row.category)}${esc(row.name || row.indicator_id)}</span></b><span><code>${esc(row.category)}/${esc(row.indicator_id)}</code></span></div></td>
                <td class="hide-sm">${esc(row.owner)}</td>
                <td><span class="chip ${statusChip(row.status)} status-pill">${esc(row.status.replace("_", " "))}</span></td>
                <td class="right num">${row.has_file ? row.companies : "–"}</td>
                <td class="right num hide-sm">${row.year_max ?? "–"}</td>
                <td class="right"><button class="btn ghost sm" data-run="build" data-cat="${esc(row.category)}" data-id="${esc(row.indicator_id)}" ${row.has_script && !busy ? "" : "disabled"} title="${row.has_script ? "Run the script" : "No script yet"}">Build</button></td>
              </tr>`).join("") || `<tr><td colspan="6" class="muted" style="text-align:center;padding:32px">No indicators in any catalog yet</td></tr>`}
            </tbody>
          </table>
        </div>
        <div class="card-pad row-actions" style="border-top:1px solid var(--border);padding-block:14px">
          ${CATS.map((c) => `<button class="btn ghost sm" data-run="build" data-cat="${c}" ${dis}>${swatch(c)}Build all ${CAT_LABEL[c].toLowerCase()}</button>`).join("")}
        </div>
      </div>

      <div class="card card-pad wide">
        <div style="display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;align-items:center">
          <div><h3>Export scores</h3><p class="sub" style="margin:0">Writes <code>scores/&lt;profile&gt;/scores.csv</code> and <code>indicator_ranks.csv</code> from the live data.</p></div>
          <div class="save-row">
            <div class="select-wrap" style="min-width:200px"><select id="export-profile">${ws.profiles.map((p) => `<option ${p === state.profileId ? "selected" : ""}>${esc(p)}</option>`).join("")}</select></div>
            <button class="btn" data-run="score" ${dis}>Export</button>
          </div>
        </div>
      </div>
    </div>`;

  $("#ws-refresh").addEventListener("click", async () => { await loadWorkspace(true); renderWorkspace(); });
  $$("[data-run]", main).forEach((btn) => btn.addEventListener("click", () => {
    const command = btn.dataset.run;
    const payload = { command };
    if (command === "save") payload.message = $("#save-message").value;
    if (command === "build") Object.assign(payload, { category: btn.dataset.cat, indicator_id: btn.dataset.id || "" });
    if (command === "new-indicator") Object.assign(payload, { category: $("#new-cat").value, indicator_id: $("#new-id").value.trim() });
    if (command === "score") payload.profile = $("#export-profile").value;
    runJob(payload);
  }));
}

async function runJob(payload) {
  try {
    followJob(await api("/api/run", payload));
  } catch (e) {
    toast(e.message, 4000);
  }
}

function followJob(job) {
  state.job = job;
  showConsole(job);
  if (state.view === "workspace") renderWorkspace();
  const poll = async () => {
    try {
      const j = await api(`/api/job?id=${job.id}`);
      state.job = j;
      showConsole(j);
      if (j.running) return setTimeout(poll, 600);
      toast(j.code === 0 ? `Done: ${j.title}` : `Failed: ${j.title} - see output`, 3500);
      await afterJob();
    } catch (e) {
      toast(e.message);
    }
  };
  setTimeout(poll, 400);
}

async function afterJob() {
  await loadWorkspace(false);
  await reloadMeta();
  if (state.view === "workspace") renderWorkspace();
}

function showConsole(job) {
  $("#console").hidden = false;
  $("#console-title").textContent = job.title;
  $("#console-cmd").textContent = job.command;
  $("#console-dot").className = `status-dot ${job.running ? "running" : job.code === 0 ? "ok" : "fail"}`;
  const out = $("#console-out");
  const atBottom = out.scrollHeight - out.scrollTop - out.clientHeight < 40;
  out.textContent = job.output.join("\n") || (job.running ? "running…" : "(no output)");
  if (atBottom) out.scrollTop = out.scrollHeight;
}

// ------------------------------------------------------------------ company drawer
async function openCompany(ticker) {
  const drawer = $("#drawer");
  drawer.innerHTML = `<div class="muted">Loading ${esc(ticker)}…</div>`;
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
  $("#scrim").hidden = false;
  try {
    const { company: co, indicators } = await api("/api/explain", { source: state.source, profile: state.profile, ticker });
    const r = state.result;
    const drivers = indicators.filter((d) => isNum(d.rank)).sort((a, b) => b.points - a.points);
    const missing = indicators.filter((d) => !isNum(d.rank));
    drawer.innerHTML = `
      <div class="drawer-top">
        <div>
          <div class="ticker">${esc(co.ticker)}</div>
          <h2>${esc(co.name || co.ticker)}</h2>
          <div class="muted">${esc(co.sector || "")}</div>
        </div>
        <button class="icon-btn" id="drawer-close" aria-label="Close">✕</button>
      </div>
      <div class="hero-score"><b>${fmt(co.total_score)}</b><span>${isNum(co.total_score) ? `total score · #${co.position} of ${r.scored}` : "not enough data for a total score"}</span></div>
      <div class="cat-bars">
        ${CATS.map((c) => {
          const v = co[`${c}_score`];
          const on = r.category_weights[c];
          return `<div class="cat-bar">
            <span class="cat-label">${swatch(c)}${CAT_LABEL[c]}</span>
            <div class="bar">${isNum(v) ? `<i style="width:${Math.max(1.5, v)}%;background:var(--${c})"></i>` : ""}</div>
            <span class="n ${isNum(v) ? "" : "na"}">${on ? fmt(v) : "off"}</span>
          </div>`;
        }).join("")}
      </div>
      <p class="section-title">What drives the score</p>
      <p class="muted small" style="margin:0 0 8px">Percentile = share of compared companies this one beats. Points add up to the total score.</p>
      ${drivers.map((d) => `
        <div class="driver">
          <span class="t">${swatch(d.category)}${esc(d.name || d.indicator_id)}</span>
          <span class="pts">+${fmt(d.points)}</span>
          <span class="raw">${fmtRaw(d.value)} ${esc(d.unit)}${isNum(d.year) ? ` · ${d.year}` : ""} · ${d.higher_is_better ? "higher" : "lower"} is better</span>
          <span class="raw">better than ${Math.round(d.rank * 100)}%</span>
          <div class="bar"><i style="width:${Math.max(1.5, d.rank * 100)}%;background:var(--${d.category})"></i></div>
        </div>`).join("")}
      ${missing.length ? `<p class="muted small" style="margin-top:18px">No data for: ${missing.map((d) => esc(d.name || d.indicator_id)).join(", ")}</p>` : ""}
    `;
    $("#drawer-close").addEventListener("click", closeCompany);
  } catch (e) {
    drawer.innerHTML = `<p>${esc(e.message)}</p>`;
  }
}

function closeCompany() {
  $("#drawer").classList.remove("open");
  $("#drawer").setAttribute("aria-hidden", "true");
  $("#scrim").hidden = true;
}

// ------------------------------------------------------------------ wiring
function bindView() {
  const search = $("#search");
  if (search) {
    search.addEventListener("input", debounce(() => {
      state.search = search.value;
      state.limit = 25;
      const pos = search.selectionStart;
      renderView();
      const again = $("#search");
      again.focus();
      again.setSelectionRange(pos, pos);
    }, 120));
  }
  $("#sector-filter")?.addEventListener("change", (e) => { state.sector = e.target.value; state.limit = 25; renderView(); });
  $("#more")?.addEventListener("click", () => { state.limit += 50; renderView(); });
  $$("tr[data-ticker]").forEach((tr) => tr.addEventListener("click", () => openCompany(tr.dataset.ticker)));
  initCube();
}

async function reloadMeta() {
  state.meta = await api(`/api/meta?source=${state.source}`);
  $("#demo-banner").hidden = state.source !== "demo";
  $$("#source button").forEach((b) => b.classList.toggle("active", b.dataset.source === state.source));
  state.profile = normalizeProfile({ ...state.base, ...state.profile, indicator_weights: state.base.indicator_weights }, state.profile);
  renderPanel();
  scoreNow();
}

function bindStatic() {
  $$("#nav button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
  $$("#source button").forEach((b) => b.addEventListener("click", async () => {
    if (b.dataset.source === state.source) return;
    state.source = b.dataset.source;
    state.search = ""; state.sector = ""; state.limit = 25;
    await reloadMeta();
  }));
  $("#theme").addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("ethack-theme", next); } catch { /* storage blocked */ }
  });
  $("#profile-select").addEventListener("change", (e) => loadProfile(e.target.value));
  $("#sector-relative").addEventListener("change", (e) => { state.profile.sector_relative = e.target.checked; changed(); });
  $("#min-share").addEventListener("input", (e) => { state.profile.min_weight_share = Number(e.target.value); syncRange(e.target); changed(); });
  $("#save-btn").addEventListener("click", async () => {
    const name = $("#save-name").value.trim();
    if (!name) return toast("Give the profile a name first");
    try {
      const res = await api("/api/profiles", { profile: { ...state.profile, name } });
      state.meta.profiles = res.profiles;
      state.profileId = res.id;
      state.base = { ...state.profile, name };
      state.profile.name = name;
      state.edited = false;
      renderPanel();
      $("#save-msg").textContent = `Saved to ${res.path}`;
      toast(`Profile saved: ${name}`);
    } catch (e) {
      toast(e.message);
    }
  });
  $("#scrim").addEventListener("click", closeCompany);
  $("#panel-toggle").addEventListener("click", () => {
    const open = $("#panel").classList.toggle("open");
    $("#panel-toggle").setAttribute("aria-expanded", String(open));
  });
  $("#console-close").addEventListener("click", () => ($("#console").hidden = true));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeCompany(); });
  window.addEventListener("hashchange", () => setView(location.hash.slice(1)));
}

async function init() {
  bindStatic();
  try {
    state.meta = await api("/api/meta?source=real");
    const asked = new URLSearchParams(location.search).get("source");  // ?source=demo for presentations
    state.source = asked === "demo" || asked === "real" ? asked : state.meta.has_real ? "real" : "demo";
    if (state.source === "demo") state.meta = await api("/api/meta?source=demo");
    $("#demo-banner").hidden = state.source !== "demo";
    $$("#source button").forEach((b) => b.classList.toggle("active", b.dataset.source === state.source));
    setView(location.hash.slice(1) || "ranking");
    await loadProfile(state.meta.profiles.includes(state.meta.default_profile) ? state.meta.default_profile : state.meta.profiles[0]);
    loadWorkspace(false);
    const company = new URLSearchParams(location.search).get("company");  // ?company=AAPL deep link
    if (company) openCompany(company.toUpperCase());
  } catch (e) {
    $("#main").innerHTML = `<div class="card empty"><h3>Could not reach the dashboard server</h3><p>${esc(e.message)}<br>Start it with <code>python run.py dashboard</code>.</p></div>`;
  }
}

init();
