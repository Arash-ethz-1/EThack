/* Evidence tab - dashboard/static/evidence.js (loaded after app.js, uses its helpers).
   Three exhibits that argue the score MEANS something. Results come from
   GET /api/checks (checks/caught_later.py, checks/weight_robustness.py, written by
   `python run.py verify`) and POST /api/audit (checks/_audit.py). Only displays. */

const sc = (d0, d1, r0, r1) => v => r0 + (v - d0) / (d1 - d0 || 1) * (r1 - r0);
const svg = (w, h, g, label) => `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="${label}">${g}</svg>`;
const usd = v => v == null ? "–" : v >= 1e9 ? `$${(v / 1e9).toFixed(2)}bn` : v >= 1e6 ? `$${(v / 1e6).toFixed(1)}m` : `$${Math.round(v).toLocaleString("en-US")}`;
const EX = [
  { id: "A", check: "caught_later", title: "Low scores get caught later", kicker: "Does the score predict real misconduct?" },
  { id: "B", check: "weight_robustness", title: "The ranking survives disagreement", kicker: "Does it depend on our weights?" },
  { id: "C", check: null, title: "Audit any company", kicker: "Check it yourself" },
];
const AUD = { ticker: null, data: null, loading: false };

function check(id) { return (state.checks.checks || []).find(c => c.id === id); }
function statusOf(ex) { if (!ex.check) return "live"; const c = check(ex.check); return !c || c.status === "not_run" ? "not run" : c.status; }

function renderIndex() {
  $("#index").innerHTML = EX.map(e => `<li><button type="button" data-ex="${e.id}" aria-current="${state.ex === e.id}">
    <span class="ex">${e.id}</span><span class="t">${esc(e.title)}<small>${esc(e.kicker)}</small></span></button></li>`).join("");
  $$("#index button").forEach(b => b.onclick = () => { state.ex = b.dataset.ex; renderIndex(); renderExhibit(); });
}

function pending(cmd) { return `<div class="pend"><p style="margin:0 0 6px">Not run yet.</p><code style="font-size:12px">${esc(cmd)}</code></div>`; }

/* A - caught later: share fined per within-sector quintile of the 2021 score */
function chartQuintiles(rows) {
  const W = 620, H = 260, L = 44, R = 10, T = 16, B = 44, max = Math.max(...rows.map(r => r.share || 0), 0.05);
  const bw = (W - L - R) / rows.length, y = sc(0, max * 1.15, H - B, T);
  let g = "";
  [0, max / 2, max].forEach(v => g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${Math.round(v * 100)}%</text>`);
  rows.forEach((r, i) => {
    const x = L + i * bw + bw * .18, w = bw * .64, top = y(r.share || 0), edge = i === 0 || i === rows.length - 1;
    g += `<rect class="${edge ? "q-edge" : "q-mid"}" x="${x}" y="${top}" width="${w}" height="${H - B - top}" rx="3"><title>${r.group}: ${r.hits} of ${r.companies} companies fined (${Math.round(r.share * 100)}%)</title></rect>
      <text class="strong" x="${x + w / 2}" y="${top - 6}" text-anchor="middle">${Math.round(r.share * 100)}%</text>
      <text x="${x + w / 2}" y="${H - B + 16}" text-anchor="middle">${r.group.replace(" worst", "").replace(" best", "")}</text>
      <text x="${x + w / 2}" y="${H - B + 30}" text-anchor="middle" class="muted-t">${i === 0 ? "worst fifth" : i === rows.length - 1 ? "best fifth" : ""}</text>`;
  });
  return svg(W, H, g, "Share of companies fined by the EPA 2022-2025, by 2021 score group");
}

/* B - robustness: histogram of rank correlations */
function chartHistogram(counts) {
  const W = 620, H = 200, L = 30, R = 10, T = 10, B = 30, max = Math.max(...counts, 1), bw = (W - L - R) / counts.length;
  const y = sc(0, max, H - B, T);
  let g = "";
  counts.forEach((c, i) => {
    const lo = i / counts.length;
    g += `<rect class="${lo >= 0.7 ? "q-edge" : "q-mid"}" x="${L + i * bw + 1}" y="${y(c)}" width="${bw - 2}" height="${H - B - y(c)}" rx="2"><title>${c} runs with correlation ${lo.toFixed(2)}–${(lo + 1 / counts.length).toFixed(2)}</title></rect>`;
  });
  [0, .25, .5, .75, 1].forEach(v => g += `<text x="${L + v * (W - L - R)}" y="${H - 10}" text-anchor="middle">${v}</text>`);
  return svg(W, H, g, "How similar each random-weight ranking is to ours");
}

function exhibitA() {
  const c = check("caught_later");
  if (!c || c.status === "not_run") return pending("python run.py verify caught_later");
  const n = c.numbers;
  return `<figure class="fig">${chartQuintiles(n.total_score)}
      <figcaption>Share of companies fined by the EPA in ${n.outcome_years[0]}–${n.outcome_years[1]}, by the score our method would have given them with data up to ${n.as_of}.
      Companies ranked within their own sector, ${n.companies} companies, ${n.fined} fined.</figcaption></figure>
    <div class="ev-cols">
      <div><h4>How to read it</h4><p>We rebuilt every indicator as it stood at the end of ${n.as_of} and scored the S&amp;P 500 with exactly the dashboard's code.
      The fines were not an input: they came later. If the score only reflected polished reports, all five bars would be the same height.</p>
      <p class="muted">Indicators available in ${n.as_of}: ${n.indicators_used.map(i => esc(META(i).name)).join(", ")}.</p></div>
      <div><h4>Honest limits</h4><p>Bigger companies run more plants and so get inspected more; our score is size-neutral, the outcome is not. We also tested federal employee lawsuits - no pattern there, so we do not claim one.</p></div>
    </div>
    <h4 class="ev-h">Largest fines that followed</h4>
    <div class="outs">${c.rows.slice(0, 10).map(r => `<div><span class="mono">${esc(r.ticker)}</span><span class="num">${usd(r.value)}</span><span>${esc(r.detail)} · <a href="${esc(r.url)}" target="_blank" rel="noopener">EPA case ↗</a></span></div>`).join("")}</div>`;
}

function exhibitB() {
  const c = check("weight_robustness");
  if (!c || c.status === "not_run") return pending("python run.py verify weight_robustness");
  const n = c.numbers, det = n.companies_detail;
  const top = det.filter(d => d.top_share >= 0.9).slice(0, 12), bottom = det.filter(d => d.bottom_share >= 0.9).slice(-12).reverse();
  const list = (rows, key) => rows.map(d => `<div><span class="mono">${esc(d.ticker)}</span><span>${esc(d.name)}</span><span class="num">${Math.round(d[key] * 100)}%</span></div>`).join("");
  return `<figure class="fig">${chartHistogram(n.rho_histogram)}
      <figcaption>${n.runs.toLocaleString("en-US")} rankings, each with random weights for every category and every indicator, compared with ours (1 = identical order). Median ${n.median_rho}, 95% of runs above ${n.rho_p5}.</figcaption></figure>
    <div class="ev-cols">
      <div><h4>In the top fifth under ≥ 90% of weightings</h4><div class="outs slim">${list(top, "top_share") || '<span class="muted">none</span>'}</div>
        <p class="muted">${n.always_top} companies in total.</p></div>
      <div><h4>In the bottom fifth under ≥ 90% of weightings</h4><div class="outs slim">${list(bottom, "bottom_share") || '<span class="muted">none</span>'}</div>
        <p class="muted">${n.always_bottom} companies in total.</p></div>
    </div>`;
}

function exhibitC() {
  const opts = (state.score ? state.score.rows : []).slice().sort((a, b) => (a.name || "").localeCompare(b.name || ""))
    .map(r => `<option value="${r.ticker}"${r.ticker === AUD.ticker ? " selected" : ""}>${esc(r.name)} (${r.ticker})</option>`).join("");
  const a = AUD.data;
  let body = `<p class="muted">Pick a company: you get the sentences from its own filings that our numbers come from, its record with the US environmental regulator, and recent news - so you can judge the score yourself.</p>`;
  if (AUD.loading) body = `<p class="muted">Collecting filings, regulator records and news for ${esc(AUD.ticker)}… (the news service allows one request every 5 seconds)</p>`;
  else if (a) {
    const row = state.score.rows.find(r => r.ticker === a.ticker) || {};
    const cases = a.regulators.epa_cases, ghg = a.regulators.ghg, news = a.news || {};
    body = `<div class="aud-head"><div><span class="label mono">${a.ticker} · ${esc(a.sector)}</span><h3>${esc(a.name)}</h3><span class="muted">${esc(a.sub_industry || "")}</span></div>
        <div class="score-line"><div><span class="label">Total</span><span class="v">${f1(row.total_score)}</span></div>${CATS.map(([id, nm, col]) => `<div><span class="label"><span class="sw" style="background:var(${col})"></span>${nm}</span><span class="v">${f1(row[`${id}_score`])}</span></div>`).join("")}</div></div>
      <div class="aud-grid">
        <section><h4>In its own words <small>SEC filings</small></h4>${a.filings.length ? a.filings.map(q => `<blockquote><q>${esc(q.quote)}</q>
          <footer>${esc(q.name)} · FY ${q.year} · <a href="${esc(q.source_url)}" target="_blank" rel="noopener">filing ↗</a></footer></blockquote>`).join("") : '<p class="muted">No extracted quotes for this company.</p>'}</section>
        <section><h4>On the regulator's record <small>EPA</small></h4>
          ${ghg ? `<p><b>${Math.round(ghg.tonnes).toLocaleString("en-US")} t CO₂e</b> from large US facilities in ${ghg.year} - ${ghg.per_musd.toFixed(0)} t per $M revenue. <a href="${ghg.url}" target="_blank" rel="noopener">GHGRP ↗</a></p>` : `<p class="muted">No US facility above EPA's 25,000 t reporting threshold.</p>`}
          ${cases.length ? `<table class="mini"><tbody>${cases.slice(0, 8).map(k => `<tr><td>${k.year}</td><td>${esc(k.defendant)}</td><td class="r num">${usd(k.penalty_usd)}</td><td><a href="${k.url}" target="_blank" rel="noopener">case ↗</a></td></tr>`).join("")}</tbody></table>
            <p class="muted">${cases.length} federal EPA penalt${cases.length === 1 ? "y" : "ies"} since 2016.</p>` : `<p class="muted">No federal EPA civil penalty since 2016.</p>`}</section>
        <section><h4>In the news <small>last 3 months</small></h4>
          ${news.articles && news.articles.length ? `<ul class="news">${news.articles.slice(0, 8).map(n => `<li><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a><span class="muted">${esc(n.domain)} · ${n.date.slice(0, 4)}-${n.date.slice(4, 6)}-${n.date.slice(6, 8)}</span></li>`).join("")}</ul>`
            : `<p class="muted">${esc(news.error || "No matching headlines.")}</p>`}
          ${news.search_url ? `<p><a href="${esc(news.search_url)}" target="_blank" rel="noopener">Search the news yourself ↗</a></p>` : ""}
          <p class="muted small">Headlines are context for a human reader. They never change a score.</p></section>
      </div>`;
  }
  return `<div class="aud-pick"><label><span class="label">Company</span><select id="aud-select"><option value="">Choose…</option>${opts}</select></label>
    <button type="button" class="btn" id="aud-random">Random company</button></div>${body}`;
}

async function runAudit(ticker) {
  AUD.ticker = ticker; AUD.loading = true; AUD.data = null; renderExhibit();
  AUD.data = await postJSON("/api/audit", { ticker });
  AUD.loading = false;
  if (state.ex === "C") renderExhibit();
}

function renderExhibit() {
  const e = EX.find(x => x.id === state.ex) || EX[0];
  const c = e.check ? check(e.check) : null;
  const verdict = e.check ? (c && c.status !== "not_run" ? c.verdict : "") : "";
  const body = e.id === "A" ? exhibitA() : e.id === "B" ? exhibitB() : exhibitC();
  $("#exhibit").innerHTML = `<div class="kicker"><span class="label">Exhibit ${e.id} · ${esc(e.kicker)}</span></div>
    <h3>${esc(e.title)}</h3>${verdict ? `<p class="verdict">${esc(verdict)}</p>` : ""}${body}
    ${e.check ? `<details class="method"><summary>How this is checked</summary><p>Deterministic code, fixed inputs, re-run with <code>python run.py verify ${e.check}</code>. Source: <code>checks/${e.check}.py</code>.${c && c.ran_at ? ` Last run ${esc(c.ran_at)}.` : ""}</p></details>` : ""}`;
  if (e.id === "C") {
    $("#aud-select").onchange = ev => ev.target.value && runAudit(ev.target.value);
    $("#aud-random").onclick = () => { const rows = state.score.rows; runAudit(rows[Math.floor(Math.random() * rows.length)].ticker); };
  }
}
