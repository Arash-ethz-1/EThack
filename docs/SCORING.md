# Scoring - from sub-indicators to a 0-100 impact score

Code: `common/score.py`. Run: `python run.py score`. Tests: `tests/test_score.py`.
Deterministic: same inputs, same scores, no model calls. Owner: Arash - propose
changes, do not edit.

## Method (v1)

For each category (economic, social, environmental):

1. **Take `ready` indicators only** from the catalog.
2. **Latest year per company.** Each company uses its most recent value.
3. **Percentile rank across the S&P 500 universe** -> 0 (worst) to 1 (best).
   If `higher_is_better = false` the rank is flipped. Ties share the average rank.
4. **Category score = weighted mean of the ranks x 100**, using the catalog `weight`.
   Missing indicators are skipped, not treated as zero.
5. **Coverage rule:** a company only gets a score if the indicators it has carry at
   least **50% of the category's total weight** (`MIN_WEIGHT_SHARE` in
   `common/config.py`). Otherwise the score is empty - we do not score what we cannot see.

Output `scores/category_scores.csv`, one row per company:
`ticker, name, sector, <cat>_score, <cat>_n_indicators, <cat>_weight_share` for each category.
`scores/indicator_ranks.csv` has every rank, so any score can be explained.

## Why percentile ranks

- **Robust to outliers and units** - a single extreme value does not squash everyone
  else to 0, and tonnes, ratios and % become comparable without tuning.
- **Easy to explain** - "a social score of 80 means better than ~80% of the S&P 500
  on the average social indicator."
- Trade-off: it throws away distance (rank 1 vs. 2 can be tiny or huge). Fine for v1.

## Open decisions (team)

- **Sector-relative ranking?** An oil company will always rank low on emissions
  intensity. Ranking within GICS sector compares companies to their peers instead.
  Likely needed for environmental; decide once real data exists.
- **Indicator weights** - all `1` until there is a reason.
- **Year alignment** - should all companies use the same year instead of their latest?
- **Phase 3: how the three category scores become portfolio weights.**
