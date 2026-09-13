# Pitch - S&P 500 Sustainability (draft, ~4 minutes + demo)

All numbers from `docs/PRODUCT.md` (printed by the code). Rehearse with the dashboard open.

## 1. The problem (30 s)

- ESG ratings disagree with each other, reward big companies with big reporting teams, and
  cannot be checked - they are opinions with a number attached.
- An ETH fund needs something it can defend: a score that is transparent, reproducible and
  that *means* something.

## 2. Our answer (40 s)

> A sustainable company can keep running for decades without wearing down the planet,
> its people, or its own economic base.

- Three pillars, 15 indicators, all from public records: SEC filings, EPA, Department of
  Labor, the Science Based Targets initiative.
- Every company is compared only with its own sector. No estimates: a gap stays a gap.
- Every number on screen links to the document it came from.

## 3. Demo (90 s)

1. **Ranking** - top companies, click one: the chain from source document to score.
2. **Portfolio** (`#portfolio`) - "This is the fund": 477 holdings, tobacco and oil & gas out.
   Switch profile to **Net Zero**: carbon intensity 79.6 vs 138.2 for the index (-42%),
   60% of the money in companies with a science-based climate target vs 45%.
   Tracking error 1.9% - it still behaves like the S&P 500.
3. **Evidence A** (`#evidence/A`) - the slide that wins: "If we had run this at the end of 2021,
   the companies we rated worst in their sector were fined by the EPA 3.3 times as often
   in the following four years (26% vs 8%)."
4. **Evidence C** (`#evidence/C/NUE`) - "Don't trust us - audit any company": the sentences
   from its filings, its EPA record, its news.

## 4. Why it holds (30 s)

- **Weights are a choice - it doesn't matter much:** 1,000 random weightings, the ranking
  correlates 0.87 with ours.
- **Deterministic:** no AI produces a score; one command rebuilds everything from public data.

## 5. Close (20 s)

A sustainability-tilted S&P 500 fund an ETH committee can explain line by line - more
sustainable, same market exposure, and a score that predicted who got caught.

## Q&A prep

| Question | Answer |
|---|---|
| Is this an impact fund? | No. Buying listed shares doesn't fund new projects. It is a sustainability-tilted index fund - it rewards better companies and votes their shares. |
| Does it cost return? | Hypothetically (today's weights on the last 36 months, not a backtest): balanced 20.4%/yr vs 20.5%; net zero 19.4% - about 1 point less in a period when oil & gas rallied. Tracking error 1.9%. |
| Why these weights? | Evidence B: under 1,000 random weightings the ranking correlates 0.87 with ours. The profile lets a committee set its own. |
| Isn't EPA-fine prediction just size? | Partly possible - big companies run more plants. The score is size-neutral and sector-relative; we state the limit on the exhibit. We also tested employee lawsuits and found no pattern, and we say so. |
| US data only? | Yes - SEC, EPA, DOL. Foreign plants and practices are mostly invisible. Named on the Method tab. |
| Targets aren't emissions. | Correct - we use both: SBTi targets *and* EPA-reported facility emissions and fines. |
| Why exclude oil & gas instead of scoring it? | A policy choice of the fund (GICS sub-industry, not a revenue test); switchable live in the Portfolio tab. |
| Data quality? | Every value has a source link; extracted values carry the exact quote; wrong matches found by hand are documented in the commit history. |
| What's missing? | Controversy data (UN Global Compact violators), Scope 3 emissions, non-US sources, market-cap coverage 461/500. |
