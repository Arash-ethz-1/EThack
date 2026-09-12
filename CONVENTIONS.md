# CONVENTIONS.md

Five people, twenty hours, one repo. These rules exist so that nobody spends 03:00
resolving a merge conflict instead of shipping. Read the ownership table first.

---

## 1. File ownership - the rule that saves the night

**You may only edit files you own.** If you need a change elsewhere, message the
owner. This is not bureaucracy; it is the reason five people can merge into `main`
all night without a single conflict, and the reason our branches need no review.

| Path | Owner | Notes |
|---|---|---|
| `CLAUDE.md`, `CONVENTIONS.md`, `Makefile`, `requirements.txt` | **Arash** | ask before proposing changes |
| `src/ethack/contracts.py` | **Arash** | frozen; changes need the downstream owner's OK |
| `src/ethack/sources/epa.py` `echo.py` `satellite.py` `reports.py` | **Jean** | all acquisition |
| `src/ethack/sources/sec.py` `ex21.py` | **Arash** | needed for the link layer |
| `src/ethack/link.py` | **Arash** | critical path |
| `src/ethack/indicators/base.py` `registry.py` | **Arash** | the framework |
| `src/ethack/indicators/impl/*.py` | **Lauren** | one file per indicator |
| `src/ethack/score.py` | **Lauren** | |
| `src/ethack/blackout.py` | **Arash** | |
| `src/ethack/portfolio/*` | **Florian** | |
| `src/ethack/eval/*` | **Harprit** | |
| `app/main.py`, `app/pages/1_explorer.py`, `app/pages/2_blackout.py` | **Arash** | shell + wow demo |
| `app/pages/3_portfolio.py` | **Florian** | |
| `app/pages/4_evaluation.py` | **Harprit** | |
| `data/raw/*`, `data/PROVENANCE.md` | **Jean** | append only |
| `data/manual/reported_scope1.csv` | **Jean** | agent output + hand benchmark |
| `data/manual/link_labels.csv` | **Arash** | training labels for the reranker |
| `tests/test_<yourmodule>.py` | **whoever owns the module** | |
| `docs/tasks/<name>.md` | **that person** | edit your own plan freely |
| `METRICS.md` | **Harprit** | |
| `figures/*` | producer of the figure | |
| `PROGRESS.md` | **everyone, own section only** | append-only; never touch another section |

Anyone may **read** anything. Anyone may **open an issue** about anything.

## 2. Git

`main` is protected by convention: **nobody commits on `main`, ever.** Every piece
of work is a short-lived branch that gets rebased onto `main` and fast-forwarded in.
The ownership table means we still do not need review cycles - the branch is there
so that `main` is never mid-edit, and so a broken change is one `git switch` away
from being undone instead of a revert on top of four other people's commits.

**The loop. Every single time.**

```bash
# 1. start from the truth, never from what you had an hour ago
git switch main
git pull --rebase origin main

# 2. branch for the thing you are about to do - one task, one branch
git switch -c arash/link-ex21

# 3. work. commit every 30-45 min.
python run.py test
git add -A && git commit -m "[link] add EX-21 subsidiary registry scraper"

# 4. log it in PROGRESS.md under your own section, then commit that too
git commit -am "[docs] progress: EX-21 scraper, 487/503 resolved"

# 5. pull again - other people moved while you worked - and replay on top
git pull --rebase origin main
python run.py test          # green on top of THEIR work, not just yours

# 6. fast-forward into main and push
git switch main
git pull --rebase origin main
git merge --ff-only arash/link-ex21
git push origin main

# 7. bin the branch
git branch -d arash/link-ex21
```

`python run.py sync` does steps 1 and `python run.py ship <branch>` does 5-7. Use them.

If `--ff-only` refuses, someone pushed while you were in step 5. That is not an
error, it is the check working: `git switch -` back, `git pull --rebase origin main`
again, re-run `python run.py test`, retry.

**Branch names:** `<yourname>/<short-thing>`. `jean/ghgrp-backfill`,
`lauren/say-do-indicator`, `harprit/enforcement-oos`. Your name first so `git branch -a`
sorts by person.

**Rules**

1. `main` must always run. If `python run.py all` on mocks is broken, that is a
   drop-everything emergency, and it belongs to whoever broke it.
2. **Never** `git push --force`, to `main` or to a branch someone else has checked
   out. Not once, not "just quickly".
3. **Always** `--rebase` on pull, and **always** `--ff-only` on the merge into `main`.
   We want a linear history; merge commits from five people overnight make the log
   unreadable and make "what broke the headline number?" unanswerable.
4. **Always pull before you start and again before you merge.** Twice, not once.
   The first pull stops you building on stale contracts; the second stops you
   shipping something that only passes against a `main` from two hours ago.
5. Commit small and often - every 30 to 45 minutes. A four-hour uncommitted chunk
   is an unrecoverable loss when a laptop dies at 04:00. Branches are local until
   pushed, so `git push -u origin <branch>` at least once an hour as a backup.
6. **Update `PROGRESS.md` in the same branch as the work it describes.** A progress
   entry that lands without its code is a lie with a timestamp.
7. One task per branch. If you notice a second thing, finish the first, merge,
   branch again. Branches that live longer than ~90 minutes are how you get the
   03:00 conflict this whole file exists to prevent.
8. Never commit secrets, `.env`, or `.streamlit/secrets.toml`.
9. `data/raw/` **is** committed. The archive is part of our thesis - see
   `docs/THESIS.md`. Everything derived (`data/processed/`, `data/mock/`) is not.

**When to use a pull request instead:** only for a change to `contracts.py`, the
ownership table, or `CLAUDE.md` - the three files that affect everyone. Push the
branch, open the PR, get the one affected owner to say yes in the channel, merge it
yourself. Do not wait for a review on your own files; that is what the ownership
table is for.

**Commit message format**

```
[layer] imperative summary in under 60 chars

Optional body: why, not what. Note any model or agent you used and why.
```

Valid layers: `sources` `link` `indicators` `score` `portfolio` `eval` `app`
`docs` `infra` `test`

```
[link] add EX-21 subsidiary registry scraper
[indicators] add metered carbon intensity, sector-relative
[eval] out-of-sample enforcement test, odds ratio 2.4 (n=380)
[app] blackout simulator: toggle a source, recompute tiers
```

If an AI agent wrote a meaningful part of the change, say so in the body. We want
to be able to answer "what did the AI actually do here?" precisely, in the pitch.

## 3. Testing - proportionate, not performative

We are not chasing coverage. We are buying insurance against the two failures that
actually kill hackathon projects: a silent schema drift, and a 03:00 regression in a
headline number.

**Required**

1. **Contract tests.** Every layer's output validates against its schema in
   `contracts.py`. One test per contract. These catch the integration bug that
   otherwise surfaces at 06:00 when you wire the dashboard.
2. **Indicator tests.** Every indicator in `impl/` needs a test that it
   (a) returns a Series indexed by ticker, (b) respects its declared direction,
   (c) returns NaN rather than crashing on missing input.
3. **Smoke test.** `python run.py all` on mock data produces every expected artefact.
4. **Golden numbers.** Once a headline figure exists, pin it:
   `assert abs(score.loc["XOM"] - 0.31) < 0.01`. If someone's refactor moves it,
   we find out in seconds instead of in front of judges.

**Not required:** mocking every network call, property-based testing, >X% coverage.

**How to write them**

```python
# tests/test_indicators.py
import pandas as pd
from ethack.indicators.registry import get, all_specs

def test_every_indicator_declares_durability():
    for spec in all_specs():
        assert spec.durability is not None, f"{spec.id} has no durability rating"
        assert spec.rationale, f"{spec.id} has no rationale - it cannot go on a slide"

def test_carbon_intensity_handles_missing_revenue(mock_panel):
    panel = mock_panel.copy()
    panel.loc[panel.index[0], "revenue_usd"] = None
    out = get("carbon_intensity").compute(panel)
    assert out.isna().iloc[0]          # NaN, not a crash, not a zero
    assert out.notna().sum() > 0
```

Rules: every test runs in under 5 seconds and needs no network. Tests that need the
internet are marked `@pytest.mark.network` and are skipped by default
(`python run.py test` passes `-m "not network"`).

**Fixtures** live in `tests/conftest.py`. `mock_panel` is already there and is
built from the same generator as `python run.py mocks`, so if you change a contract the
tests break immediately - which is the point.

## 4. Code

- Python 3.11+, `pandas`, type hints on public functions. Format with `ruff format`.
- **Pure functions in the core.** `score.py`, `portfolio/`, `eval/` take dataframes
  and return dataframes. No file reads inside them, no network, no global state.
  This is what makes them testable and reproducible.
- All I/O lives in `sources/` and in the thin `__main__` blocks.
- Fail loudly on bad data, silently on missing data: raise on a schema violation,
  return NaN for a value we genuinely do not have. Never impute a zero for a
  missing emission - a zero is a claim, NaN is the truth.
- No magic numbers in the core. Carbon prices, weights and thresholds live in
  `src/ethack/config.py` so the dashboard can change them at runtime.

## 5. When you are blocked

Do not wait. `python run.py mocks` gives you schema-valid input for every layer. Build
against the mock, commit, and swap in real data when it lands. If you find
yourself waiting on another person for more than 20 minutes, you are working on
the wrong thing - check `docs/tasks/<yourname>.md` for what else is yours.
