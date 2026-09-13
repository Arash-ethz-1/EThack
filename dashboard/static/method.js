/* Method tab - dashboard/static/method.js (loaded after app.js, uses its helpers).
   Plain-language methodology. Indicator facts (name, description, source, coverage, years)
   come live from GET /api/meta (the catalogs); the pillar questions, UN SDG links and the
   one-line weak spot per indicator are editorial text kept here. */

const PILLARS = {
  environmental: { q: "Is it damaging nature - and does it depend on resources that may run out?", sdg: "SDG 12 · 13 · 15" },
  social: { q: "Does it treat the people who work for it fairly and safely?", sdg: "SDG 3 · 5 · 8 · 10" },
  economic: { q: "Can it sustain itself and the economy around it?", sdg: "SDG 8 · 9 · 16" },
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

function renderMethod() {
  const inds = state.meta.indicators;
  const card = m => `<article class="m-ind">
      <header><h4>${esc(m.name)}</h4><span class="dir">${m.higher_is_better ? "higher is better" : "lower is better"}</span></header>
      <p>${esc(m.description)}</p>
      <dl><div><dt>Source</dt><dd>${esc(m.source)}</dd></div>
        <div><dt>Coverage</dt><dd>${m.companies} of ${state.meta.companies} companies · ${m.year_min ?? "–"}–${m.year_max ?? "–"}</dd></div>
        <div><dt>Weak spot</dt><dd>${esc(WEAK[m.id] || "–")}</dd></div></dl>
    </article>`;
  $("#view-method").innerHTML = `
    <div class="lede"><div><span class="label">Method</span>
      <h2>A sustainable company can keep running for decades without wearing down the planet, its people, or its own economic base.</h2>
      <p>We score that along the three pillars of sustainability. Every number comes from a public document - SEC filings, US regulators, the Science Based Targets initiative - and every value on this dashboard links back to it.</p></div></div>

    <ol class="m-steps">
      <li><b>Collect.</b> ${inds.length} indicators, each a script that rebuilds its file from the public source. No number is estimated or filled in: a company without data is a gap.</li>
      <li><b>Compare within the sector.</b> Each company is ranked 0-100 only against its own GICS sector, so a bank is never compared with a steel maker. Only values from 2022 on count.</li>
      <li><b>Weigh.</b> Pillar score = weighted mean of its indicators; total = weighted mean of the pillars. A company needs data for at least half the weight to get a score. The weights are a choice - Exhibit B shows the ranking barely depends on them.</li>
      <li><b>Invest.</b> Start from the S&amp;P 500, drop tobacco and oil &amp; gas, tilt every weight by the score (a company one standard deviation better gets about 1.8x its weight), keep each sector's size, cap any company at 5%.</li>
    </ol>

    ${CATS.map(([id, name, col]) => `<section class="m-pillar">
      <div class="m-ph"><span class="sw" style="background:var(${col})"></span><h3>${name}</h3><span class="muted">${PILLARS[id].sdg}</span></div>
      <p class="m-q">${PILLARS[id].q}</p>
      <div class="m-grid">${inds.filter(m => m.category === id).map(card).join("")}</div>
    </section>`).join("")}

    <section class="m-limits"><h3>What we do not claim</h3><ul>
      <li>US data sources: foreign plants, foreign lawsuits and non-US pay practices are mostly invisible.</li>
      <li>Targets are not emissions, and disclosure is not behaviour - we keep both kinds of indicator and label them.</li>
      <li>No model or AI produces a score. Scores come from deterministic code (<code>common/score.py</code>); anyone can rerun it.</li>
      <li>This is a sustainability-tilted index fund, not an impact fund: buying shares on the market does not fund new projects.</li>
    </ul></section>`;
}
