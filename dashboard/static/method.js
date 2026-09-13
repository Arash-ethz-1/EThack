/* Method tab - dashboard/static/method.js (loaded after app.js, uses its helpers).
   How a number is made, shown for one real company, step under step: source value -> rank in sector
   -> pillar score -> total -> weight in the fund. Every number comes from POST /api/trace
   (common/score.py and portfolio/allocate.py); the browser only lays the arithmetic out.
   Indicator facts come from GET /api/meta; the pillar questions and weak spots are editorial text. */

const PILLARS = {
  environmental: { q: "Is it damaging nature - and does it depend on resources that may run out?", name: "Environmental Factors" },
  social: { q: "Does it treat the people who work for it fairly and safely?", name: "Social Factors" },
  economic: { q: "Can it sustain itself and the economy around it?", name: "Economic Factors" },
};
const WEAK = {
  tax_rate_gap: "Part of a gap comes from legal R&D credits and foreign tax rates.",
  revenue_volatility: "Punishes fast-growing companies as much as unstable ones.",
  employment_growth: "Jobs bought through an acquisition count as jobs created.",
  federal_contract_exposure: "Direct federal contracts only; subcontracting is invisible.",
  median_worker_pay: "Driven by industry and country mix - fair only within a sector.",
  labor_litigation_intensity: "Only disputes that reach federal court; arbitration clauses hide the rest.",
  political_alignment: "Company PACs only - lobbying fees and trade associations are invisible.",
  shareholder_payout_ratio: "Dividends are not harmful in themselves; a debated measure.",
  ceo_pay_ratio: "Companies with low-paid or part-time workforces look worse.",
  employer_retirement_contribution: "US plans only; defined-benefit pensions excluded.",
  workplace_injury_rate: "Banks, software and railroads do not report to OSHA.",
  human_capital_disclosure: "Measures what a company counts, not how it treats people.",
  resource_supply_risk: "One value per sub-industry - it does not separate peers.",
  sbti_climate_target: "A target, not actual emissions.",
  ghg_intensity: "US facilities above 25,000 t only; no Scope 2 or 3.",
  epa_penalty_intensity: "Federal EPA cases only; fines also reflect how hard a regulator looks.",
};
const TRACE = { ticker: null, data: null, ind: null, loading: false };
const n2 = (v, d = 2) => v == null ? "–" : (+v).toFixed(d);

function strip(cmp, unit) {
  const W = 1120, H = 74, L = 8, R = 8, n = cmp.peers.length;
  if (!n) return "";
  const x = i => L + (W - L - R) * (n === 1 ? .5 : i / (n - 1));
  let g = `<line class="grid" x1="${L}" x2="${W - R}" y1="34" y2="34"/>`;
  const mine = cmp.peers.findIndex(p => p.ticker === cmp.ticker);
  cmp.peers.forEach((p, i) => g += `<circle class="${i === mine ? "dot-me" : "dot"}" cx="${x(i)}" cy="34" r="${i === mine ? 7 : 4.5}"><title>${esc(p.ticker)}: ${fmtVal(p.value, unit)}</title></circle>`);
  const lo = cmp.peers[0], hi = cmp.peers[n - 1];
  g += `<text x="${L}" y="66">lowest ${fmtVal(lo.value, unit)} (${esc(lo.ticker)})</text><text x="${W - R}" y="66" text-anchor="end">highest ${fmtVal(hi.value, unit)} (${esc(hi.ticker)})</text>`;
  if (mine >= 0) g += `<text class="strong" x="${Math.min(Math.max(x(mine), 90), W - 90)}" y="14" text-anchor="middle">${esc(cmp.ticker)} · ${fmtVal(cmp.value, unit)}</text>`;
  return svg(W, H, g, "Every company in the sector, sorted by value");
}

async function loadTrace() {
  TRACE.loading = true;
  TRACE.data = await postJSON("/api/trace", body({ ticker: TRACE.ticker, settings: PF.settings || {} }));
  TRACE.loading = false;
  if (!TRACE.data.error && !TRACE.ind) {
    const withData = TRACE.data.indicators.filter(x => x.comparison.rank != null);
    TRACE.ind = (withData.find(x => x.indicator_id === "ghg_intensity") || withData[0] || {}).indicator_id;
  }
  if (state.view === "method") renderMethod();
}

function renderMethod() {
  if (!TRACE.ticker) TRACE.ticker = state.score.rows.find(r => r.ticker === "NUE") ? "NUE" : state.score.rows[0].ticker;
  if (!TRACE.data || TRACE.data.company?.ticker !== TRACE.ticker) {
    if (!TRACE.loading) loadTrace();
    $("#view-method").innerHTML = `<div class="head"><p class="eyebrow">Method</p><h2>Calculating ${esc(TRACE.ticker)}…</h2></div>`;
    return;
  }
  const t = TRACE.data;
  if (t.error) { $("#view-method").innerHTML = `<p class="muted">${esc(t.error)}</p>`; return; }
  const c = t.company, inds = t.indicators, fund = t.fund, s = fund.settings;
  const cur = inds.find(x => x.indicator_id === TRACE.ind) || inds[0], cmp = cur.comparison;
  const opts = state.score.rows.slice().sort((a, b) => (a.name || "").localeCompare(b.name || ""))
    .map(r => `<option value="${r.ticker}"${r.ticker === c.ticker ? " selected" : ""}>${esc(r.name)} (${r.ticker})</option>`).join("");
  const catName = id => (HOME_ORDER.find(k => k[0] === id) || [id, id])[1];
  const col = id => `var(${(CATS.find(k => k[0] === id) || CATS[0])[2]})`;
  const raw = cmp.position != null && cmp.n > 1 ? (cmp.position - 1) / (cmp.n - 1) : null;

  const step = (n, title, text, inner) => `<li class="mstep"><div class="mstep-n num">${n}</div><div class="mstep-b"><h3>${title}</h3>${text ? `<p class="lead">${text}</p>` : ""}${inner}</div></li>`;

  const sourceTable = `<div class="table-wrap"><table class="mini wide"><thead><tr><th>Indicator</th><th class="r">Value</th><th class="r">Year</th><th>Source</th></tr></thead><tbody>
    ${inds.map(x => `<tr class="${x.value == null ? "out" : ""}"><td title="${esc(x.name)}"><span class="sw" style="background:${col(x.category)}"></span>${esc(short(x.indicator_id))}</td>
      <td class="r num">${x.value == null ? "no data" : `${fmtVal(x.value, x.unit)} <span class="muted small">${esc(x.unit || "")}</span>`}</td>
      <td class="r num">${x.year ?? "–"}</td>
      <td class="small">${x.source_url ? `<a href="${esc(x.source_url)}" target="_blank" rel="noopener">${esc((x.source || "source").split(/[(+,]/)[0].trim())} ↗</a>` : '<span class="muted">–</span>'}</td></tr>`).join("")}
  </tbody></table></div>`;

  const rankBlock = `<div class="chips">${inds.filter(x => x.comparison.rank != null).map(x => `<button type="button" data-ind="${x.indicator_id}" aria-pressed="${x.indicator_id === cur.indicator_id}" title="${esc(x.name)}">${esc(short(x.indicator_id))}</button>`).join("")}</div>
    ${cmp.rank != null ? `<figure class="fig flat">${strip(cmp, cur.unit)}<figcaption>${cmp.n} ${esc(c.sector)} companies, lowest to highest</figcaption></figure>
    <div class="calc">
      <div><span>position</span><b class="num">p = ${n2(cmp.position, cmp.position % 1 ? 1 : 0)}</b></div>
      <div><span>rank = (p − 1) / (n − 1)</span><b class="num">(${n2(cmp.position, cmp.position % 1 ? 1 : 0)} − 1) / (${cmp.n} − 1) = ${n2(raw, 3)}</b></div>
      ${cmp.higher_is_better ? `<div><span>higher is better</span><b class="num">${n2(cmp.rank, 3)}</b></div>` : `<div><span>lower is better → flip</span><b class="num">1 − ${n2(raw, 3)} = ${n2(cmp.rank, 3)}</b></div>`}
      <div class="res"><span>points</span><b class="num">${n2(cmp.rank * 100, 1)}</b></div>
    </div>` : `<p class="muted">No value for this indicator - it is left out, not counted as zero.</p>`}`;

  const pillarBlock = `<div class="calc">${t.pillars.filter(p => p.terms.length).map(p => {
      const have = p.terms.filter(x => x.points != null);
      const sumW = have.reduce((a, x) => a + x.weight, 0);
      return `<div class="calc-p"><span><span class="sw" style="background:${col(p.category)}"></span>${catName(p.category)}
          ${have.length < p.terms.length ? `<em class="muted small"> · ${p.terms.length - have.length} without data, left out</em>` : ""}</span>
        <b class="num">${have.length ? `(${have.map(x => `${x.weight}×${n2(x.points, 1)}`).join(" + ")}) / ${sumW} = ` : ""}${p.score == null ? "no score" : n2(p.score, 1)}</b></div>`;
    }).join("")}</div>`;

  const tw = t.total.weights, pill = t.pillars.filter(p => p.score != null && tw[p.category]);
  const totalBlock = `<div class="calc"><div class="res"><span>total</span><b class="num">(${pill.map(p => `${tw[p.category]}×${n2(p.score, 1)}`).join(" + ")}) / ${pill.reduce((a, p) => a + tw[p.category], 0)} = ${c.total_score == null ? "no score" : n2(c.total_score, 1)}</b></div>
    <div><span>position in the ranking</span><b class="num">#${c.position ?? "–"} of ${state.score.scored}</b></div></div>`;

  const held = fund.status === "held";
  const fundBlock = !held ? `<div class="calc"><div class="res"><span>${esc(fund.reason)}</span><b class="num">0%</b></div></div>` : `<div class="calc">
      <div><span>equal weight</span><b class="num">1 / ${fund.companies} = ${pct(fund.benchmark, 3)}</b></div>
      <div><span>minus fossil fuels & tobacco (${fund.held_companies} left)</span><b class="num">${pct(fund.eligible, 3)}</b></div>
      ${s.method === "tilt" ? `<div><span>distance from average, z</span><b class="num">(${n2(fund.total_score, 1)} − ${n2(fund.mean, 1)}) / ${n2(fund.std, 1)} = ${signed(fund.z, 2)}</b></div>
      <div><span>tilt</span><b class="num">× e<sup>${s.tilt_strength} × ${signed(fund.z, 2)}</sup> = × ${n2(fund.tilt_factor, 3)} → ${pct(fund.tilted, 3)}</b></div>` : `<div><span>exclude the worst ${pct(s.exclude_bottom_pct, 0)}</span><b class="num">${pct(fund.tilted, 3)}</b></div>`}
      ${s.sector_neutral ? `<div><span>${esc(fund.sector)} keeps its size</span><b class="num">× ${pct(fund.sector_eligible, 2)} / ${pct(fund.sector_tilted, 2)} = ${pct(fund.sector_neutral, 3)}</b></div>` : ""}
      <div><span>cap ${pct(s.max_weight, 0)}</span><b class="num">${fund.capped >= s.max_weight - 1e-9 ? "capped" : "not reached"} → ${pct(fund.capped, 3)}</b></div>
      <div class="res"><span>of $1 billion${fund.holding !== c.ticker ? ` (as ${esc(fund.holding)})` : ""}</span><b class="num">${usd(fund.weight * fund.fund_usd)}</b></div>
    </div>`;

  const catalog = HOME_ORDER.map(([id, name]) => `<tr class="grp"><th colspan="4"><span class="sw" style="background:${col(id)}"></span>${name} <span class="muted">· ${esc(PILLARS[id].q)}</span></th></tr>` +
    state.meta.indicators.filter(m => m.category === id).map(m => `<tr><td title="${esc(m.description)}"><b>${esc(short(m.id))}</b><div class="sub">${esc(m.name)}</div></td>
      <td class="small">${m.higher_is_better ? "↑ better" : "↓ better"}</td>
      <td class="r num small">${Math.round(m.companies / state.meta.companies * 100)}%</td>
      <td class="small muted">${esc(WEAK[m.id] || "–")}</td></tr>`).join("")).join("");

  $("#view-method").innerHTML = `
    <div class="head"><p class="eyebrow">Method</p>
      <h2>From a public document to dollars, step by step.</h2>
      <p class="lead">One company, real numbers, your weights. No model, no estimates.</p></div>
    <div class="filters"><select id="m-company" aria-label="Company">${opts}</select></div>

    <ol class="msteps">
      ${step(1, "Collect", "", sourceTable)}
      ${step(2, "Rank within the sector", "", rankBlock)}
      ${step(3, "Pillar scores", "Weighted mean of the points", pillarBlock)}
      ${step(4, "Total", "Weighted mean of the pillars", totalBlock)}
      ${step(5, "Fund weight", "", fundBlock)}
      ${step(6, "Test it", "", `<div class="chips"><button type="button" data-go="evidence/A">Caught later</button><button type="button" data-go="evidence/B">Robust to weights</button><button type="button" data-go="netzero">Carbon price</button></div>`)}
    </ol>

    <details class="how"><summary>All ${state.meta.indicators.length} indicators · coverage · weak spots</summary>
      <div class="table-wrap"><table class="mini wide catalog"><thead><tr><th>Indicator</th><th>Direction</th><th class="r">Coverage</th><th>Weak spot</th></tr></thead><tbody>${catalog}</tbody></table></div></details>
    <details class="how"><summary>What we do not claim</summary><ul>
      <li>US sources only: foreign plants, lawsuits and pay are mostly invisible.</li>
      <li>Targets are not emissions; disclosure is not behaviour.</li>
      <li>No AI produces a score - rerun the code, get the same numbers.</li>
      <li>A sustainability-tilted index fund, not an impact fund.</li>
    </ul></details>`;

  $("#m-company").onchange = e => { TRACE.ticker = e.target.value; TRACE.data = null; renderMethod(); };
  $$("#view-method .chips button[data-ind]").forEach(b => b.onclick = () => { TRACE.ind = b.dataset.ind; renderMethod(); });
  $$("#view-method .chips button[data-go]").forEach(b => b.onclick = () => { const [v, sub] = b.dataset.go.split("/"); go(v, sub); });
}
