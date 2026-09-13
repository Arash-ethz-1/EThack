/* Evidence tab - dashboard/static/evidence.js (loaded after app.js, uses its helpers).
   Three exhibits that argue the score MEANS something. A and B are computed live on the weights
   chosen on the start page: POST /api/evidence runs checks/caught_later.py and
   checks/weight_robustness.py (the same code as `python run.py verify`). C calls POST /api/audit
   (checks/_audit.py). Only displays. */

const sc = (d0, d1, r0, r1) => v => r0 + (v - d0) / (d1 - d0 || 1) * (r1 - r0);
const EX = [
  { id: "A", check: "caught_later", title: "Low scores get caught later", kicker: "Does the score predict real misconduct?" },
  { id: "B", check: "weight_robustness", title: "The ranking survives disagreement", kicker: "Does it depend on the weights?" },
  { id: "C", check: null, title: "Audit any company", kicker: "Check it yourself" },
];
const AUD = { ticker: null, data: null, loading: false };

/* A - caught later: share fined per within-sector quintile of the 2021 score */
function chartQuintiles(rows) {
  const W = 1120, H = 300, L = 44, R = 10, T = 22, B = 46, max = Math.max(...rows.map(r => r.share || 0), 0.05);
  const bw = (W - L - R) / rows.length, y = sc(0, max * 1.15, H - B, T);
  let g = "";
  [0, max / 2, max].forEach(v => g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${Math.round(v * 100)}%</text>`);
  rows.forEach((r, i) => {
    const x = L + i * bw + bw * .3, w = bw * .4, top = y(r.share || 0), edge = i === 0 || i === rows.length - 1;
    g += `<rect class="${edge ? "q-edge" : "q-mid"}" x="${x}" y="${top}" width="${w}" height="${H - B - top}"><title>${r.group}: ${r.hits} of ${r.companies} companies fined (${Math.round(r.share * 100)}%)</title></rect>
      <text class="strong" x="${x + w / 2}" y="${top - 7}" text-anchor="middle">${Math.round(r.share * 100)}%</text>
      <text x="${x + w / 2}" y="${H - B + 17}" text-anchor="middle">${r.group.replace(" worst", "").replace(" best", "")}</text>
      <text x="${x + w / 2}" y="${H - B + 32}" text-anchor="middle">${i === 0 ? "worst fifth" : i === rows.length - 1 ? "best fifth" : ""}</text>`;
  });
  return svg(W, H, g, "Share of companies fined by the EPA 2022-2025, by 2021 score group");
}

/* B - robustness: histogram of rank correlations */
function chartHistogram(counts) {
  const W = 1120, H = 220, L = 30, R = 10, T = 10, B = 30, max = Math.max(...counts, 1), bw = (W - L - R) / counts.length;
  const y = sc(0, max, H - B, T);
  let g = `<line class="grid" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>`;
  counts.forEach((c, i) => {
    const lo = i / counts.length;
    g += `<rect class="${lo >= 0.7 ? "q-edge" : "q-mid"}" x="${L + i * bw + 1}" y="${y(c)}" width="${bw - 2}" height="${H - B - y(c)}"><title>${c} runs with correlation ${lo.toFixed(2)}–${(lo + 1 / counts.length).toFixed(2)}</title></rect>`;
  });
  [0, .25, .5, .75, 1].forEach(v => g += `<text x="${L + v * (W - L - R)}" y="${H - 10}" text-anchor="middle">${v}</text>`);
  return svg(W, H, g, "How similar each random-weight ranking is to yours");
}

function exhibitA(c) {
  const n = c.numbers;
  return `<figure class="fig">${chartQuintiles(n.total_score)}
      <figcaption>Share of companies fined by the EPA in ${n.outcome_years[0]}–${n.outcome_years[1]}, by the score your weights would have given them with data up to ${n.as_of}.
      Ranked within their own sector · ${n.companies} companies, ${n.fined} fined.</figcaption></figure>
    <div class="cols">
      <div><h3 class="h3">How to read it</h3><p>Every indicator was rebuilt as it stood at the end of ${n.as_of} and scored with exactly the ranking code, on your weights.
      The fines were not an input: they came later. If the score only reflected polished reports, all five bars would be the same height.</p>
      <p class="small muted">Indicators known in ${n.as_of}: ${n.indicators_used.map(i => esc(META(i).name)).join(", ")}.</p></div>
      <div><h3 class="h3">Honest limits</h3><p>Bigger companies run more plants and get inspected more: the score is size-neutral, the outcome is not. Federal employee lawsuits showed no pattern, so we do not claim one.
      Change the weights on the start page and this exhibit is recomputed for them.</p></div>
    </div>
    <h3 class="h3">Largest fines that followed</h3>
    <table class="mini"><tbody>${c.rows.slice(0, 10).map(r => `<tr><td class="tk-c">${esc(r.ticker)}</td><td class="r num">${usd(r.value)}</td><td class="muted">${esc(r.detail)} · <a href="${esc(r.url)}" target="_blank" rel="noopener">EPA case ↗</a></td></tr>`).join("")}</tbody></table>`;
}

function exhibitB(c) {
  const n = c.numbers, det = n.companies_detail;
  const top = det.filter(d => d.top_share >= 0.9).slice(0, 12), bottom = det.filter(d => d.bottom_share >= 0.9).slice(-12).reverse();
  const list = (rows, key) => rows.map(d => `<tr><td class="tk-c">${esc(d.ticker)}</td><td>${esc(d.name)}</td><td class="r num">${Math.round(d[key] * 100)}%</td></tr>`).join("");
  return `<figure class="fig">${chartHistogram(n.rho_histogram)}
      <figcaption>${n.runs.toLocaleString("en-US")} rankings, each with random weights for every pillar and every indicator you kept, compared with yours (1 = identical order). Median ${n.median_rho}, 95% of runs above ${n.rho_p5}.</figcaption></figure>
    <div class="cols">
      <div><h3 class="h3">Top fifth under ≥ 90% of weightings</h3><table class="mini"><tbody>${list(top, "top_share") || '<tr><td class="muted">none</td></tr>'}</tbody></table>
        <p class="small muted">${n.always_top} companies in total.</p></div>
      <div><h3 class="h3">Bottom fifth under ≥ 90% of weightings</h3><table class="mini"><tbody>${list(bottom, "bottom_share") || '<tr><td class="muted">none</td></tr>'}</tbody></table>
        <p class="small muted">${n.always_bottom} companies in total.</p></div>
    </div>`;
}

function exhibitC() {
  const opts = (state.score ? state.score.rows : []).slice().sort((a, b) => (a.name || "").localeCompare(b.name || ""))
    .map(r => `<option value="${r.ticker}"${r.ticker === AUD.ticker ? " selected" : ""}>${esc(r.name)} (${r.ticker})</option>`).join("");
  const a = AUD.data;
  let out = `<p class="muted">Pick a company: the sentences from its own filings that our numbers come from, its record with the US environmental regulator, and recent news - so you can judge the score yourself.</p>`;
  if (AUD.loading) out = `<p class="muted">Collecting filings, regulator records and news for ${esc(AUD.ticker)}… (the news service allows one request every 5 seconds)</p>`;
  else if (a && a.error) out = `<p class="muted">${esc(a.error)}</p>`;
  else if (a) {
    const row = state.score.rows.find(r => r.ticker === a.ticker) || {};
    const cases = a.regulators.epa_cases, ghg = a.regulators.ghg, news = a.news || {};
    out = `<div class="aud-head"><div><p class="eyebrow">${a.ticker} · ${esc(a.sector)} · ${esc(a.sub_industry || "")}</p><h3 class="h2">${esc(a.name)}</h3></div>
        <div class="scores">${[["total", "Total", null], ...CATS].map(([id, nm, col]) => `<div><span class="label">${col ? `<span class="sw" style="background:var(${col})"></span>` : ""}${nm}</span><span class="v num">${f1(row[`${id}_score`])}</span></div>`).join("")}</div></div>
      <div class="cols3">
        <section><h3 class="h3">In its own words <span class="muted">SEC filings</span></h3>${a.filings.length ? a.filings.map(q => `<blockquote class="quote"><p>${esc(q.quote)}</p>
          <footer>${esc(q.name)} · FY ${q.year} · <a href="${esc(q.source_url)}" target="_blank" rel="noopener">filing ↗</a></footer></blockquote>`).join("") : '<p class="muted">No extracted quotes for this company.</p>'}</section>
        <section><h3 class="h3">On the regulator's record <span class="muted">EPA</span></h3>
          ${ghg ? `<p><b class="num">${Math.round(ghg.tonnes).toLocaleString("en-US")} t CO₂e</b> from large US facilities in ${ghg.year} - ${ghg.per_musd.toFixed(0)} t per $M revenue. <a href="${ghg.url}" target="_blank" rel="noopener">GHGRP ↗</a></p>` : `<p class="muted">No US facility above EPA's 25,000 t reporting threshold.</p>`}
          ${cases.length ? `<table class="mini"><tbody>${cases.slice(0, 8).map(k => `<tr><td class="num">${k.year}</td><td>${esc(k.defendant)}</td><td class="r num">${usd(k.penalty_usd)}</td><td><a href="${k.url}" target="_blank" rel="noopener">case ↗</a></td></tr>`).join("")}</tbody></table>
            <p class="small muted">${cases.length} federal EPA penalt${cases.length === 1 ? "y" : "ies"} since 2016.</p>` : `<p class="muted">No federal EPA civil penalty since 2016.</p>`}</section>
        <section><h3 class="h3">In the news <span class="muted">last 3 months</span></h3>
          ${news.articles && news.articles.length ? `<ul class="news">${news.articles.slice(0, 8).map(n => `<li><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a><span class="muted small">${esc(n.domain)} · ${n.date.slice(0, 4)}-${n.date.slice(4, 6)}-${n.date.slice(6, 8)}</span></li>`).join("")}</ul>`
            : `<p class="muted">${esc(news.error || "No matching headlines.")}</p>`}
          ${news.search_url ? `<p><a href="${esc(news.search_url)}" target="_blank" rel="noopener">Search the news yourself ↗</a></p>` : ""}
          <p class="small muted">Headlines are context for a human reader. They never change a score.</p></section>
      </div>`;
  }
  return `<div class="filters"><select id="aud-select" aria-label="Company"><option value="">Choose a company…</option>${opts}</select>
    <button type="button" class="ghost" id="aud-random">Random company</button></div>${out}`;
}

async function runAudit(ticker) {
  AUD.ticker = ticker; AUD.loading = true; AUD.data = null;
  if (state.view === "evidence") renderEvidence();
  AUD.data = await postJSON("/api/audit", { ticker });
  AUD.loading = false;
  if (state.view === "evidence" && state.ex === "C") renderEvidence();
}

async function renderEvidence() {
  const e = EX.find(x => x.id === state.ex) || EX[0];
  const c = e.check ? state.evidence[e.check] : null;
  const nav = `<nav class="subnav" aria-label="Exhibits">${EX.map(x => `<button type="button" data-ex="${x.id}" aria-current="${x.id === e.id}"><span class="num">${x.id}</span>${esc(x.title)}</button>`).join("")}</nav>`;
  let content;
  if (e.check && !c) {
    content = `<p class="muted">Computing on your weights…</p>`;
    postJSON("/api/evidence", body({ check: e.check })).then(r => { state.evidence[e.check] = r; if (state.view === "evidence" && state.ex === e.id) renderEvidence(); });
  } else if (c && c.error) content = `<p class="muted">${esc(c.error)}</p>`;
  else content = e.id === "A" ? exhibitA(c) : e.id === "B" ? exhibitB(c) : exhibitC();
  $("#view-evidence").innerHTML = `<div class="head"><p class="eyebrow">Evidence</p><h2>A score is only worth something if it means something.</h2></div>
    ${nav}
    <article class="exhibit">
      <p class="eyebrow">Exhibit ${e.id} · ${esc(e.kicker)}</p>
      ${c && c.verdict ? `<p class="verdict">${esc(c.verdict)}</p>` : `<p class="verdict">${esc(e.title)}</p>`}
      ${c && c.live ? `<p class="live"><span class="dot"></span>Computed live on your weights (${esc(weightsText())}) in ${c.seconds} s · <code>checks/${e.check}.py</code></p>` : ""}
      ${content}
    </article>`;
  $$("#view-evidence .subnav button").forEach(b => b.onclick = () => go("evidence", b.dataset.ex));
  if (e.id === "C") {
    $("#aud-select").onchange = ev => ev.target.value && runAudit(ev.target.value);
    $("#aud-random").onclick = () => { const rows = state.score.rows; runAudit(rows[Math.floor(Math.random() * rows.length)].ticker); };
  }
}
