# Plan

**Goal:** quantify the sustainability impact of S&P 500 companies in three categories,
and use it to weight a portfolio allocation.

## Phase 1 - Data extraction (now)

| Category | Owner | Folder |
|---|---|---|
| Economic impact | Lauren | `economic/` |
| Social impact | Florian, Lauren, Arash | `social/` |
| Environmental impact | Jean | `environmental/` |

**Done when**, for every category:
- [ ] `universe/sp500.csv` exists (Arash - blocks the ticker check for everyone)
- [ ] >= 3 indicators with status `ready` in the catalog (strong = criteria in `AGENTS.md` section 4)
- [ ] every indicator reproducible with `python run.py build <category>`
- [ ] `python run.py check` passes with no errors

Suggested order for each person:
1. Pick 4-5 candidate indicators, add them with `python run.py new-indicator` (status `idea`).
2. For each: find the source, check coverage fast (how many S&P 500 companies?). Drop weak ones early.
3. Build the best 3 to `ready`. A 4th/5th is a bonus, not a requirement.

## Phase 2 - Profiles, scores, dashboard (Arash)

The user of the tool (a fund, an investor) decides which indicators count and how much.
That choice is a **profile** (`profiles/<name>.toml`). `python run.py score <profile>` ->
`scores/<profile>/scores.csv`: a 0-100 score per category and a total score.
`python run.py dashboard` does the same interactively and explains every score.
Method in `docs/SCORING.md`. Built and tested on demo data; real scores appear as soon
as indicators are `ready`.

**Done when:** all three categories scored for >= 70% of the universe, and the team
has looked at the top/bottom 10 per category and agrees they make sense.

## Phase 3 - Portfolio allocation

Turn a profile's scores into portfolio weights (`portfolio/allocate.py` - interface fixed,
method is a placeholder; `profiles/net_zero.toml` answers the bonus question). To decide as a team:
- how to combine the categories (equal weights? fund's preference?)
- tilt vs. exclusion (overweight high scores vs. drop the bottom X%)
- constraints (sector neutrality vs. S&P 500, max weight per company)

## Decisions log

| Date | Decision |
|---|---|
| 2026-09-12 | Repo reset. New plan: three categories, >= 3 indicators each, 0-100 scores, then portfolio. |
| 2026-09-12 | Scores on a 0-100 scale; percentile-rank method v1 (docs/SCORING.md). |
| 2026-09-12 | Everyone works on `main` with small commits via `python run.py save`; folder ownership prevents conflicts. |
| 2026-09-12 | Lauren takes over `economic/`. Arash builds the rest of the pipeline: profiles, scoring, dashboard, portfolio placeholder. |
| 2026-09-12 | Users choose indicators + weights in a profile; total score = weighted mean of category scores. Dashboard: own web UI (`dashboard/static/`) on a stdlib Python server - no new dependency; the Workspace tab runs every `run.py` command. |
| 2026-09-12 | Task files (`docs/tasks/`) removed - everyone knows their work; progress = catalog `status` + commit messages. |
