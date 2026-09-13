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

1. **Start page** - "You decide what sustainable means": set the three weights, press Compute.
   The pipeline runs live - scores, fund, the 2021 test, 1,000 weightings, the carbon price.
2. **Net zero** (`#netzero`) - the bonus answer: sell the fuel, re-weight the rest, keep the market.
   "Excluding oil & gas alone barely moves it - a $130/t carbon price still takes 8.0% of profit
   instead of 8.2%. Our tilt inside every sector cuts it to 5.3%." Carbon intensity 79.6 vs 138.2,
   60% of the money with a science-based target vs 45%, tracking error 1.9%.
3. **Method** (`#method/NUE`) - one company, every step: the EPA number, its place among 25
   materials companies, the formula, the dollar amount in the fund.
4. **Evidence A** (`#evidence/A`) - the slide that wins: "If we had run this at the end of 2021,
   the companies we rated worst in their sector were fined by the EPA 3.3 times as often
   in the following four years (26% vs 8%)."
5. **Evidence C** (`#evidence/C/NUE`) - "Don't trust us - audit any company": the sentences
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
| Why not just sell oil & gas? | We show it: exclusion alone cuts the carbon-price hit from 8.2% to 8.0% of profit. The tilt inside sectors takes it to 5.3% while staying in utilities and materials, where emissions must fall. |
| Is the carbon price test a forecast? | No. A first-order exposure: Scope 1 US tonnes x price / pre-tax income, no pass-through. The IEA Net Zero 2030/2050 prices are marked for reference. |
| Targets aren't emissions. | Correct - we use both: SBTi targets *and* EPA-reported facility emissions and fines. |
| Why exclude oil & gas instead of scoring it? | A policy choice of the fund (GICS sub-industry, not a revenue test); switchable live in the Portfolio tab. |
| Data quality? | Every value has a source link; extracted values carry the exact quote; wrong matches found by hand are documented in the commit history. |
| What's missing? | Controversy data (UN Global Compact violators), Scope 3 emissions, non-US sources, market-cap coverage 461/500. |
