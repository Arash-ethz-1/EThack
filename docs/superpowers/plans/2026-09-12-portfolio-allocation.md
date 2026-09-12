# Portfolio Allocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **OWNERSHIP: this is a PROPOSAL, not work to be done by the social team.**
> `portfolio/` is Arash's area (`AGENTS.md` section 2). Written by Florian's session so the
> method is decided on evidence rather than in the last hour. Arash owns the merge.

**Goal:** Turn the three category scores into portfolio weights that sum to 1, by tilting
the benchmark toward high scores rather than picking stocks.

**Architecture:** `allocate()` composes five pure functions, each independently testable:
benchmark weights -> standardise scores -> multiplicative tilt -> sector-neutral
renormalisation -> iterative weight cap. The tilt is `w_i is proportional to
benchmark_i * exp(lambda * z_i)`, which keeps every weight positive (no shorting) and
collapses to the benchmark at `lambda = 0`, so one dial spans index-hugging to concentrated.

**Tech Stack:** Python 3.11+, pandas, pytest. No new dependencies (`AGENTS.md` section 4.9).

**Spec:** `docs/tasks/florian.md` (section "Plan - for the team") and the placeholder
docstring in `portfolio/allocate.py`, which already fixes the interface.

## Global Constraints

- Signature is already fixed and MUST NOT change:
  `allocate(scores: pd.DataFrame, profile: Profile, fund_usd: float = 1e9) -> pd.DataFrame`
- `OUTPUT_COLUMNS = ["ticker", "weight", "reason"]`; weights sum to 1.0.
- Deterministic code only. No model calls (`AGENTS.md` section 4.8).
- No new entries in `requirements.txt`.
- `scores` is `common.score.Result.table`: columns `ticker, name, sector, position,
  total_score, total_weight_share, <cat>_score, <cat>_n_indicators, <cat>_weight_share`.
  `total_score` is 0-100 and is **NaN** when a company lacks enough data.
- **A company with no score keeps its benchmark weight.** It is never dropped and never
  treated as worst. Coverage gaps are our measurement problem, not an investment view.
  (As of 2026-09-12 `labor_litigation_intensity` covers 2% of the universe - dropping
  unscored companies would turn that gap into a portfolio bet.)
- **Market cap does not exist in this repo.** `grep -rl "market_cap"` returns nothing.
  The benchmark is therefore equal weight, with a market-cap path behind a column check
  so nothing breaks when Arash adds `universe/marketcaps.csv`.
- Tests live in `tests/test_portfolio.py` and follow `tests/test_score.py`: plain pytest
  functions, small inline DataFrames, no fixtures, no mocks.
- Run tests with `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`.
- Commit with `python run.py save "[portfolio] ..."` - never raw git (`AGENTS.md` section 3).

### Facts verified against the repo on 2026-09-12 (do not re-guess these)

- **`Profile` field names.** The dataclass in `common/score.py` is
  `Profile(name, description="", category_weights={...}, indicator_weights={}, min_weight_share,
  sector_relative=False, portfolio={})`. There is **no** `categories=` or `indicators=` keyword -
  those are the TOML section names, not constructor arguments. `Profile(name="t", categories={},
  indicators={})` raises `TypeError: Profile.__init__() got an unexpected keyword argument
  'categories'`. Tests must use `Profile(name="t")` or `Profile(name="t", portfolio={...})`.
- **`Profile.portfolio` already exists** (`field(default_factory=dict)`, commented "phase 3, not
  used yet") and `profile_from_dict` already copies a `[portfolio]` TOML block into it. Nothing in
  `common/score.py` needs to change - open question 2 below is closed.
- **`scores/balanced/scores.csv` header** (verified, 15 columns):
  `ticker, name, sector, position, total_score, total_weight_share,` then `<cat>_score,
  <cat>_n_indicators, <cat>_weight_share` for economic / social / environmental.
  `allocate()` only reads `ticker`, `sector`, `total_score`, so the small test tables are enough.
  Today the file has 503 rows, 503 of them scored, 0 missing sectors, 0 duplicate tickers,
  11 sectors, the smallest being Energy with 21 companies.
- **`dashboard/server.py:60` does `from portfolio.allocate import OUTPUT_COLUMNS,
  PLANNED_SETTINGS`.** Keep both module constants - deleting either breaks the dashboard.
- **No existing test asserts the `NotImplementedError`** (`grep -rn allocate tests/` is empty), so
  implementing `allocate()` cannot break the current suite. Baseline before this plan:
  `/venvs/python_general/bin/python -m pytest -q` -> **36 passed**.
- **`python run.py check`** = `common.validate.validate_all()` + the whole pytest suite. There is
  no formatter and no line-length rule, and `validate_all` does not look at `profiles/*.toml`, so
  the `[portfolio]` block in Task 8 cannot fail the check.
- **Environment:** Python 3.12.3, pandas 3.0.2, numpy 1.26.4, pytest 9.0.1.
- **`fund_usd` is accepted and unused.** `OUTPUT_COLUMNS` is fixed at `ticker, weight, reason`, so
  there is no place to put a dollar amount; the dashboard multiplies by the fund size itself. Keep
  the parameter for interface compatibility and say so in the docstring.

---

### Task 1: Benchmark weights

**Files:**
- Modify: `portfolio/allocate.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `benchmark_weights(scores: pd.DataFrame, marketcaps: pd.Series | None = None) -> pd.Series`
  indexed by ticker, summing to 1.0.

- [ ] **Step 1: Write the failing test**

```python
import pandas as pd
import pytest

from portfolio.allocate import benchmark_weights


def table(rows):
    return pd.DataFrame(rows, columns=["ticker", "sector", "total_score"])


def test_benchmark_is_equal_weight_without_market_caps():
    scores = table([("A", "Tech", 80.0), ("B", "Tech", 40.0), ("C", "Energy", 60.0)])
    w = benchmark_weights(scores)
    assert w.to_dict() == {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}
    assert w.sum() == pytest.approx(1.0)


def test_benchmark_uses_market_caps_when_given():
    scores = table([("A", "Tech", 80.0), ("B", "Tech", 40.0)])
    caps = pd.Series({"A": 300.0, "B": 100.0})
    w = benchmark_weights(scores, caps)
    assert w["A"] == pytest.approx(0.75)
    assert w["B"] == pytest.approx(0.25)


def test_benchmark_falls_back_to_the_median_cap_for_missing_caps():
    scores = table([("A", "Tech", 80.0), ("B", "Tech", 40.0), ("C", "Energy", 60.0)])
    caps = pd.Series({"A": 300.0, "C": 100.0})  # B has no cap
    w = benchmark_weights(scores, caps)
    assert w.sum() == pytest.approx(1.0)
    assert w["B"] == pytest.approx(200.0 / 600.0)   # the median of the caps we do have


def test_empty_universe_and_duplicate_tickers_are_rejected():
    with pytest.raises(ValueError):
        benchmark_weights(table([]))
    with pytest.raises(ValueError):
        benchmark_weights(table([("A", "Tech", 80.0), ("A", "Tech", 40.0)]))
```

The last test is not decoration. Without the guards an empty universe dies deep inside
`benchmark_weights` with `ZeroDivisionError: float division by zero`, and a duplicated ticker
survives all the way to `allocate()`, where `pd.isna(scored[t])` gets a two-element Series and
raises `ValueError: The truth value of a Series is ambiguous`. Both were reproduced. This is the
one place every path goes through, so both checks belong here.

- [ ] **Step 2: Run test to verify it fails**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: FAIL with `ImportError: cannot import name 'benchmark_weights'`

- [ ] **Step 3: Write minimal implementation**

```python
def benchmark_weights(scores: pd.DataFrame, marketcaps: pd.Series | None = None) -> pd.Series:
    """Starting weights before any tilt. Equal weight unless market caps are supplied.

    A company without a market cap gets the median cap rather than being dropped -
    the benchmark must cover the whole universe.
    """
    tickers = scores["ticker"].astype(str)
    if len(tickers) == 0:
        raise ValueError("cannot build a portfolio from an empty universe")
    if tickers.duplicated().any():
        raise ValueError(f"duplicate tickers in scores: {sorted(tickers[tickers.duplicated()].unique())}")
    if marketcaps is None or marketcaps.empty:
        return pd.Series(1.0 / len(tickers), index=tickers)
    caps = marketcaps.reindex(tickers)
    caps = caps.fillna(caps.median())
    return caps / caps.sum()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
python run.py save "[portfolio] benchmark_weights: equal weight, market-cap ready"
```

---

### Task 2: Standardise scores, neutral for missing

**Files:**
- Modify: `portfolio/allocate.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: `benchmark_weights` (not called here).
- Produces: `score_z(scores: pd.DataFrame, column: str = "total_score") -> pd.Series`
  indexed by ticker; mean 0, std 1 over scored companies; **0.0 for NaN scores**.

- [ ] **Step 1: Write the failing test**

```python
from portfolio.allocate import score_z


def test_z_centres_on_mean_and_scales_by_std():
    scores = table([("A", "Tech", 80.0), ("B", "Tech", 60.0), ("C", "Energy", 40.0)])
    z = score_z(scores)
    assert z["B"] == pytest.approx(0.0)
    assert z["A"] == pytest.approx(-z["C"])
    assert z["A"] > 0


def test_unscored_company_is_neutral_not_worst():
    scores = table([("A", "Tech", 80.0), ("B", "Tech", 40.0), ("C", "Energy", float("nan"))])
    z = score_z(scores)
    assert z["C"] == 0.0          # neutral, so it keeps its benchmark weight
    assert z["A"] > 0 and z["B"] < 0


def test_identical_scores_give_zero_not_nan():
    scores = table([("A", "Tech", 50.0), ("B", "Tech", 50.0)])
    z = score_z(scores)
    assert z.to_dict() == {"A": 0.0, "B": 0.0}


def test_all_scores_missing_gives_zero_for_everyone():
    nan = float("nan")
    z = score_z(table([("A", "Tech", nan), ("B", "Tech", nan)]))
    assert z.to_dict() == {"A": 0.0, "B": 0.0}   # an unscored universe = the plain benchmark
```

Note on `ddof`: nothing above pins the standard deviation convention - the first test only
checks symmetry, so population (`ddof=0`) and sample (`ddof=1`) both pass. `ddof=0` is the
choice because the 503 companies are the whole universe, not a sample of one. If you want the
convention locked, assert the number:
`assert z["A"] == pytest.approx(20.0 / pd.Series([80.0, 60.0, 40.0]).std(ddof=0))`.

- [ ] **Step 2: Run test to verify it fails**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py::test_unscored_company_is_neutral_not_worst -v`
Expected: FAIL with `ImportError: cannot import name 'score_z'`

- [ ] **Step 3: Write minimal implementation**

```python
def score_z(scores: pd.DataFrame, column: str = "total_score") -> pd.Series:
    """Standardised score per ticker. A company without a score gets 0.0 - neutral.

    Neutral, not worst: a missing score is our data gap, not evidence about the company.
    At 0.0 the tilt factor exp(lambda * 0) is 1, so the company keeps its benchmark weight.
    """
    values = pd.Series(scores[column].to_numpy(), index=scores["ticker"].astype(str), dtype=float)
    scored = values.dropna()
    if scored.empty:
        return pd.Series(0.0, index=values.index)
    spread = scored.std(ddof=0)
    if spread == 0:
        return pd.Series(0.0, index=values.index)
    return ((values - scored.mean()) / spread).fillna(0.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
python run.py save "[portfolio] score_z: standardised scores, unscored companies neutral"
```

---

### Task 3: Multiplicative tilt

**Files:**
- Modify: `portfolio/allocate.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: `benchmark_weights` -> `pd.Series`, `score_z` -> `pd.Series`.
- Produces: `tilt(benchmark: pd.Series, z: pd.Series, strength: float) -> pd.Series`
  summing to 1.0.

- [ ] **Step 1: Write the failing test**

```python
from portfolio.allocate import tilt


def test_zero_strength_reproduces_the_benchmark():
    bench = pd.Series({"A": 0.5, "B": 0.3, "C": 0.2})
    z = pd.Series({"A": 2.0, "B": 0.0, "C": -2.0})
    out = tilt(bench, z, 0.0)
    assert out.round(10).to_dict() == bench.round(10).to_dict()


def test_higher_score_gains_weight_and_all_weights_stay_positive():
    bench = pd.Series({"A": 0.5, "B": 0.5})
    z = pd.Series({"A": 1.0, "B": -1.0})
    out = tilt(bench, z, 1.0)
    assert out["A"] > 0.5 > out["B"]
    assert (out > 0).all()
    assert out.sum() == pytest.approx(1.0)


def test_extreme_strength_does_not_produce_inf_or_nan():
    bench = pd.Series({"A": 0.5, "B": 0.5})
    z = pd.Series({"A": 40.0, "B": -40.0})
    out = tilt(bench, z, 50.0)
    assert out.notna().all()
    assert out.sum() == pytest.approx(1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: FAIL with `ImportError: cannot import name 'tilt'`

- [ ] **Step 3: Write minimal implementation**

```python
import numpy as np

MAX_EXPONENT = 20.0  # exp(20) is ~4.9e8; beyond this float64 loses all resolution


def tilt(benchmark: pd.Series, z: pd.Series, strength: float) -> pd.Series:
    """benchmark_i * exp(strength * z_i), renormalised to sum to 1.

    exp() keeps every weight strictly positive, so there is no shorting and nothing to
    explain to a fund. strength = 0 returns the benchmark exactly.
    """
    exponent = (strength * z.reindex(benchmark.index).fillna(0.0)).clip(-MAX_EXPONENT, MAX_EXPONENT)
    weights = benchmark * np.exp(exponent)
    return weights / weights.sum()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
python run.py save "[portfolio] tilt: multiplicative exp tilt on benchmark weights"
```

---

### Task 4: Sector-neutral renormalisation

**Files:**
- Modify: `portfolio/allocate.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: `tilt` output, `benchmark_weights` output.
- Produces: `sector_labels(sectors: pd.Series, index: pd.Index) -> pd.Series` and
  `sector_neutralise(weights: pd.Series, benchmark: pd.Series, sectors: pd.Series) -> pd.Series`

- [ ] **Step 1: Write the failing test**

```python
from portfolio.allocate import sector_neutralise


def test_sector_totals_match_the_benchmark_after_neutralising():
    weights = pd.Series({"A": 0.60, "B": 0.20, "C": 0.15, "D": 0.05})
    bench = pd.Series({"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25})
    sectors = pd.Series({"A": "Tech", "B": "Tech", "C": "Energy", "D": "Energy"})
    out = sector_neutralise(weights, bench, sectors)
    assert out[["A", "B"]].sum() == pytest.approx(0.5)
    assert out[["C", "D"]].sum() == pytest.approx(0.5)


def test_ordering_inside_a_sector_is_preserved():
    weights = pd.Series({"A": 0.60, "B": 0.20, "C": 0.15, "D": 0.05})
    bench = pd.Series({"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25})
    sectors = pd.Series({"A": "Tech", "B": "Tech", "C": "Energy", "D": "Energy"})
    out = sector_neutralise(weights, bench, sectors)
    assert out["A"] > out["B"] and out["C"] > out["D"]


def test_sector_with_zero_tilted_weight_falls_back_to_benchmark_shape():
    weights = pd.Series({"A": 0.0, "B": 0.0, "C": 1.0})
    bench = pd.Series({"A": 0.25, "B": 0.25, "C": 0.5})
    sectors = pd.Series({"A": "Tech", "B": "Tech", "C": "Energy"})
    out = sector_neutralise(weights, bench, sectors)
    assert out[["A", "B"]].sum() == pytest.approx(0.5)
    assert out["A"] == pytest.approx(0.25)


def test_missing_or_blank_sector_label_is_its_own_bucket_not_a_hole():
    weights = pd.Series({"A": 0.5, "B": 0.3, "C": 0.2})
    bench = pd.Series({"A": 1 / 3, "B": 1 / 3, "C": 1 / 3})
    for label in (None, ""):
        out = sector_neutralise(weights, bench, pd.Series({"A": "Tech", "B": label, "C": "Tech"}))
        assert out[["A", "C"]].sum() == pytest.approx(2 / 3)
        assert out["B"] == pytest.approx(1 / 3)
```

**Why the last test exists.** The obvious implementation loops over `sec.dropna().unique()`, which
silently skips every company whose sector is missing: those keep their *tilted* weight while every
real sector is rescaled, the total is then no longer 1, and the closing `out / out.sum()` smears the
error across all sectors. Reproduced with A, C in Tech and B unlabelled: Tech came out at **0.6897**
against a benchmark target of **0.6667**. `scores/balanced/scores.csv` has no missing sector today,
but `universe/sp500.csv` is read with `keep_default_na=False` (blank sector -> `""`), while
`pd.read_csv("scores/balanced/scores.csv")` turns the same blank into `NaN` - so both spellings must
be handled. `common/score.py` already has the constant for this: `NO_SECTOR = "(no sector)"`.

- [ ] **Step 2: Run test to verify it fails**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: FAIL with `ImportError: cannot import name 'sector_neutralise'`

- [ ] **Step 3: Write minimal implementation**

```python
from common.score import NO_SECTOR, Profile   # NO_SECTOR = "(no sector)", already in common/score.py


def sector_labels(sectors: pd.Series, index: pd.Index) -> pd.Series:
    """Sector per ticker, with missing and blank labels folded into one explicit bucket.

    Companies without a sector must form a group of their own, not fall out of the loop -
    see the note above.
    """
    sec = sectors.reindex(index).astype(object)
    return sec.where(sec.notna() & (sec != ""), NO_SECTOR)


def sector_neutralise(weights: pd.Series, benchmark: pd.Series, sectors: pd.Series,
                      excluded: pd.Series | None = None) -> pd.Series:
    """Rescale each sector so its total equals the benchmark's, keeping order within it.

    Without this, a sector that scores badly for structural reasons (emissions intensity
    in Energy) is systematically underweighted, which is a sector bet rather than a
    company-quality bet. See the open question in docs/SCORING.md.
    """
    sec = sector_labels(sectors, weights.index)
    out = weights.copy()
    for name in sec.unique():
        members = sec[sec == name].index
        target = benchmark.reindex(members).sum()
        current = weights.reindex(members).sum()
        if current > 0:
            out.loc[members] = weights.loc[members] * (target / current)
        elif excluded is not None and bool(excluded.reindex(members).fillna(False).all()):
            # Every name in this sector was deliberately excluded. Falling back to the
            # benchmark here would SILENTLY RE-ADMIT them at full weight - the exact
            # opposite of the instruction. This is a real case, not a hypothetical: the
            # S&P 500 Energy sector is exactly the 21 Oil & Gas companies, so any
            # fossil-fuel exclusion empties the sector completely.
            out.loc[members] = 0.0
        else:
            out.loc[members] = benchmark.reindex(members)
    total = out.sum()
    if total <= 0:
        raise ValueError("every company was excluded - nothing left to allocate")
    return out / total
```

Every group is now covered, so the sector totals already add up to 1 and the final
`out / out.sum()` is a no-op that only guards against float drift. `benchmark.reindex(members)`
rather than `benchmark.loc[members]` so a ticker missing from the benchmark gives `NaN` instead of
a `KeyError` - it cannot happen through `allocate()`, where both come from the same table.

- [ ] **Step 4: Run test to verify it passes**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
python run.py save "[portfolio] sector_neutralise: sector totals match the benchmark"
```

---

### Task 5: Iterative maximum-weight cap

**Files:**
- Modify: `portfolio/allocate.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: any weight `pd.Series` summing to 1.
- Produces: `apply_cap(weights: pd.Series, max_weight: float) -> pd.Series` and
  `cap_by_sector(weights: pd.Series, sectors: pd.Series, max_weight: float) -> pd.Series`

- [ ] **Step 1: Write the failing test**

```python
from portfolio.allocate import apply_cap, cap_by_sector


def test_cap_limits_the_largest_and_keeps_the_sum():
    w = pd.Series({"A": 0.7, "B": 0.2, "C": 0.1})
    out = apply_cap(w, 0.4)
    assert out.max() <= 0.4 + 1e-9
    assert out.sum() == pytest.approx(1.0)


def test_redistribution_can_push_a_second_name_over_the_cap_and_is_repeated():
    w = pd.Series({"A": 0.60, "B": 0.35, "C": 0.05})
    out = apply_cap(w, 0.4)
    assert out["A"] <= 0.4 + 1e-9
    assert out["B"] <= 0.4 + 1e-9
    assert out.sum() == pytest.approx(1.0)


def test_cap_at_or_above_equal_weight_changes_nothing():
    w = pd.Series({"A": 0.5, "B": 0.5})
    out = apply_cap(w, 0.9)
    assert out.round(10).to_dict() == w.round(10).to_dict()


def test_cap_exactly_equal_weight_flattens_everything():
    out = apply_cap(pd.Series({"A": 0.7, "B": 0.2, "C": 0.1}), 1 / 3)
    assert out["A"] == pytest.approx(1 / 3)
    assert out["C"] == pytest.approx(1 / 3)


def test_cap_below_equal_weight_is_rejected():
    w = pd.Series({"A": 0.5, "B": 0.5})
    with pytest.raises(ValueError):
        apply_cap(w, 0.1)   # 2 names cannot fit under a 10% cap


def test_cap_counts_only_companies_that_can_hold_weight():
    # C is excluded (0.0) and can never absorb anything, so a 34% cap is infeasible here
    with pytest.raises(ValueError):
        apply_cap(pd.Series({"A": 0.5, "B": 0.5, "C": 0.0}), 0.34)


def test_excluded_names_never_get_weight_back_from_the_cap():
    out = apply_cap(pd.Series({"A": 0.8, "B": 0.2, "C": 0.0}), 0.5)
    assert out["C"] == 0.0
    assert out.max() <= 0.5 + 1e-9


def test_cap_by_sector_keeps_sector_totals_and_honours_the_cap():
    weights = pd.Series({"A": 0.40, "B": 0.10, "C": 0.25, "D": 0.25})
    sectors = pd.Series({"A": "Tech", "B": "Tech", "C": "Energy", "D": "Energy"})
    out = cap_by_sector(weights, sectors, 0.35)
    assert out.max() <= 0.35 + 1e-9
    assert out[["A", "B"]].sum() == pytest.approx(0.5)   # Tech total untouched
    assert out.sum() == pytest.approx(1.0)
```

**`test_cap_counts_only_companies_that_can_hold_weight` is the bug this task nearly shipped.**
The obvious feasibility guard, `max_weight * len(weights) < 1`, counts names that hold zero -
exactly what `exclude_worst` produces. Run on `{"A": 0.5, "B": 0.5, "C": 0.0}` with a 0.34 cap it
passes the guard (`0.34 * 3 = 1.02`), caps A and B to 0.34, finds no room to place the excess
(C is 0 and stays 0 by construction), breaks out of the loop, and the closing `out / out.sum()`
divides `{0.34, 0.34, 0}` by 0.68 - returning **`{"A": 0.5, "B": 0.5, "C": 0.0}`, a silent cap
violation with no error**. Reproduced. Counting only `(weights > 0).sum()` turns it into the
`ValueError` it should always have been.

- [ ] **Step 2: Run test to verify it fails**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: FAIL with `ImportError: cannot import name 'apply_cap'`

- [ ] **Step 3: Write minimal implementation**

```python
def apply_cap(weights: pd.Series, max_weight: float, max_rounds: int = 100) -> pd.Series:
    """Cap each weight, spreading the excess over the uncapped names, repeatedly.

    One pass is not enough: redistributing can push another name over the cap.
    Feasibility counts only the names that already hold weight - a name at 0.0 was
    excluded on purpose and must not be revived to make the cap fit.
    """
    holdable = int((weights > 0).sum())
    if max_weight <= 0 or holdable == 0 or max_weight * holdable < 1 - 1e-12:
        needed = 1 / holdable if holdable else float("inf")
        raise ValueError(
            f"max_weight {max_weight} cannot hold {holdable} companies with weight - "
            f"needs at least {needed:.4f}"
        )
    out = weights.copy()
    for _ in range(max_rounds):
        over = out > max_weight + 1e-12
        if not over.any():
            break
        excess = (out[over] - max_weight).sum()
        out[over] = max_weight
        free = ~over
        room = out[free]
        if room.sum() <= 0:
            break
        out[free] = room + excess * (room / room.sum())
    return out / out.sum()


def cap_by_sector(weights: pd.Series, sectors: pd.Series, max_weight: float) -> pd.Series:
    """Cap inside each sector, so capping cannot move weight from one sector to another.

    A global cap redistributes a capped name's excess across the whole universe, which
    hands weight to other sectors and undoes sector neutrality (see Task 7).
    """
    sec = sector_labels(sectors, weights.index)
    out = weights.copy()
    for name in sec.unique():
        members = sec[sec == name].index
        target = weights.reindex(members).sum()
        if target <= 0:
            continue
        share = weights.loc[members] / target          # weights within the sector, summing to 1
        try:
            out.loc[members] = apply_cap(share, max_weight / target) * target
        except ValueError as err:
            raise ValueError(
                f"sector '{name}' holds {target:.4f} of the portfolio across "
                f"{int((share > 0).sum())} companies - a {max_weight:.2%} cap cannot fit it"
            ) from err
    return out / out.sum()
```

`cap_by_sector` rescales each sector to its own 0-1 problem, caps it with the same routine at
`max_weight / sector_total`, and scales back - so every sector total is preserved exactly and the
per-company cap still holds. With the equal-weight benchmark it is always feasible (a sector of
`k` of `n` companies targets `k/n`, so the per-name room is `1/n`, well under any sensible cap);
it can only become infeasible once real market caps arrive, and then it names the offending
sector instead of silently drifting.

- [ ] **Step 4: Run test to verify it passes**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: 23 passed

- [ ] **Step 5: Commit**

```bash
python run.py save "[portfolio] apply_cap: iterative max weight per company"
```

---

### Task 6: Exclusion method

**Files:**
- Modify: `portfolio/allocate.py`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: `benchmark_weights` output, `scores` table.
- Produces: `exclude_worst(benchmark: pd.Series, scores: pd.DataFrame, bottom_pct: float) -> pd.Series`

- [ ] **Step 1: Write the failing test**

```python
from portfolio.allocate import exclude_worst


def test_excludes_the_bottom_share_and_renormalises():
    scores = table([("A", "Tech", 90.0), ("B", "Tech", 70.0),
                    ("C", "Energy", 50.0), ("D", "Energy", 10.0)])
    bench = pd.Series({"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25})
    out = exclude_worst(bench, scores, 0.25)
    assert out["D"] == 0.0
    assert out.sum() == pytest.approx(1.0)
    assert out["A"] == pytest.approx(1 / 3)


def test_unscored_companies_are_never_excluded():
    scores = table([("A", "Tech", 90.0), ("B", "Tech", 10.0), ("C", "Energy", float("nan"))])
    bench = pd.Series({"A": 1 / 3, "B": 1 / 3, "C": 1 / 3})
    out = exclude_worst(bench, scores, 0.5)
    assert out["C"] > 0          # missing data is not a reason to divest
    assert out["B"] == 0.0


def test_bottom_pct_outside_zero_to_one_is_rejected():
    scores = table([("A", "Tech", 90.0), ("B", "Tech", 10.0)])
    bench = pd.Series({"A": 0.5, "B": 0.5})
    for bad in (-0.1, 1.0, 2.0):
        with pytest.raises(ValueError):
            exclude_worst(bench, scores, bad)
```

Without the range check a negative `bottom_pct` is not an error but a silent no-op:
`exclude_worst(bench, scores, -0.5)` returned `{"A": 0.5, "B": 0.5}` - a typo in a profile would
quietly turn exclusion off. `1.0` and above already raise, but only by accident, from the
"excluded every company" branch at the end.

- [ ] **Step 2: Run test to verify it fails**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: FAIL with `ImportError: cannot import name 'exclude_worst'`

- [ ] **Step 3: Write minimal implementation**

```python
def exclude_worst(benchmark: pd.Series, scores: pd.DataFrame, bottom_pct: float) -> pd.Series:
    """Drop the worst `bottom_pct` of SCORED companies; keep everything else.

    Only scored companies can be excluded. Divesting because we failed to collect data
    would turn a coverage gap into an investment decision.
    """
    if not 0 <= bottom_pct < 1:
        raise ValueError(f"bottom_pct must be in [0, 1), got {bottom_pct}")
    values = pd.Series(scores["total_score"].to_numpy(), index=scores["ticker"].astype(str), dtype=float)
    scored = values.dropna()
    n_drop = int(len(scored) * bottom_pct)   # truncates: 503 scored at 0.1 -> 50 dropped
    out = benchmark.copy()
    if n_drop > 0:
        out.loc[scored.nsmallest(n_drop).index] = 0.0
    if out.sum() <= 0:
        raise ValueError(f"bottom_pct {bottom_pct} excluded every company")
    return out / out.sum()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: 26 passed

- [ ] **Step 5: Commit**

```bash
python run.py save "[portfolio] exclude_worst: drop the bottom X% of scored companies"
```

---

### Task 7: Compose `allocate()`

**Files:**
- Modify: `portfolio/allocate.py` (replace the `NotImplementedError` body)
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: `benchmark_weights`, `score_z`, `tilt`, `sector_neutralise`, `apply_cap`,
  `cap_by_sector`, `exclude_worst`.
- Produces: `allocate(scores, profile, fund_usd=1e9) -> pd.DataFrame[ticker, weight, reason]`.

- [ ] **Step 1: Write the failing test**

```python
from common.score import Profile
from portfolio.allocate import allocate


def full_table(rows):
    return pd.DataFrame(rows, columns=["ticker", "name", "sector", "total_score"])


def profile(**portfolio):
    """A Profile for the tiny test tables. max_weight 1.0 unless a test says otherwise:
    two or three companies cannot physically fit under the 5% production cap."""
    return Profile(name="t", portfolio={"max_weight": 1.0, **portfolio})


def test_allocate_returns_the_fixed_columns_and_sums_to_one():
    scores = full_table([("A", "Alpha", "Tech", 90.0), ("B", "Beta", "Tech", 50.0),
                         ("C", "Gamma", "Energy", 10.0)])
    out = allocate(scores, profile())
    assert list(out.columns) == ["ticker", "weight", "reason"]
    assert out["weight"].sum() == pytest.approx(1.0)
    assert len(out) == 3


def test_default_tilt_overweights_the_leader():
    scores = full_table([("A", "Alpha", "Tech", 90.0), ("B", "Beta", "Tech", 10.0)])
    w = allocate(scores, profile()).set_index("ticker")["weight"]
    assert w["A"] > w["B"]


def test_reason_explains_every_row():
    scores = full_table([("A", "Alpha", "Tech", 90.0), ("B", "Beta", "Tech", float("nan"))])
    reasons = allocate(scores, profile()).set_index("ticker")["reason"]
    assert "no score" in reasons["B"].lower()
    assert reasons["A"]


def test_sector_neutrality_survives_the_cap():
    scores = full_table([("A", "Alpha", "Tech", 99.0), ("B", "Beta", "Tech", 1.0),
                         ("C", "Gamma", "Energy", 60.0), ("D", "Delta", "Energy", 40.0)])
    w = allocate(scores, profile(tilt_strength=3.0, max_weight=0.35)).set_index("ticker")["weight"]
    assert w.max() <= 0.35 + 1e-9
    assert w[["A", "B"]].sum() == pytest.approx(0.5)   # both constraints hold at once
    assert w.sum() == pytest.approx(1.0)


def test_unknown_method_is_rejected():
    scores = full_table([("A", "Alpha", "Tech", 90.0), ("B", "Beta", "Tech", 10.0)])
    with pytest.raises(ValueError):
        allocate(scores, profile(method="magic"))
```

**Two defects this step must not repeat.**

1. **`Profile` does not take `categories=` / `indicators=`.** The real field names are
   `category_weights` and `indicator_weights` (see the verified facts at the top). Every call
   `Profile(name="t", description="", categories={}, indicators={})` fails at collection time with
   `TypeError: Profile.__init__() got an unexpected keyword argument 'categories'` - all three
   original Task 7 tests failed this way before anything else was even exercised. Use the
   `profile()` helper above.
2. **The 5% default cap is infeasible on a 2- or 3-name test table.** With the constructor fixed,
   the same three tests then failed with
   `ValueError: max_weight 0.05 cannot hold 2 companies - needs at least 0.5000`, raised from
   `apply_cap`. Do **not** "fix" this by clamping the cap inside `allocate()`: clamping a 2-name
   universe to a 0.5 cap flattens the tilt and `test_default_tilt_overweights_the_leader` then
   fails on `w["A"] > w["B"]` because both land on exactly 0.5. The honest fix is the test helper -
   a tiny universe genuinely cannot honour a 5% cap, and `apply_cap` saying so is correct
   behaviour, not a bug to route around.

**Why `test_sector_neutrality_survives_the_cap` exists.** `sector_neutralise` followed by a global
`apply_cap` is **order-dependent and the cap wins**: capping a name spreads its excess across the
whole universe, including other sectors, so the sector totals `sector_neutralise` just fixed drift
straight back out. Measured on a 4-name table, Tech went from exactly 0.5 after neutralising to
0.4312 after `apply_cap(0.35)`. On the real 503-company table it is invisible at the default
settings only because the cap never binds there (the largest weight at `tilt_strength = 0.6` is
0.0068, well under 0.05) - push `tilt_strength` to 4.0 and the cap bites, and the worst sector
drifts **1.595 percentage points** from its benchmark weight. Since sector neutrality is the whole
argument of Task 4, the cap has to be applied inside each sector (`cap_by_sector`, Task 5), which
holds both constraints exactly: the same 503-name run at `tilt_strength = 4.0` gives max weight
0.05 and a maximum sector deviation of 0.0.

- [ ] **Step 2: Run test to verify it fails**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: FAIL with `NotImplementedError: portfolio allocation is phase 3`. If you instead see
`TypeError: Profile.__init__() got an unexpected keyword argument 'categories'`, you copied the
old test - fix the constructor before reading anything into the failure.

- [ ] **Step 3: Write minimal implementation**

```python
DEFAULTS = {
    "method": "tilt",
    "tilt_strength": 0.6,
    "exclude_bottom_pct": 0.1,
    "max_weight": 0.05,
    "sector_neutral": True,
}


def allocate(scores: pd.DataFrame, profile: Profile, fund_usd: float = 1e9) -> pd.DataFrame:
    """scores: Result.table from common.score.score_profile. Returns OUTPUT_COLUMNS.

    fund_usd is part of the fixed interface but unused: OUTPUT_COLUMNS has no dollar column.
    """
    settings = {**DEFAULTS, **(getattr(profile, "portfolio", None) or {})}
    if settings["method"] not in {"tilt", "exclude"}:
        raise ValueError(f"unknown portfolio method '{settings['method']}' - use 'tilt' or 'exclude'")
    tickers = scores["ticker"].astype(str)
    sectors = pd.Series(scores["sector"].to_numpy(), index=tickers)

    bench = benchmark_weights(scores)
    z = score_z(scores)

    if settings["method"] == "exclude":
        weights = exclude_worst(bench, scores, float(settings["exclude_bottom_pct"]))
        how = f"excluded bottom {float(settings['exclude_bottom_pct']):.0%}"
    else:
        weights = tilt(bench, z, float(settings["tilt_strength"]))
        how = f"tilt strength {float(settings['tilt_strength'])}"

    cap = float(settings["max_weight"])
    if settings["sector_neutral"]:
        # Pass the exclusion mask so an emptied sector stays empty instead of being
        # refilled from the benchmark.
        excluded = weights <= 0 if settings["method"] == "exclude" else None
        weights = sector_neutralise(weights, bench, sectors, excluded)
        weights = cap_by_sector(weights, sectors, cap)   # NOT apply_cap - see the note above
    else:
        weights = apply_cap(weights, cap)

    scored = pd.Series(scores["total_score"].to_numpy(), index=tickers, dtype=float)
    reason = [
        "no score - held at benchmark weight" if pd.isna(scored[t])
        else f"score {scored[t]:.0f}, z {z[t]:+.2f}, {how}"
        for t in weights.index
    ]
    return pd.DataFrame(
        {"ticker": weights.index, "weight": weights.to_numpy(), "reason": reason}
    ).sort_values("weight", ascending=False).reset_index(drop=True)[OUTPUT_COLUMNS]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v && python run.py check`
Expected: 31 passed, and `run.py check` OK (the rest of the suite was 36 passed before this plan,
so `run.py check` should report 67 passed)

- [ ] **Step 5: Commit**

```bash
python run.py save "[portfolio] allocate: sector-neutral capped tilt, unscored held at benchmark"
```

---

### Task 8: Profile settings and a real end-to-end run

**Files:**
- Modify: `profiles/balanced.toml`
- Test: `tests/test_portfolio.py`

**Interfaces:**
- Consumes: `allocate`.
- Produces: a `[portfolio]` block that `profile_from_dict` carries through.

- [ ] **Step 1: Write the failing test**

```python
def test_profile_settings_override_the_defaults():
    scores = full_table([("A", "Alpha", "Tech", 90.0), ("B", "Beta", "Tech", 10.0)])
    p = Profile(name="t", portfolio={"method": "tilt", "tilt_strength": 0.0,
                                     "max_weight": 1.0, "sector_neutral": False})
    out = allocate(scores, p).set_index("ticker")["weight"]
    assert out["A"] == pytest.approx(0.5)   # strength 0 -> equal-weight benchmark


def test_balanced_profile_ships_portfolio_settings():
    from common.score import load_profile

    settings = load_profile("balanced").portfolio
    assert settings.get("method") in {"tilt", "exclude"}
    assert 0 < float(settings["max_weight"]) <= 1
```

**Only the second test is red.** `Profile` already has a `portfolio` field and `allocate` already
reads it, so `test_profile_settings_override_the_defaults` passes the moment Task 7 is green - it
is a regression guard, not a red step. The genuinely failing one is
`test_balanced_profile_ships_portfolio_settings`: `load_profile("balanced").portfolio` is `{}`
today, so it fails until the TOML block below exists. Keep both; run them in this order.

- [ ] **Step 2: Run test to verify it fails**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py::test_balanced_profile_ships_portfolio_settings -v`
Expected: FAIL - `load_profile("balanced").portfolio` is the empty dict, so `settings.get("method")`
is `None` and the assertion fails.

- [ ] **Step 3: Write minimal implementation**

Append to `profiles/balanced.toml` (after the `[categories]` block - a TOML table runs to the next
table header, so this must go last, not between the top-level keys):

```toml
[portfolio]
method = "tilt"
tilt_strength = 0.6
max_weight = 0.05
sector_neutral = true
```

**No change to `common/score.py` is needed.** `Profile` already declares
`portfolio: dict = field(default_factory=dict)` and `profile_from_dict` already does
`portfolio=dict(data.get("portfolio", {}))`; verified by parsing `balanced.toml` with this block
appended, which yields
`{'method': 'tilt', 'tilt_strength': 0.6, 'max_weight': 0.05, 'sector_neutral': True}`.
`profile_to_toml` also writes the block back out, so profiles saved from the dashboard keep it.
`common/validate.py` never reads `profiles/*.toml`, so `run.py check` is unaffected.
`profiles/` is still Arash's area - this stays a proposal for him to merge.

- [ ] **Step 3b: Run the whole suite**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: 33 passed

- [ ] **Step 4: Verify against real scores**

Run:
```bash
python run.py score balanced
/venvs/python_general/bin/python -c "
import pandas as pd
from common.score import load_profile
from portfolio.allocate import allocate
s = pd.read_csv('scores/balanced/scores.csv')
p = load_profile('balanced')
w = allocate(s, p)
print(w.head(10).to_string(index=False))
print('sum', w.weight.sum(), '| max', w.weight.max(), '| names', (w.weight > 0).sum())

# the cap and sector neutrality are both inert at strength 0.6 - prove them where they bite
sec = s.set_index('ticker')['sector']
bench = pd.Series(1 / len(s), index=s.ticker)
p.portfolio = {**p.portfolio, 'tilt_strength': 4.0}
hard = allocate(s, p).set_index('ticker')['weight']
drift = (hard.groupby(sec).sum() - bench.groupby(sec).sum()).abs().max()
print('strength 4.0: max', hard.max(), '| worst sector drift', drift)
"
```
Expected: 503 rows, weights sum to 1.0, every company present, and at `tilt_strength = 0.6` a max
weight of about 0.0068 - i.e. **the 5% cap never binds at the default settings, so this run does
not test it**. That is why the second half pushes the strength to 4.0, where the expected output is
max weight 0.05 and a worst-case sector drift of 0.0. A drift around 0.016 means `allocate()` is
still using the global `apply_cap` instead of `cap_by_sector` (Task 7).

Also worth knowing before you read the numbers: today all 503 companies have a `total_score`, so
the "unscored companies keep their benchmark weight" path - the constraint this whole plan is built
around - is **not** exercised by this run. To see it, drop the scores of a few tickers in a local
copy of the CSV and check that their weight comes back at exactly `1/503` and their reason reads
"no score".

- [ ] **Step 5: Commit**

```bash
python run.py save "[portfolio] balanced profile gets a [portfolio] block; verified on real scores"
```

---

## Open questions for Arash

1. **Market cap.** `universe/` has no market caps, so the benchmark is equal weight.
   `sp500/data/marketcaps.csv` exists outside the repo. Adding `universe/marketcaps.csv`
   switches Task 1 to a real index benchmark with no code change.
2. ~~**`Profile.portfolio`.**~~ **Closed.** The field already exists on the dataclass
   (`portfolio: dict = field(default_factory=dict)`) and `profile_from_dict` /`profile_to_toml`
   already read and write the `[portfolio]` block. Nothing is needed in `common/score.py`.
   `allocate` keeps the `getattr` only so a hand-built `Profile` from an older pickle still works.
3. **Quarterly backtest.** `sp500/sp500_sim.py` already rebalances every 3 months. Once
   the `quarter` column lands, `allocate` can be called per quarter to produce a real
   10-year backtest instead of today's weights applied to the past.
4. **Capping versus sector neutrality, if market caps arrive.** `cap_by_sector` is exactly
   feasible under an equal-weight benchmark for any cap at or above `1/n`. Under real market-cap
   weights a single sector can be too heavy to fit under a 5% per-name cap; the code then raises
   naming the sector. Your call whether that should instead relax the cap or the neutrality.
5. **Fixed `total_score` snapshot.** `allocate` re-standardises the scores it is handed, so the
   weights move whenever coverage changes, even if no company changed. Fine for a hackathon;
   worth a frozen reference distribution before anyone calls it a strategy.

---

## Adversarial review, 2026-09-12

Every code block in this plan was extracted into a scratch package under `/tmp` (real `common/`
symlinked in, `portfolio/allocate.py` rebuilt task by task) and run with
`/venvs/python_general/bin/python -m pytest`. Defects found and fixed above:

| # | Task | Defect | Evidence |
|---|---|---|---|
| 1 | 7, 8 | `Profile(name="t", description="", categories={}, indicators={})` is not the real dataclass | `TypeError: ... unexpected keyword argument 'categories'`, 3 failed 18 passed |
| 2 | 7 | the default 5% cap is infeasible on a 2-3 name test table | `ValueError: max_weight 0.05 cannot hold 2 companies`, 3 failed 18 passed after fixing #1 |
| 3 | 4, 5, 7 | `sector_neutralise` then a global `apply_cap` undoes sector neutrality | Tech 0.5 -> 0.4312 on a toy table; 1.595 pp worst-sector drift on the real 503 names at strength 4.0 |
| 4 | 5 | `apply_cap` silently violates the cap when zero weights are present | `apply_cap({A:0.5, B:0.5, C:0.0}, 0.34)` returned `{A:0.5, B:0.5, C:0.0}` |
| 5 | 4 | companies with a missing sector fall out of the loop and skew every sector | unlabelled member -> Tech 0.6897 against a 0.6667 target |
| 6 | 1 | duplicate tickers reach `allocate` and crash unreadably | `ValueError: The truth value of a Series is ambiguous` |
| 7 | 1 | an empty universe divides by zero | `ZeroDivisionError: float division by zero` |
| 8 | 6 | a negative `bottom_pct` is a silent no-op | `exclude_worst(bench, scores, -0.5)` returned the untouched benchmark |
| 9 | 8 | the Task 8 test was never red - it passes as soon as Task 7 is green | replaced with a `load_profile("balanced").portfolio` assertion |

The originally claimed pass counts 3 / 6 / 9 / 12 / 16 / 18 / 21 were **all reproduced exactly for
Tasks 1-6** as written (3, 6, 9, 12, 16, 18). Task 7 was the first break: 3 failed, 18 passed. The
counts in this plan are now 4 / 8 / 11 / 15 / 23 / 26 / 31 / 33, and the full hardened suite was
executed end to end: **33 passed**. Edge cases checked and now covered or guarded: single-company
universe (weight 1.0), all scores NaN (falls back to the plain benchmark), single-member sector
(gets exactly its benchmark weight), `max_weight` exactly `1/n` (flattens to equal weight,
converges), duplicate tickers and empty universe (both rejected with a readable message).
