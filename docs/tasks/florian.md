# Florian - Portfolio Construction


> **This is a proposal, not an order.** You own this file - if you see a better
> route, edit it, commit it, and tell the team in one line. The only things that are
> not yours to change alone are the contracts in `src/ethack/contracts.py` and the
> file ownership table in `CONVENTIONS.md`.


You answer the bonus question, and you own the part of the pitch that decides whether
a finance audience thinks we understand markets or just spreadsheets.

**Your files:** `portfolio/*` `app/pages/3_portfolio.py` `tests/test_portfolio.py`

---

## 16:00 - 17:00 | You are never blocked

`python run.py mocks` gives you `company_scores.parquet` with `score`, `ci_low`, `ci_high`,
`tier`, `visibility`, `coverage_ratio` - the real schema, fake values. Build the
entire allocation against it and swap the file at 01:00. Do not wait for Lauren.

## 17:00 - 21:00 | The thesis, written before the code

Write your argument in `docs/PORTFOLIO.md` first. If you cannot write it, the code
will not save it.

Every other team answers *overweight renewables, divest fossil fuels*. That is both
consensus and empirically weak: module prices fell roughly 90% while module makers
destroyed enormous amounts of capital. **Decarbonisation working is not the same as
decarbonisation paying.** Our four moves instead:

1. **Bottleneck, not theme.** A crash net-zero is a *wiring* problem, not a solar
   problem - you cannot electrify faster than you can build grid to carry it. Grid
   equipment, transformers, copper, regulated utilities with rate-base growth have
   multi-year backlogs and real pricing power. Panels do not. Rent accrues to whoever
   owns the constraint.
2. **Own and engage, do not divest.** Selling a high emitter to someone who does not
   care removes zero molecules and removes your vote. Hold top-decile emitters whose
   *metered* trajectory is actually falling - our EPA panel gives you the real slope,
   not a pledge - and buy the discount that forced ESG selling creates.
3. **Size by visibility.** *This one is ours alone.* Position size scales with how
   well we can see the company: low visibility, smaller position. It falls straight
   out of the thesis, it is trivially defensible ("we do not take large positions in
   things we cannot measure"), and no other team will have it.
4. **Greenflation.** A mandated crash transition is the largest capex programme in
   history against binding physical constraints - it is inflationary, which derates
   exactly the long-duration growth names most funds hold as their climate sleeve.
   So the book is short-duration, hard-asset, value-tilted. It looks almost nothing
   like an ESG fund, and you should say so.

Starting allocation proposal - **change it if you can defend the change better:**

| Weight | Sleeve |
|---|---|
| 35% | bottleneck owners: grid equipment, copper, transformers, regulated utilities |
| 22% | metered decarbonisers: high emitters with a verified falling slope, held and voted |
| 20% | low carbon-at-risk compounders, screened by our own Pillar 3 |
| 13% | hard-tech optionality: industrial heat, long-duration storage, nuclear fuel cycle |
| 10% | cash and carbon-price hedge |
| +10% short overlay | widest Say-Do gap names - undisclosed liability that disclosure will expose |

**Name your zero weights out loud, with reasons.** Being specific about what you will
not own is what separates a portfolio from a wish list.

## 21:00 - 01:00 | Build it

`construct(scores, visibility_sizing=True)` -> the `portfolio` contract. Pure
function: dataframe in, dataframe out, no file reads, no network. Make
`visibility_sizing` a toggle so the dashboard can show the difference it makes -
that side-by-side *is* your slide.

Sleep 22:00-02:00 if you finish the logic early. You are mock-blocked until Lauren's
real scores land at 01:00 anyway, and you want to be sharp for the back half.

## 02:00 - 06:00 | Real scores, real names

Swap in the real file. Sanity-check every holding by hand - if a name looks wrong,
it probably is, and finding that at 04:00 is much better than on stage. Write the
sleeve rationales as finished prose.

## 06:00 - 09:00 | Your dashboard page

`app/pages/3_portfolio.py`. Import `_shared.load()`; do not read parquet yourself.
Allocation bar, sleeve table, the visibility-sizing toggle, the zero-weight list.

## Your wow contribution

**Visibility-weighted position sizing** plus the own-and-engage argument. The line to
land: *divesting your carbon does not reduce the world's carbon - it just removes
your vote.*

> **Model decision: NO. Deterministic construction only.** A trained allocator on
> 500 rows is indefensible and a finance judge will say so. Rules you can state in a
> sentence beat an optimiser nobody can interrogate.

## Done when

- [ ] `docs/PORTFOLIO.md` - the argument, in prose
- [ ] `portfolio.csv` valid against the contract, real tickers, weights summing correctly
- [ ] visibility-sizing toggle with a before/after comparison
- [ ] zero weights named with reasons
- [ ] your dashboard page renders in the shell
