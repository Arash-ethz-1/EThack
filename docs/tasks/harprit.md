# Harprit - Validation and Evidence


> **This is a proposal, not an order.** You own this file - if you see a better
> route, edit it, commit it, and tell the team in one line. The only things that are
> not yours to change alone are the contracts in `src/ethack/contracts.py` and the
> file ownership table in `CONVENTIONS.md`.


You own the single biggest differentiator in the project. Almost no hackathon team
validates anything, which means a score nobody tested is the field's default. If you
can show ours predicts something real and a vendor score does not, the argument is
over before Q&A starts.

**Your files:** `eval/*` `METRICS.md` `app/pages/4_evaluation.py`
`tests/test_eval.py`

---

## 16:00 - 17:00 | Start on mocks, not on real data

`make mocks` gives you `company_scores.parquet` in the real schema. **Write the whole
test harness against it now.** If evaluation genuinely happens last, it happens at
09:00 and gets cut - and that is exactly how teams lose their strongest slide.

## 17:00 - 20:00 | Test 1: does the score predict misconduct?

The cleanest validation available to us, because the ground truth is free and
independent: EPA enforcement actions.

1. score using data through **2021 only** (Lauren's `score()` takes a year filter -
   agree the interface with her at 17:00, in one message)
2. do bottom-quintile companies incur more enforcement dollars and violation-quarters
   in **2022-2024** than top-quintile?
3. report the **odds ratio, n, and a p-value**
4. run the identical test on a vendor ESG score (yfinance sustainability fields, or
   any free score you can get) as the benchmark

If ours separates and theirs does not, that is the slide that wins. If neither does,
report that honestly - it is still a real finding about ESG scores generally.

## 20:00 - 23:00 | Test 2: does the market price it?

Event study. Pick 5-8 carbon-policy shock dates, compute abnormal returns for
high- vs low-carbon-at-risk portfolios in a +/-3 day window against a market model.

If high-CaR names drop on policy tightening, our score is a live risk factor rather
than a virtue rating. **If they do not move, say so** - unpriced risk is the more
interesting finding and it sets up Florian's portfolio directly.

Sleep 23:00-03:00. Real scores do not exist until 01:00; do not burn the night
waiting for them.

## 03:00 - 07:00 | Test 3: the information half-life - this one is ours alone

The quantitative core of the whole thesis, and nobody else will have anything like it.

**Question:** how stale can the data get before the ranking is wrong?

Re-score using only data available as of T-1y, T-2y, T-3y, and measure Kendall tau
against today's ranking. You get a decay curve. That curve tells the fund two things
no ESG vendor will tell them:

- how often they must refresh to keep the ranking meaningful
- what it costs them in ranking accuracy when refreshing becomes **impossible**

That second reading is the entire project in one chart. If GHGRP is rescinded, the
fund's view does not go wrong immediately - it decays at a measurable rate, and you
are the person who measured it.

Then run the **red-team agent** against our top five and bottom five rankings.

> **Agent decision: YES for the red team, at ~07:00.** Point it at our own output
> with one instruction: build the strongest case that this ranking is wrong. Two
> payoffs - you patch the holes before Q&A, and "we ran an adversarial agent against
> our own output, here is what it found" signals more maturity than any architecture.

> **Model decision: OPTIONAL, and only if you have slack.** A gradient-boosted model
> on the ~150k facility-year panel (Jean's 2010-2023 pull) predicting 3-year emission
> decline, time-split at 2020, benchmarked against a persistence baseline. Real n,
> real ML, and it feeds Florian's decarboniser sleeve. **Cut it without hesitation if
> Tests 1-3 are not finished** - validation of the score beats a fourth model.

## 07:00 - 09:00 | METRICS.md and your page

One table, every number we claim, with its n and its method. This file is what a
judge opens to check whether we are serious.

Also commit `PREDICTIONS.md`: the five companies our model flags hardest, timestamped,
with what would prove us wrong. Teams willing to be checked are remembered.

## Your wow contribution

**The information half-life curve.** It converts the political story into a measured
rate of decay, which is the difference between a narrative and a finding.

## Done when

- [ ] Test 1: odds ratio + n + p-value, plus the vendor benchmark
- [ ] Test 2: event study table, honest either way
- [ ] Test 3: half-life decay curve
- [ ] red-team agent run, findings patched or documented
- [ ] `METRICS.md` and `PREDICTIONS.md` committed
- [ ] your dashboard page renders in the shell
