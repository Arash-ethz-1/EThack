# Lauren - Indicators and Scoring


> **This is a proposal, not an order.** You own this file - if you see a better
> route, edit it, commit it, and tell the team in one line. The only things that are
> not yours to change alone are the contracts in `src/ethack/contracts.py` and the
> file ownership table in `CONVENTIONS.md`.


You own the part that turns data into a judgement. The innovation you are responsible
for is not *more* indicators - it is being **honest about what we do not know**,
which almost nobody does and which is disproportionately persuasive to an
institutional audience.

**Your files:** `indicators/impl/*.py` `score.py` `tests/test_score.py`

---

## 16:00 - 17:00 | Start on mocks immediately

`python run.py mocks && python run.py test`. Four reference indicators already exist and pass tests -
read `impl/carbon_intensity.py`, it is your template. **You are never blocked on
Jean or Arash.** The mock panel has `metered_scope1_t`, `reported_scope1_t`,
`satellite_scope1_t`, `revenue_usd`, `ebitda_usd`, `sector`.

## 17:00 - 21:00 | Build out the indicator set

Each indicator is one file: an `IndicatorSpec` plus a `compute()`. Rules that the
tests enforce, so you cannot forget them:

- a written `rationale` - one sentence, goes straight onto the methodology slide
- an honest `durability` rating
- `direction` +1 or -1
- **NaN for missing, never 0.** A zero emission is a claim; NaN is the truth.
  This single discipline is why our numbers will hold up and others' will not.

Proposed set beyond the four that exist (change it if you can argue better):
`carbon_at_risk_50` / `_200`, enforcement penalties per $B revenue, emissions
trajectory 2019-2023 from the metered panel, target credibility (pledge steepness
vs. delivered slope), assurance presence, revenue-weighted water stress if time.

Aim for 8-12 good indicators across all five dimensions. Twelve defensible beats
thirty arbitrary, and every one you add has to be defended in Q&A.

## 21:00 - 01:00 | score.py - where you win or lose

Four things, none optional:

1. **Sector-relative percentiles.** Comparing software to cement is a category error
   and a judge will say so within ten seconds.
2. **Bootstrap confidence intervals**, and companies whose intervals overlap
   **share a tier**. Say it out loud: *we refuse to claim #47 differs from #63 when
   the data cannot tell.* This is the most credible sentence in the pitch.
3. **A `visibility` column** - how much of this company we can actually see. Reported
   alongside the score, never folded into it. "Clean and well-observed" and "clean
   but unverifiable" are completely different risk positions.
4. **Three weighting modes**: declared, equal, and confidence-weighted
   (coverage x durability). Then report how little the ranking moves between them.
   Robustness to your own weighting scheme is the answer when the weights get
   attacked - and they will.

`dead_sources` is a parameter of `score()`, not an afterthought: drop the indicators
that depend on a switched-off source, renormalise the survivors, recompute. That is
what makes Arash's blackout page real rather than a mock-up.

## 01:00 - 03:00 | Hand the results over, then stop

Write `data/processed/company_scores.parquet`, tell Florian and Harprit, and do a
sensitivity table: how much does the top-20 change under each weighting mode.

Sleep 03:00-08:00. From 08:00 you are the person who can answer any methodology
question, so be awake for the rehearsal.

## Your wow contribution

**Uncertainty-aware scoring.** Tiers instead of a spurious 1-500 ranking, CIs that
widen honestly when coverage falls, and a visibility axis running orthogonal to the
score. Every other team will hand the judges a false-precision leaderboard. You hand
them a number *and* how much of it to trust.

> **Model decision: NO trained model in this layer.** Scoring must be deterministic
> and reproducible - if a judge asks "why 0.40?", the answer is a line of code.
> Bootstrapping is resampling, not learning. Keep it that way.

## Done when

- [x] 8-12 indicators, each with rationale, durability, unit, and a test — 11 live:
      `metered_carbon_intensity`, `satellite_carbon_intensity`, `emissions_trajectory`,
      `carbon_at_risk_50/100/200`, `saydo_gap`, `satellite_divergence`,
      `target_credibility`, `assurance_presence`, `facility_concentration`.
- [x] `company_scores.parquet` valid against the contract (`python run.py score` on
      mocks, 120/120 companies rankable, tiers A-E roughly balanced)
- [x] CIs and tiers, with overlapping intervals sharing a tier — bounded to the
      four A/B..D/E boundary pairs, not transitively cascaded (a naive neighbour
      chain collapses the whole table into tier A - caught this on mocks, see
      `score._assign_tiers`)
- [x] sensitivity table across the three weighting modes — `score.sensitivity_table()`;
      top-20 overlap is 19-20/20 across declared/equal/confidence on mocks
- [x] `score(dead_sources=...)` works, so the blackout page is live — verified
      against every scenario in `blackout.scenarios()`. Caught and fixed a real bug
      here: `satellite_divergence` alone still named `company_reports` as a source,
      so "Voluntary reporting collapses too" left zero indicators computable. Added
      `satellite_carbon_intensity` (sources: satellite + sec_xbrl only) so the
      "keeps working when everything else is dark" claim in `docs/THESIS.md` is
      actually true, not just asserted. Regression-tested in `test_indicators.py`.

## Handoff notes for Florian / Harprit

- `data/processed/company_scores.parquet` is written by `python run.py score`
  (that's `python -m ethack.score` with `src/` on `PYTHONPATH`, which `run.py`
  sets for you - no separate setup needed). Columns match `contracts.COMPANY_SCORES`
  exactly.
- `tier == "U"` means "coverage below `MIN_COVERAGE_TO_RANK`, we refuse to rank it" -
  `score` is `NaN` for those rows on purpose. Please don't `.dropna()` it away
  silently; the count of U's is itself a number worth reporting.
- `n_indicators_used` and `visibility` are your per-company confidence signals for
  sizing/weighting in the portfolio and eval layers.
- Also flagged, not mine to fix: `blackout.scenarios()` has "GHGRP + ECHO gone" and
  "All US federal environmental data gone" defined as the literal same
  `dead_sources` set - looks like a copy-paste, probably meant to add `satellite` or
  another source to the second one.
