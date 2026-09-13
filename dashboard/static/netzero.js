/* Net zero tab - dashboard/static/netzero.js (loaded after app.js and portfolio.js, uses their helpers).
   The bonus question: the world commits to net zero as fast as possible; how do you invest $1bn?
   Every number comes from POST /api/netzero (portfolio/transition.py: three funds side by side and a
   carbon price stress test). Only displays. */

const NZ_LINES = [["index", "S&P 500 (equal weight)", "l-bench"], ["exclusion", "Without fossil fuels & tobacco", "l-mid"], ["fund", "Our net-zero fund", "l-fund"]];

function nzCurve(st) {
  const W = 1120, H = 320, L = 52, R = 210, T = 16, B = 34;
  const top = Math.max(...st.curve.flatMap(p => NZ_LINES.map(([k]) => p[k] || 0))), step = top > 0.08 ? 0.02 : 0.01;
  const maxP = st.prices[st.prices.length - 1], maxV = Math.ceil(top / step) * step + step;
  const x = p => L + (W - L - R) * p / maxP, y = v => T + (H - T - B) * (1 - v / maxV);
  let g = "";
  for (let v = 0; v <= maxV + 1e-9; v += step) g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${Math.round(v * 100)}%</text>`;
  st.prices.forEach(p => g += `<text x="${x(p)}" y="${H - 10}" text-anchor="middle">$${p}</text>`);
  Object.entries(st.reference).forEach(([year, p]) => g += `<line class="ref" x1="${x(p)}" x2="${x(p)}" y1="${T}" y2="${H - B}"/><text class="strong" x="${x(p) + 6}" y="${T + 12}">IEA net zero ${year}</text>`);
  NZ_LINES.forEach(([k, , cls]) => g += `<path class="${cls}" d="${st.curve.map((p, i) => `${i ? "L" : "M"}${x(p.price)},${y(p[k])}`).join("")}"/>`);
  const last = st.curve[st.curve.length - 1];
  const ends = NZ_LINES.map(([k, n]) => ({ k, n, y: y(last[k]), v: last[k] })).sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 16) ends[i].y = ends[i - 1].y + 16;
  ends.forEach(e => g += `<text class="${e.k === "fund" ? "strong" : ""}" x="${W - R + 10}" y="${e.y + 4}">${e.n} · ${(e.v * 100).toFixed(1)}%</text>`);
  st.curve.forEach(p => g += `<rect class="hit" x="${x(p.price) - 20}" y="${T}" width="40" height="${H - T - B}"><title>$${p.price}/t: fund ${(p.fund * 100).toFixed(2)}%, without fossil ${(p.exclusion * 100).toFixed(2)}%, index ${(p.index * 100).toFixed(2)}%</title></rect>`);
  return svg(W, H, g, "Share of pre-tax profit a carbon price would take, by carbon price");
}

function renderNetZero() {
  const a = state.netzero, el = $("#view-netzero");
  if (!a) { el.innerHTML = `<div class="head"><p class="eyebrow">Net zero</p><h2>Computing…</h2></div>`; postJSON("/api/netzero", {}).then(r => { state.netzero = r; renderNetZero(); }); return; }
  if (a.error) { el.innerHTML = `<p class="muted">${esc(a.error)}</p>`; return; }
  const F = a.funds, st = a.stress, ref = st.reference["2030"], end = st.reference["2050"];
  const at = p => st.curve.find(c => c.price === p), heavy = p => st.heavy_share.find(c => c.price === p);
  const waci = k => F[k].climate.waci_tco2e_per_musd, sbti = k => F[k].climate.sbti_target_share;
  const exclUsd = a.excluded.reduce((s, x) => s + x.index_usd, 0);
  const cut = 1 - waci("fund") / waci("index");
  const r = a.risk;
  const row = (label, fmt, note) => `<tr><th>${label}${note ? `<div class="sub">${note}</div>` : ""}</th>${["index", "exclusion", "fund"].map(k => `<td class="r num ${k === "fund" ? "hl" : ""}">${fmt(k)}</td>`).join("")}</tr>`;
  const moves = (rows, title) => `<div><h3 class="h3">${title}</h3><table class="mini"><tbody>${rows.map(x => `<tr>
      <td class="co"><b>${esc(x.name || x.ticker)}</b><span class="tk">${x.ticker} · ${esc(x.sector || "")}${x.tonnes > 0 ? ` · ${Math.round(x.tonnes / 1000).toLocaleString("en-US")} kt CO₂e` : ""}</span></td>
      <td class="r num">${f1(x.total_score)}</td><td class="r num">${usd(x.index_usd)} → <b>${usd(x.usd)}</b></td></tr>`).join("")}</tbody></table></div>`;

  el.innerHTML = `
    <div class="head"><p class="eyebrow">Bonus question</p>
      <blockquote class="question">Tomorrow, the world commits to reaching net-zero emissions as fast as possible. You manage a $1 billion investment fund. How do you allocate your portfolio under this new scenario, and why?</blockquote></div>

    <div class="answer">
      <h2>Sell the fuel. Re-weight the rest. Keep the market.</h2>
      <ol class="why">
        <li><b>Sell what cannot decarbonise.</b> Oil &amp; gas and tobacco - ${a.excluded.length} companies, ${usd(exclUsd)} of an equal-weight $1bn - go to zero. Under a fast net-zero path their product is the emissions and their reserves become stranded.
          On its own this barely changes what a carbon price would cost the fund's companies: ${(at(ref).index * 100).toFixed(1)}% of profit at $${ref}/t for the index, ${(at(ref).exclusion * 100).toFixed(1)}% without fossil fuels.</li>
        <li><b>Inside every sector, move money to companies that emit less and have a plan.</b> Every weight is tilted by a score in which actual emissions and a science-based climate target count three times.
          The carbon bill at $${ref}/t falls to <b>${(at(ref).fund * 100).toFixed(1)}%</b> of profit, carbon intensity to ${waci("fund").toFixed(0)} tCO₂e per $M revenue (${signed(-cut * 100, 0)}%), and the money in companies with a science-based target rises from ${pct(sbti("index"), 0)} to ${pct(sbti("fund"), 0)}.</li>
        <li><b>Keep every other sector.</b> Utilities, materials and industrials keep their share of the fund: that is where emissions have to fall, and owning the better companies there - and voting their shares - does more than retreating into software.
          ${r ? `Tracking error ${pct(r.tracking_error)}: a $1bn fund can hold this for decades without betting against the market.` : ""}</li>
      </ol>
    </div>

    <figure class="fig"><h3 class="h3">What a carbon price would take from the companies' profit</h3>${nzCurve(st)}
      <figcaption>Fund-weighted share of pre-tax profit a carbon bill would take, at carbon prices from $0 to $${end} per tonne. Reference: IEA <a href="${esc(st.reference_url)}" target="_blank" rel="noopener">Net Zero by 2050 ↗</a>
      assumes $${ref}/t in 2030 and $${end}/t in 2050 in advanced economies. ${esc(st.assumptions)} ${st.emitters} companies have a US facility above 25,000 t; ${st.emitters_without_income} of them have no pre-tax income on record and are left out.</figcaption></figure>

    <div class="table-wrap"><table class="compare">
      <thead><tr><th></th>${NZ_LINES.map(([k, n]) => `<th class="r ${k === "fund" ? "hl" : ""}">${n}</th>`).join("")}</tr></thead>
      <tbody>
        ${row("Holdings", k => F[k].holdings)}
        ${row("Sustainability score", k => f1(F[k].score), "net-zero weights, 0–100")}
        ${row("Carbon intensity", k => waci(k).toFixed(0), "tCO₂e per $M revenue, weighted")}
        ${row("Money in companies with a science-based target", k => pct(sbti(k), 0))}
        ${row(`Profit a $${ref}/t carbon price would take`, k => pct(at(ref)[k]), "IEA 2030 price")}
        ${row(`Profit a $${end}/t carbon price would take`, k => pct(at(end)[k]), "IEA 2050 price")}
        ${row(`Money where the bill exceeds ${Math.round(st.heavy_threshold * 100)}% of profit at $${ref}/t`, k => pct(heavy(ref)[k]))}
      </tbody></table></div>

    <div class="grid2">
      <div><h3 class="h3">$1 billion by sector</h3><table class="mini"><thead><tr><th>Sector</th><th class="r">Index</th><th class="r">Fund</th></tr></thead><tbody>
        ${a.sectors.map(s => `<tr><td>${esc(s.sector)}</td><td class="r num muted">${usd(s.index_usd)}</td><td class="r num"><b>${usd(s.fund_usd)}</b></td></tr>`).join("")}
      </tbody></table><p class="small muted">The excluded companies' money is spread over the other sectors in proportion to their size; the tilt then moves money only inside each sector.</p></div>
      <div><h3 class="h3">Most exposed companies still held</h3><table class="mini"><thead><tr><th>Company</th><th class="r">at $${ref}/t</th><th class="r">Index → fund</th></tr></thead><tbody>
        ${st.most_exposed_held.map(x => `<tr><td class="co"><b>${esc(x.name || x.ticker)}</b><span class="tk">${x.ticker} · ${Math.round(x.tonnes / 1000).toLocaleString("en-US")} kt CO₂e ${x.year}</span></td>
          <td class="r num">${pct(x.risk_2030, 0)}</td><td class="r num">${usd(x.weight_index * 1e9)} → <b>${usd(x.weight_fund * 1e9)}</b></td></tr>`).join("")}
      </tbody></table><p class="small muted">Share of pre-tax profit, capped at 100% (a loss-making emitter counts as 100%). Held, but mostly with less money - and with votes to push them.</p></div>
    </div>

    <div class="grid2">
      ${moves(a.added, "Largest additions")}
      ${moves(a.cut, "Largest reductions")}
    </div>

    <details class="more-d"><summary>The ${a.excluded.length} excluded companies</summary>
      <table class="mini"><tbody>${a.excluded.map(x => `<tr><td class="co"><b>${esc(x.name)}</b><span class="tk">${x.ticker}</span></td><td class="muted">${esc(x.sub_industry)}</td><td class="r num">${usd(x.index_usd)} → $0</td></tr>`).join("")}</tbody></table></details>

    <section class="limits"><h3 class="h3">What this does not claim</h3><ul>
      <li>It is not a forecast of returns. A carbon price is a scenario input; companies may pass costs on or cut emissions.</li>
      <li>Only direct emissions of large US facilities (EPA). No Scope 2 or 3 - the emissions of burning oil and gas are handled by excluding those companies, not by measuring them.</li>
      <li>No "green revenue" data: the fund does not yet overweight makers of the transition's equipment on purpose.</li>
    </ul></section>`;
}
