# Scoring - from sub-indicators to 0-100 impact scores

Code: `common/score.py`. Run: `python run.py score [profile]` or `python run.py dashboard`.
Tests: `tests/test_score.py`, `tests/test_pipeline.py`. Deterministic: same inputs, same
scores, no model calls. Owner: Arash - propose changes, do not edit.

## Pipeline (v2)

```
indicators/*.csv ──1 load──> latest value per company ──2 rank──> 0..1 per indicator
                                                                        │
profiles/<name>.toml ──3 profile: which indicators, which weights ──────┤
                                                                        │
                        4 score: category scores 0-100 ──> total score 0-100
                                                                        │
                        5 portfolio (phase 3, placeholder: portfolio/allocate.py)
```

1. **Load** `ready` indicators only. Each company uses its most recent year.
2. **Percentile rank across the S&P 500 universe** -> 0 (worst) to 1 (best).
   If `higher_is_better = false` the rank is flipped. Ties share the average rank.
   With `sector_relative = true` a company is ranked only against its own GICS sector.
3. **Profile** - the user of the tool decides what counts:
   - `[categories]` weight per category (0 = ignore the category)
   - `[indicators]` weight per indicator, overriding the catalog `weight`; `0` switches
     it off; indicators not listed keep their catalog weight (so new indicators join
     automatically). Unknown ids are ignored with a warning.
   - `min_weight_share`, `sector_relative`, `[portfolio]` (phase 3)
4. **Category score** = weighted mean of the chosen indicator ranks x 100.
   **Total score** = weighted mean of the category scores with the category weights.
   A category with no chosen indicators drops out and the others are re-weighted.
   Missing values are skipped, not treated as zero.
5. **Coverage rule:** a company only gets a category score if the indicators it has
   carry at least `min_weight_share` (default 50%) of that category's weight - and a total
   score if its scored categories carry that share of the category weight.
   We do not score what we cannot see.

Output `scores/<profile>/scores.csv`, one row per company, best first:
`ticker, name, sector, position, total_score, total_weight_share,` and
`<cat>_score, <cat>_n_indicators, <cat>_weight_share` per category.
`scores/<profile>/indicator_ranks.csv` has every rank. `explain()` breaks a total score
into points per indicator that add up to the total - the dashboard's Company tab shows it.

Shipped profiles: `balanced` (default, everything equal) and `net_zero` (bonus question:
environmental x3, emissions intensity x3). Save your own from the dashboard.

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
- **Indicator weights** - catalog weights stay `1`; preferences belong in profiles.
- **Year alignment** - should all companies use the same year instead of their latest?
- **Phase 3: how a profile's scores become portfolio weights** (`portfolio/allocate.py`).
