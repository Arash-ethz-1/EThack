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


def test_benchmark_falls_back_to_equal_weight_for_missing_caps():
    scores = table([("A", "Tech", 80.0), ("B", "Tech", 40.0)])
    caps = pd.Series({"A": 300.0})  # B has no cap
    w = benchmark_weights(scores, caps)
    assert w.sum() == pytest.approx(1.0)
    assert w["B"] > 0
```

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
    if marketcaps is None or marketcaps.empty:
        return pd.Series(1.0 / len(tickers), index=tickers)
    caps = marketcaps.reindex(tickers)
    caps = caps.fillna(caps.median())
    return caps / caps.sum()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: 3 passed

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
```

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
Expected: 6 passed

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
Expected: 9 passed

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
- Produces: `sector_neutralise(weights: pd.Series, benchmark: pd.Series, sectors: pd.Series) -> pd.Series`

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: FAIL with `ImportError: cannot import name 'sector_neutralise'`

- [ ] **Step 3: Write minimal implementation**

```python
def sector_neutralise(weights: pd.Series, benchmark: pd.Series, sectors: pd.Series) -> pd.Series:
    """Rescale each sector so its total equals the benchmark's, keeping order within it.

    Without this, a sector that scores badly for structural reasons (emissions intensity
    in Energy) is systematically underweighted, which is a sector bet rather than a
    company-quality bet. See the open question in docs/SCORING.md.
    """
    sec = sectors.reindex(weights.index)
    out = weights.copy()
    for name in sec.dropna().unique():
        members = sec[sec == name].index
        target = benchmark.reindex(members).sum()
        current = weights.reindex(members).sum()
        if current > 0:
            out.loc[members] = weights.loc[members] * (target / current)
        else:
            out.loc[members] = benchmark.loc[members]
    return out / out.sum()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: 12 passed

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
- Produces: `apply_cap(weights: pd.Series, max_weight: float) -> pd.Series`

- [ ] **Step 1: Write the failing test**

```python
from portfolio.allocate import apply_cap


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


def test_cap_below_equal_weight_is_rejected():
    w = pd.Series({"A": 0.5, "B": 0.5})
    with pytest.raises(ValueError):
        apply_cap(w, 0.1)   # 2 names cannot fit under a 10% cap
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: FAIL with `ImportError: cannot import name 'apply_cap'`

- [ ] **Step 3: Write minimal implementation**

```python
def apply_cap(weights: pd.Series, max_weight: float, max_rounds: int = 100) -> pd.Series:
    """Cap each weight, spreading the excess over the uncapped names, repeatedly.

    One pass is not enough: redistributing can push another name over the cap.
    """
    if max_weight <= 0 or max_weight * len(weights) < 1 - 1e-12:
        raise ValueError(
            f"max_weight {max_weight} cannot hold {len(weights)} companies - "
            f"needs at least {1 / len(weights):.4f}"
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: 16 passed

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
```

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
    values = pd.Series(scores["total_score"].to_numpy(), index=scores["ticker"].astype(str), dtype=float)
    scored = values.dropna()
    n_drop = int(len(scored) * bottom_pct)
    out = benchmark.copy()
    if n_drop > 0:
        out.loc[scored.nsmallest(n_drop).index] = 0.0
    if out.sum() <= 0:
        raise ValueError(f"bottom_pct {bottom_pct} excluded every company")
    return out / out.sum()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: 18 passed

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
- Consumes: `benchmark_weights`, `score_z`, `tilt`, `sector_neutralise`, `apply_cap`, `exclude_worst`.
- Produces: `allocate(scores, profile, fund_usd=1e9) -> pd.DataFrame[ticker, weight, reason]`.

- [ ] **Step 1: Write the failing test**

```python
from common.score import Profile
from portfolio.allocate import allocate


def full_table(rows):
    return pd.DataFrame(rows, columns=["ticker", "name", "sector", "total_score"])


def test_allocate_returns_the_fixed_columns_and_sums_to_one():
    scores = full_table([("A", "Alpha", "Tech", 90.0), ("B", "Beta", "Tech", 50.0),
                         ("C", "Gamma", "Energy", 10.0)])
    out = allocate(scores, Profile(name="t", description="", categories={}, indicators={}))
    assert list(out.columns) == ["ticker", "weight", "reason"]
    assert out["weight"].sum() == pytest.approx(1.0)
    assert len(out) == 3


def test_default_tilt_overweights_the_leader():
    scores = full_table([("A", "Alpha", "Tech", 90.0), ("B", "Beta", "Tech", 10.0)])
    out = allocate(scores, Profile(name="t", description="", categories={}, indicators={}))
    w = out.set_index("ticker")["weight"]
    assert w["A"] > w["B"]


def test_reason_explains_every_row():
    scores = full_table([("A", "Alpha", "Tech", 90.0), ("B", "Beta", "Tech", float("nan"))])
    out = allocate(scores, Profile(name="t", description="", categories={}, indicators={}))
    reasons = out.set_index("ticker")["reason"]
    assert "no score" in reasons["B"].lower()
    assert reasons["A"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py -v`
Expected: FAIL with `NotImplementedError: portfolio allocation is phase 3`

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
    """scores: Result.table from common.score.score_profile. Returns OUTPUT_COLUMNS."""
    settings = {**DEFAULTS, **(getattr(profile, "portfolio", None) or {})}
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

    if settings["sector_neutral"]:
        weights = sector_neutralise(weights, bench, sectors)
    weights = apply_cap(weights, float(settings["max_weight"]))

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
Expected: 21 passed, and `run.py check` OK

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
    p = Profile(name="t", description="", categories={}, indicators={})
    p.portfolio = {"method": "tilt", "tilt_strength": 0.0, "max_weight": 1.0,
                   "sector_neutral": False}
    out = allocate(scores, p).set_index("ticker")["weight"]
    assert out["A"] == pytest.approx(0.5)   # strength 0 -> equal-weight benchmark
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/venvs/python_general/bin/python -m pytest tests/test_portfolio.py::test_profile_settings_override_the_defaults -v`
Expected: FAIL - `Profile` has no `portfolio` attribute, or the override is ignored

- [ ] **Step 3: Write minimal implementation**

Add to `profiles/balanced.toml`:

```toml
[portfolio]
method = "tilt"
tilt_strength = 0.6
max_weight = 0.05
sector_neutral = true
```

If `Profile` does not carry a `portfolio` field, `allocate` already reads it defensively
via `getattr(profile, "portfolio", None)`. Ask Arash before adding the field to the
dataclass in `common/score.py` - that file is his.

- [ ] **Step 4: Verify against real scores**

Run:
```bash
python run.py score balanced
/venvs/python_general/bin/python -c "
import pandas as pd
from common.score import load_profile
from portfolio.allocate import allocate
s = pd.read_csv('scores/balanced/scores.csv')
w = allocate(s, load_profile('balanced'))
print(w.head(10).to_string(index=False))
print('sum', w.weight.sum(), '| max', w.weight.max(), '| names', (w.weight > 0).sum())
"
```
Expected: weights sum to 1.0, max <= 0.05, every company present.

- [ ] **Step 5: Commit**

```bash
python run.py save "[portfolio] balanced profile gets a [portfolio] block; verified on real scores"
```

---

## Open questions for Arash

1. **Market cap.** `universe/` has no market caps, so the benchmark is equal weight.
   `sp500/data/marketcaps.csv` exists outside the repo. Adding `universe/marketcaps.csv`
   switches Task 1 to a real index benchmark with no code change.
2. **`Profile.portfolio`.** `allocate` reads it with `getattr` so nothing breaks today,
   but a real field on the dataclass in `common/score.py` would be cleaner. Your file.
3. **Quarterly backtest.** `sp500/sp500_sim.py` already rebalances every 3 months. Once
   the `quarter` column lands, `allocate` can be called per quarter to produce a real
   10-year backtest instead of today's weights applied to the past.
