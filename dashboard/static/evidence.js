/* Evidence tab - dashboard/static/evidence.js (loaded after app.js, uses its helpers).
   Three exhibits that argue the score MEANS something. A and B are computed live on the weights
   chosen on the start page: POST /api/evidence runs checks/caught_later.py and
   checks/weight_robustness.py (the same code as `python run.py verify`). C calls POST /api/audit
   (checks/_audit.py) twice: first everything local (10-K sentences, EPA record), then the news on its
   own, so a slow news service never blocks the page. Only displays. */

const sc = (d0, d1, r0, r1) => v => r0 + (v - d0) / (d1 - d0 || 1) * (r1 - r0);
const EX = [
  { id: "A", check: "caught_later", title: "Caught later" },
  { id: "B", check: "weight_robustness", title: "Robust to weights" },
  { id: "C", check: null, title: "Audit a company" },
];
const AUD = { ticker: null, data: null, news: null, loading: false };
const THEME = { planet: ["Environmental Factors", "--env"], people: ["Social Factors", "--soc"], legal: ["Lawsuits & fines", "--ink"] };

/* A - caught later: share fined per within-sector quintile of the 2021 score */
function chartQuintiles(rows) {
  const W = 1120, H = 230, L = 44, R = 10, T = 26, B = 36, max = Math.max(...rows.map(r => r.share || 0), 0.05);
  const bw = (W - L - R) / rows.length, y = sc(0, max * 1.12, H - B, T);
  let g = `<line class="grid" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>`;
  rows.forEach((r, i) => {
    const x = L + i * bw + bw * .3, w = bw * .4, top = y(r.share || 0), edge = i === 0 || i === rows.length - 1;
    g += `<rect class="${i === 0 ? "q-bad" : i === rows.length - 1 ? "q-good" : "q-mid"}" x="${x}" y="${top}" width="${w}" height="${H - B - top}" rx="4"><title>${r.group}: ${r.hits} of ${r.companies} companies fined</title></rect>
      <text class="big" x="${x + w / 2}" y="${top - 10}" text-anchor="middle">${Math.round(r.share * 100)}%</text>
      <text class="strong" x="${x + w / 2}" y="${H - B + 22}" text-anchor="middle">${i === 0 ? "Worst fifth" : i === rows.length - 1 ? "Best fifth" : r.group.split(" ")[0]}</text>`;
  });
  return svg(W, H, g, "Share of companies fined by the EPA 2022-2025, by 2021 score group");
}

/* B - robustness: histogram of rank correlations */
function chartHistogram(counts, median) {
  const W = 1120, H = 170, L = 10, R = 10, T = 26, B = 30, max = Math.max(...counts, 1), bw = (W - L - R) / counts.length;
  const y = sc(0, max, H - B, T), xm = L + median * (W - L - R);
  let g = `<line class="grid" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>`;
  counts.forEach((c, i) => {
    const lo = i / counts.length;
    g += `<rect rx="3" class="${lo >= 0.7 ? "q-good" : "q-mid"}" x="${L + i * bw + 1}" y="${y(c)}" width="${bw - 2}" height="${H - B - y(c)}"><title>${c} runs with correlation ${lo.toFixed(2)}–${(lo + 1 / counts.length).toFixed(2)}</title></rect>`;
  });
  g += `<line class="ref" x1="${xm}" x2="${xm}" y1="${T - 10}" y2="${H - B}"/><text class="strong" x="${xm - 6}" y="${T - 2}" text-anchor="end">median ${median.toFixed(2)}</text>`;
  [[0, "0 · unrelated"], [.5, "0.5"], [1, "1 · identical"]].forEach(([v, t]) => g += `<text x="${L + v * (W - L - R)}" y="${H - 8}" text-anchor="${v === 0 ? "start" : v === 1 ? "end" : "middle"}">${t}</text>`);
  return svg(W, H, g, "How similar each random-weight ranking is to yours");
}

function exhibitA(c) {
  const n = c.numbers;
  return `<div class="claim"><span class="v num">${n.worst_to_best_ratio ? n.worst_to_best_ratio.toFixed(1) + "×" : "–"}</span>
      <p>as many EPA fines in ${n.outcome_years[0]}–${n.outcome_years[1]} for the companies rated worst in their sector - using only data from ${n.as_of}.</p></div>
    <figure class="fig">${chartQuintiles(n.total_score)}<figcaption>${n.companies} companies · ${n.fined} fined · share fined per fifth</figcaption></figure>
    <details class="how"><summary>How it's tested</summary>
      <p>Indicators rebuilt as they stood at the end of ${n.as_of} (${n.indicators_used.map(i => esc(short(i))).join(", ")}), scored with your weights, ranked within each sector. The fines came later and were not an input.
      Limits: bigger companies run more plants; employee lawsuits showed no such pattern, so we do not claim one.</p></details>
    <h3 class="h3">Largest fines that followed</h3>
    <table class="mini"><tbody>${c.rows.slice(0, 6).map(r => `<tr><td class="tk-c">${esc(r.ticker)}</td><td class="r num"><b>${usd(r.value)}</b></td><td>${esc((r.detail.match(/\(([^)]*)\)\s*$/) || [, r.ticker])[1])}</td><td class="muted small">${esc(r.detail.replace(/ - EPA case .*$/, ""))}</td><td class="r"><a href="${esc(r.url)}" target="_blank" rel="noopener">case ↗</a></td></tr>`).join("")}</tbody></table>`;
}

function exhibitB(c) {
  const n = c.numbers, det = n.companies_detail;
  const top = det.filter(d => d.top_share >= 0.9).slice(0, 8), bottom = det.filter(d => d.bottom_share >= 0.9).slice(-8).reverse();
  const list = rows => rows.map(d => `<tr><td>${esc(d.name)}</td><td class="r num muted">${esc(d.ticker)}</td></tr>`).join("");
  return `<div class="claim"><span class="v num">${Math.round(n.top50_stay_share * 100)}%</span>
      <p>of the top 50 stay in the top fifth under ${n.runs.toLocaleString("en-US")} random weightings.</p></div>
    <figure class="fig">${chartHistogram(n.rho_histogram, n.median_rho)}<figcaption>Rank correlation of each random weighting with yours</figcaption></figure>
    <div class="grid2">
      <div><h3 class="h3">Always on top <span class="muted lg">${n.always_top} companies</span></h3><table class="mini"><tbody>${list(top) || '<tr><td class="muted">none</td></tr>'}</tbody></table></div>
      <div><h3 class="h3">Always at the bottom <span class="muted lg">${n.always_bottom} companies</span></h3><table class="mini"><tbody>${list(bottom) || '<tr><td class="muted">none</td></tr>'}</tbody></table></div>
    </div>`;
}

function mark(text, keywords) {
  let out = esc(text);
  (keywords || []).forEach(k => { out = out.replace(new RegExp(`\\b(\\w*${k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\w*)`, "gi"), "<mark>$1</mark>"); });
  return out.replace(/<mark><mark>(.*?)<\/mark><\/mark>/g, "<mark>$1</mark>");
}

function exhibitC() {
  const opts = (state.score ? state.score.rows : []).slice().sort((a, b) => (a.name || "").localeCompare(b.name || ""))
    .map(r => `<option value="${esc(r.name)} (${r.ticker})"></option>`).join("");
  const a = AUD.data;
  let out = `<p class="muted">What the company says in its own annual report, what the regulator recorded, what the news says.</p>`;
  if (AUD.loading) out = `<p class="muted">Reading ${esc(AUD.ticker)}'s 10-K and EPA record…</p>`;
  else if (a && a.error) out = `<p class="muted">${esc(a.error)}</p>`;
  else if (a) {
    const row = state.score.rows.find(r => r.ticker === a.ticker) || {};
    const cases = a.regulators.epa_cases, ghg = a.regulators.ghg, tenk = a.tenk || { passages: [] };
    const fined = cases.reduce((s, k) => s + k.penalty_usd, 0);
    const byTheme = t => tenk.passages.filter(p => p.theme === t);
    const news = AUD.news;
    out = `<div class="aud-head"><div><p class="eyebrow">${a.ticker} · ${esc(a.sector)}</p><h3 class="h2">${esc(a.name)}</h3></div>
        <div class="scores">${[["total", "Total", null], ...HOME_ORDER.map(([id, n]) => [id, n, CATS.find(k => k[0] === id)[2]])].map(([id, nm, col]) => `<div><span class="label">${col ? `<span class="sw" style="background:var(${col})"></span>` : ""}${nm}</span><span class="v num">${f1(row[`${id}_score`])}</span></div>`).join("")}</div></div>

      <div class="figures">
        <div class="fig-n"><span class="label">Direct emissions ${ghg ? ghg.year : ""}</span><span class="v num">${ghg ? (ghg.tonnes >= 1e6 ? (ghg.tonnes / 1e6).toFixed(1) + " Mt" : Math.round(ghg.tonnes / 1e3) + " kt") : "–"}</span><span class="t">${ghg ? `${ghg.per_musd.toFixed(0)} t per $M revenue · <a href="${ghg.url}" target="_blank" rel="noopener">EPA ↗</a>` : "no US plant above 25 kt"}</span></div>
        <div class="fig-n"><span class="label">EPA penalties since 2016</span><span class="v num">${cases.length ? usd(fined) : "$0"}</span><span class="t">${cases.length} case${cases.length === 1 ? "" : "s"}</span></div>
        <div class="fig-n"><span class="label">Annual report</span><span class="v num">${tenk.passages.length}</span><span class="t">relevant sentences · ${tenk.url ? `<a href="${esc(tenk.url)}" target="_blank" rel="noopener">10-K ↗</a>` : "no 10-K on file"}</span></div>
      </div>

      <div class="cols3">${Object.entries(THEME).map(([t, [name, col]]) => `<section><h3 class="h3"><span class="sw" style="background:var(${col})"></span>${name}</h3>
          ${byTheme(t).length ? byTheme(t).map(p => `<blockquote class="quote"><p>“${mark(p.text, p.keywords)}”</p></blockquote>`).join("") : '<p class="muted small">Nothing specific in the 10-K.</p>'}
          ${t === "legal" && cases.length ? `<table class="mini"><tbody>${cases.slice(0, 4).map(k => `<tr><td class="num">${k.year}</td><td class="small">${esc(k.defendant)}</td><td class="r num">${usd(k.penalty_usd)}</td><td class="r"><a href="${k.url}" target="_blank" rel="noopener">↗</a></td></tr>`).join("")}</tbody></table>` : ""}
        </section>`).join("")}</div>

      <section class="news-s"><h3 class="h3">In the news <span class="muted lg">last 3 months</span></h3>
        ${!news ? `<p class="muted small">Loading headlines…</p>`
          : news.articles && news.articles.length ? `<ul class="news">${news.articles.slice(0, 6).map(n => `<li><a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a><span class="muted small">${esc(n.domain)} · ${n.date.slice(0, 4)}-${n.date.slice(4, 6)}-${n.date.slice(6, 8)}</span></li>`).join("")}</ul>`
          : `<p class="muted small">News feed unavailable right now.</p>`}
        ${news && news.search_url ? `<a class="ghost" href="${esc(news.search_url)}" target="_blank" rel="noopener">Search the news ↗</a>` : ""}
      </section>`;
  }
  return `<div class="filters"><input type="search" id="aud-search" list="aud-list" placeholder="Search a company or ticker…" aria-label="Search company" value="${esc(AUD.ticker ? `${(state.score.rows.find(r => r.ticker === AUD.ticker) || {}).name || ""} (${AUD.ticker})` : "")}">
    <datalist id="aud-list">${opts}</datalist></div>${out}`;
}

async function runAudit(ticker) {
  AUD.ticker = ticker; AUD.loading = true; AUD.data = null; AUD.news = null;
  if (state.view === "evidence") renderEvidence();
  const data = await postJSON("/api/audit", { ticker, news: false });
  if (AUD.ticker !== ticker) return;
  AUD.data = data; AUD.loading = false;
  if (state.view === "evidence" && state.ex === "C") renderEvidence();
  const news = await postJSON("/api/audit", { ticker, only_news: true });
  if (AUD.ticker !== ticker) return;
  AUD.news = news.news || { articles: [] };
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
  $("#view-evidence").innerHTML = `<div class="head"><p class="eyebrow">Evidence</p><h2>Does the score mean something?</h2></div>
    ${nav}
    <article class="exhibit">
      ${c && c.live ? `<p class="live"><span class="dot"></span>live on your weights · ${c.seconds} s</p>` : ""}
      ${content}
    </article>`;
  $$("#view-evidence .subnav button").forEach(b => b.onclick = () => go("evidence", b.dataset.ex));
  if (e.id === "C") {
    const pick = ev => {
      const v = ev.target.value.trim(), m = v.match(/\(([A-Z.\-]+)\)$/), q = v.toUpperCase();
      const row = m ? state.score.rows.find(r => r.ticker === m[1]) : state.score.rows.find(r => r.ticker === q || (r.name || "").toUpperCase() === q);
      if (row && row.ticker !== AUD.ticker) runAudit(row.ticker);
    };
    $("#aud-search").oninput = pick; $("#aud-search").onchange = pick;
    if (!AUD.ticker) runAudit(state.score.rows.find(r => r.ticker === "NUE") ? "NUE" : state.score.rows[0].ticker);
  }
}
