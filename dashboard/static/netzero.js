/* Net zero tab - dashboard/static/netzero.js (loaded after app.js and portfolio.js, uses their helpers).
   The bonus question: the world commits to net zero as fast as possible; how do you invest $1bn?
   Every number comes from POST /api/netzero (portfolio/transition.py: three funds side by side and a
   carbon price stress test). Only displays. */

const NZ_LINES = [["index", "S&P 500", "l-bench"], ["exclusion", "No fossil fuels", "l-mid"], ["fund", "Net-zero fund", "l-fund"]];

function nzCurve(st) {
  const W = 1120, H = 320, L = 52, R = 180, T = 16, B = 34;
  const top = Math.max(...st.curve.flatMap(p => NZ_LINES.map(([k]) => p[k] || 0))), step = top > 0.08 ? 0.02 : 0.01;
  const maxP = st.prices[st.prices.length - 1], maxV = Math.ceil(top / step) * step + step;
  const x = p => L + (W - L - R) * p / maxP, y = v => T + (H - T - B) * (1 - v / maxV);
  let g = "";
  for (let v = 0; v <= maxV + 1e-9; v += step) g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${Math.round(v * 100)}%</text>`;
  st.prices.forEach(p => g += `<text x="${x(p)}" y="${H - 10}" text-anchor="middle">$${p}</text>`);
  Object.entries(st.reference).forEach(([year, p]) => g += `<line class="ref" x1="${x(p)}" x2="${x(p)}" y1="${T}" y2="${H - B}"/><text class="strong" x="${x(p) + 6}" y="${T + 12}">IEA ${year}</text>`);
  NZ_LINES.forEach(([k, , cls]) => g += `<path class="${cls}" d="${st.curve.map((p, i) => `${i ? "L" : "M"}${x(p.price)},${y(p[k])}`).join("")}"/>`);
  const last = st.curve[st.curve.length - 1];
  const ends = NZ_LINES.map(([k, n]) => ({ k, n, y: y(last[k]), v: last[k] })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 16) ends[i].y = ends[i - 1].y + 16;
  ends.forEach(e => g += `<text class="${e.k === "fund" ? "strong" : ""}" x="${W - R + 10}" y="${e.y + 4}">${e.n} ${(e.v * 100).toFixed(1)}%</text>`);
  st.curve.forEach(p => g += `<rect class="hit" x="${x(p.price) - 20}" y="${T}" width="40" height="${H - T - B}"><title>$${p.price}/t: fund ${(p.fund * 100).toFixed(2)}%, no fossil ${(p.exclusion * 100).toFixed(2)}%, index ${(p.index * 100).toFixed(2)}%</title></rect>`);
  return svg(W, H, g, "Share of pre-tax profit a carbon price would take, by carbon price");
}

/* the story in three bars: index -> sell fossil fuels -> re-weight inside sectors */
function nzSteps(at, excluded) {
  const W = 1120, H = 220, T = 40, B = 56, max = Math.max(at.index, at.exclusion, at.fund) * 1.05;
  const cols = [["index", "S&P 500", "today"], ["exclusion", "1 · Sell oil, gas & tobacco", `${excluded} companies out`], ["fund", "2 · Re-weight inside sectors", "less carbon, more climate targets"]];
  const bw = 160, gap = (W - cols.length * bw) / cols.length;
  let g = `<line class="grid" x1="0" x2="${W}" y1="${H - B}" y2="${H - B}"/>`;
  cols.forEach(([k, label, sub], i) => {
    const x = gap / 2 + i * (bw + gap), h = (H - T - B) * at[k] / max;
    g += `<rect class="${k === "fund" ? "q-good" : k === "index" ? "q-bad" : "q-mid"}" x="${x}" y="${H - B - h}" width="${bw}" height="${h}" rx="4"/>
      <text class="big" x="${x + bw / 2}" y="${H - B - h - 12}" text-anchor="middle">${(at[k] * 100).toFixed(1)}%</text>
      <text class="strong" x="${x + bw / 2}" y="${H - B + 24}" text-anchor="middle">${label}</text>
      <text x="${x + bw / 2}" y="${H - B + 44}" text-anchor="middle">${sub}</text>`;
    if (i) g += `<text class="arrow" x="${x - gap / 2}" y="${H - B - 30}" text-anchor="middle">→</text>`;
  });
  return svg(W, H, g, "Profit a carbon price would take: index, without fossil fuels, net-zero fund");
}

function sectorBars(sectors) {
  const max = Math.max(...sectors.map(s => Math.max(s.fund_usd, s.index_usd)));
  const W = 560, L = 170, R = 70, rowH = 26, H = sectors.length * rowH + 4, x = v => L + (W - L - R) * v / max;
  let g = "";
  sectors.forEach((s, i) => {
    const y = i * rowH + 4;
    g += `<text class="strong" x="${L - 12}" y="${y + 12}" text-anchor="end">${esc(s.sector)}</text>
      <rect class="b-bench" x="${L}" y="${y + 12}" width="${Math.max(0, x(s.index_usd) - L)}" height="4"><title>Index ${usd(s.index_usd)}</title></rect>
      <rect class="b-fund" x="${L}" y="${y + 3}" width="${Math.max(0, x(s.fund_usd) - L)}" height="8"><title>Fund ${usd(s.fund_usd)}</title></rect>
      <text x="${Math.max(x(s.fund_usd), x(s.index_usd)) + 6}" y="${y + 12}">${usd(s.fund_usd)}</text>`;
  });
  return svg(W, H, g, "Dollars per sector, fund vs index");
}

function renderNetZero() {
  const a = state.netzero, el = $("#view-netzero");
  if (!a) { el.innerHTML = `<div class="head"><p class="eyebrow">Net zero</p><h2>Computing…</h2></div>`; postJSON("/api/netzero", {}).then(r => { state.netzero = r; renderNetZero(); }); return; }
  if (a.error) { el.innerHTML = `<p class="muted">${esc(a.error)}</p>`; return; }
  const F = a.funds, st = a.stress, ref = st.reference["2030"], end = st.reference["2050"];
  const at = p => st.curve.find(c => c.price === p), heavy = p => st.heavy_share.find(c => c.price === p);
  const waci = k => F[k].climate.waci_tco2e_per_musd, sbti = k => F[k].climate.sbti_target_share;
  const r = a.risk;
  const row = (label, fmt) => `<tr><th>${label}</th>${["index", "exclusion", "fund"].map(k => `<td class="r num ${k === "fund" ? "hl" : ""}">${fmt(k)}</td>`).join("")}</tr>`;
  const moves = (rows, title) => `<div><h3 class="h3">${title}</h3><table class="mini"><tbody>${rows.map(x => `<tr>
      <td class="co"><b>${esc(x.name || x.ticker)}</b><span class="tk">${esc(x.sector || "")}</span></td>
      <td class="r num"><span class="muted">${usd(x.index_usd)} →</span> <b>${usd(x.usd)}</b></td></tr>`).join("")}</tbody></table></div>`;

  el.innerHTML = `
    <div class="head"><p class="eyebrow">Bonus question · net zero tomorrow, $1 billion to invest</p>
      <h2>Sell the fuel. Re-weight the rest. Keep the market.</h2></div>

    <figure class="fig"><h3 class="h3">Profit a $${ref}/t carbon price would take <span class="muted lg">IEA net-zero price for 2030</span></h3>${nzSteps(at(ref), a.excluded.length)}</figure>

    <div class="figures">
      <div class="fig-n"><span class="label">Carbon intensity</span><span class="v num">${signed((waci("fund") / waci("index") - 1) * 100, 0)}%</span><span class="t">${waci("fund").toFixed(0)} vs ${waci("index").toFixed(0)} tCO₂e/$M</span></div>
      <div class="fig-n"><span class="label">Climate target</span><span class="v num">${pct(sbti("fund"), 0)}</span><span class="t">of the money · index ${pct(sbti("index"), 0)}</span></div>
      <div class="fig-n"><span class="label">At $${end}/t</span><span class="v num">${pct(at(end).fund)}</span><span class="t">profit hit · index ${pct(at(end).index)}</span></div>
      ${r ? `<div class="fig-n"><span class="label">Tracking error</span><span class="v num">${pct(r.tracking_error)}</span><span class="t">still moves like the index</span></div>` : ""}
    </div>

    <figure class="fig"><h3 class="h3">Profit hit by carbon price <span class="muted lg">$0–${end} per tonne</span></h3>${nzCurve(st)}
      <details class="how"><summary>How it's calculated</summary><p>${esc(st.assumptions)} ${st.emitters} companies have a US facility above 25,000 t; ${st.emitters_without_income} without pre-tax income on record are left out.
        Prices: IEA <a href="${esc(st.reference_url)}" target="_blank" rel="noopener">Net Zero by 2050 ↗</a>.</p></details></figure>

    <div class="table-wrap"><table class="compare">
      <thead><tr><th></th>${NZ_LINES.map(([k, n]) => `<th class="r ${k === "fund" ? "hl" : ""}">${n}</th>`).join("")}</tr></thead>
      <tbody>
        ${row("Holdings", k => F[k].holdings)}
        ${row("Score", k => f1(F[k].score))}
        ${row("Carbon intensity", k => waci(k).toFixed(0))}
        ${row("Climate target", k => pct(sbti(k), 0))}
        ${row(`Profit hit at $${ref}/t`, k => pct(at(ref)[k]))}
        ${row(`Profit hit at $${end}/t`, k => pct(at(end)[k]))}
        ${row(`Money in companies losing >${Math.round(st.heavy_threshold * 100)}% of profit`, k => pct(heavy(ref)[k]))}
      </tbody></table></div>

    <div class="grid2">
      <div><h3 class="h3">$1 billion by sector <span class="key fund"></span><span class="lg">Fund</span><span class="key bench"></span><span class="lg">Index</span></h3>${sectorBars(a.sectors)}</div>
      <div><h3 class="h3">Biggest emitters still held <span class="muted lg">less money, still voted</span></h3><table class="mini"><tbody>
        ${st.most_exposed_held.slice(0, 8).map(x => `<tr><td class="co"><b>${esc(x.name || x.ticker)}</b><span class="tk">${(x.tonnes / 1e6).toFixed(1)} Mt CO₂e</span></td>
          <td class="r num"><span class="muted">${usd(x.weight_index * 1e9)} →</span> <b>${usd(x.weight_fund * 1e9)}</b></td></tr>`).join("")}
      </tbody></table></div>
    </div>

    <div class="grid2">
      ${moves(a.added.slice(0, 6), "More money")}
      ${moves(a.cut.slice(0, 6), "Less money")}
    </div>

    <details class="how"><summary>The ${a.excluded.length} excluded companies</summary>
      <table class="mini"><tbody>${a.excluded.map(x => `<tr><td class="co"><b>${esc(x.name)}</b><span class="tk">${esc(x.sub_industry)}</span></td><td class="r num">${usd(x.index_usd)} → $0</td></tr>`).join("")}</tbody></table></details>
    <details class="how"><summary>What this does not claim</summary><ul>
      <li>Not a return forecast - companies may pass costs on or cut emissions.</li>
      <li>Direct emissions of large US plants only; burning oil and gas (Scope 3) is handled by excluding those companies.</li>
      <li>No green-revenue data yet: makers of transition equipment are not overweighted on purpose.</li>
    </ul></details>`;
}
