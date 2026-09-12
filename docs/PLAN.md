# Plan

**Goal:** quantify the sustainability impact of S&P 500 companies in three categories,
and use it to weight a portfolio allocation.

## Phase 1 - Data extraction (now)

| Category | Owner | Folder | Task file |
|---|---|---|---|
| Economic impact | Arash | `economic/` | `docs/tasks/arash.md` |
| Social impact | Florian, Lauren | `social/` | `docs/tasks/florian.md`, `docs/tasks/lauren.md` |
| Environmental impact | Jean | `environmental/` | `docs/tasks/jean.md` |

**Done when**, for every category:
- [ ] `universe/sp500.csv` exists (Arash - blocks the ticker check for everyone)
- [ ] >= 3 indicators with status `ready` in the catalog (strong = criteria in `AGENTS.md` section 4)
- [ ] every indicator reproducible with `python run.py build <category>`
- [ ] `python run.py check` passes with no errors

Suggested order for each person:
1. Pick 4-5 candidate indicators, add them with `python run.py new-indicator` (status `idea`).
2. For each: find the source, check coverage fast (how many S&P 500 companies?). Drop weak ones early.
3. Build the best 3 to `ready`. A 4th/5th is a bonus, not a requirement.

## Phase 2 - Category scores (0-100)

`python run.py score` -> `scores/category_scores.csv`. Method in `docs/SCORING.md`.
The code exists and is tested; it produces real scores as soon as indicators are `ready`.

**Done when:** all three categories scored for >= 70% of the universe, and the team
has looked at the top/bottom 10 per category and agrees they make sense.

## Phase 3 - Portfolio allocation

Turn the three category scores into portfolio weights (`portfolio/`). To decide as a team:
- how to combine the categories (equal weights? fund's preference?)
- tilt vs. exclusion (overweight high scores vs. drop the bottom X%)
- constraints (sector neutrality vs. S&P 500, max weight per company)

## Decisions log

| Date | Decision |
|---|---|
| 2026-09-12 | Repo reset. New plan: three categories, >= 3 indicators each, 0-100 scores, then portfolio. |
| 2026-09-12 | Scores on a 0-100 scale; percentile-rank method v1 (docs/SCORING.md). |
| 2026-09-12 | Everyone works on `main` with small commits via `python run.py save`; folder ownership prevents conflicts. |
