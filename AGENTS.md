# AGENTS.md - rules for every AI agent in this repo

Read this whole file before your first action. It is short on purpose.

**The people you help are often not developers and do not know git.** You are
responsible for keeping the repo clean on their behalf. Do not ask them to type git
commands - use `python run.py ...`, which is built to be safe. Explain what you did
in plain language.

---

## 1. What we are building

EThack, challenge: quantify and compare the sustainability of **S&P 500 companies**
for an ETH-affiliated fund.

| Phase | Goal | Status |
|---|---|---|
| **1. Data extraction** | each category has **>= 3 strong sub-indicators** in the shared format | **now** |
| 2. Scoring | the user picks indicators + weights (**profile**) -> 0-100 score per category + total (`python run.py score`, `python run.py dashboard`) | pipeline + dashboard built, needs data |
| 3. Portfolio | use a profile's scores to **weight a portfolio allocation** | placeholder in `portfolio/allocate.py` |

Full plan: `docs/PLAN.md`.

## 2. Who owns what

**Only edit files in the area of the person you are helping.** This is what keeps
four people from overwriting each other. Anyone may read anything.

| Area | Owner | Topic |
|---|---|---|
| `economic/` | **Lauren** | economic impact indicators (taken over from Arash) |
| `social/` | **Florian** and **Lauren** | social impact indicators - **one indicator = one person** (`owner` column in `social/catalog.csv`) |
| `environmental/` | **Jean** | environmental impact indicators |
| `universe/`, `common/`, `tests/`, `run.py`, `profiles/`, `dashboard/`, `portfolio/`, `AGENTS.md`, `docs/*.md` | **Arash** | shared infrastructure, scoring pipeline, dashboard |

Need a change outside your area (a new column in the format, a scoring change, a
bug in `common/`)? **Do not make it.** Tell your person to message the owner.

If you do not know who you are helping: run `git config user.name` and ask the
person to confirm before you edit anything.

## 3. The working loop - every session, no exceptions

```bash
python run.py start                              # 1. FIRST THING: pull team's work, show status
# work in your area only
python run.py save "[social] ceo pay ratio: SEC download cached"   # 2. OFTEN
```

- **Start every session with `python run.py start`.** Your view of the repo is
  stale until you do. Do not plan or edit before it ran.
- **Save often** - every time something works, at least every 30-45 minutes, and
  always before you stop. Small commits are cheap; a lost afternoon is not.
- `save` does everything in the right order: commit -> pull (rebase) -> format
  check -> push. **Never** replace it with raw `git commit` / `git push`.
- Message format: `[area] what changed, past tense, concrete`. Good:
  `[environmental] ghg intensity: 412/503 companies, 2023`. Bad: `update`, `wip`, `fix`.
- Always `save` before you stop.

### When `save` or `start` says STOP

| Message | What you do |
|---|---|
| `your changes clash with a teammate's changes` in a file **your person owns** | Resolve it: `git pull --rebase origin main`, open each conflicted file, keep **both** people's intent (never just delete the other side), `git add <file>`, `git rebase --continue`, `python run.py check`, then `python run.py save "..."`. Explain to your person what you merged. |
| same, in a file **someone else owns** | **Stop.** `git rebase --abort` if a rebase is open. Tell your person the file and owner; they message that owner. |
| `NOT PUSHED: fix the errors above` | The errors are in your area. Fix the data/script, run `save` again. |
| `(not yours, not blocking)` | Someone else's file is broken. Do not fix it. Mention it to your person. |
| `.env contains secrets` / `larger than 20 MB` | Follow the message. Never work around it. |
| `you are on branch ...` | Stop and ask Arash. |

### Never, ever

- `git push --force`, `git reset --hard`, `git clean`, `git checkout -- .`, `git rebase -i`,
  deleting branches, rewriting history, or `git stash drop`.
  These destroy teammates' work and cannot be undone.
- Commit `.env`, API keys, passwords.
- Edit, reorder or "tidy up" anyone else's files.
- Create branches. This team works on `main` with small commits - the area ownership
  is what prevents conflicts.

## 4. Data rules

The full format is `docs/DATA_FORMAT.md`. The essentials:

1. **Every indicator is one CSV** at `<category>/indicators/<indicator_id>.csv` with
   exactly these columns: `ticker, year, value, source, source_url, retrieved, note`.
   One row = one company, one year, one number.
2. **Every indicator has one row in `<category>/catalog.csv`** (name, unit,
   `higher_is_better`, weight, owner, source, status) and **one script** in
   `<category>/scripts/<indicator_id>.py` that produces the CSV from scratch.
   Start a new one with `python run.py new-indicator <category> <indicator_id>`.
3. **Write indicators only through `common.io.write_indicator`** - it validates the
   format and refuses bad data.
4. **Download through `common.io.cached_download` / `cached_json`** - it stores the raw
   file in `<category>/raw/` and logs URL + time in `raw/_downloads.csv`. Never
   download the same thing twice.
5. **No source, no row.** Every value has a `source_url` a human can open.
6. **Never invent, estimate, or fill in numbers.** A missing company is a missing row.
   If you extract values from documents with a model, put the exact quote/page in
   `note` and spot-check at least 10 by hand before `ready`.
7. **Never write a number in a log, commit or doc that you did not see printed** by
   code you ran.
8. **Scores are computed by `common/score.py` only** - deterministic code, no model
   calls. Do not score, rank or weight companies anywhere else (the dashboard only
   displays them).
   `common/demo.py` makes **random** demo data for trying the dashboard - never copy it
   into an indicator file and never present it as a result.
9. No new Python dependencies without asking Arash (`requirements.txt` stays small).

### What makes an indicator "strong" (required before status `ready`)

- **Coverage**: data for >= 70% of S&P 500 companies (the check warns below that).
- **Reproducible**: `python run.py build <category> <id>` recreates the file from a public source.
- **Recent**: latest year 2022 or newer.
- **Size-neutral**: normalised (per revenue, per employee, a ratio, a %) so big
  companies do not win by being big.
- **Clear direction**: `higher_is_better` is obvious and the `description` says why it
  measures *impact* in this category, in one sentence.
- **Not a duplicate** of another indicator (e.g. two versions of the same emissions number).

## 5. Commands

```bash
python run.py setup                              # once per laptop
python run.py start                              # pull + status
python run.py status                             # what is changed / unpushed
python run.py save "[area] message"              # commit + pull + check + push
python run.py new-indicator social ceo_pay_ratio # catalog row + script from template
python run.py build social [indicator_id]        # run scripts -> indicators/*.csv
python run.py check                              # format check + tests
python run.py score [profile]                    # scores/<profile>/scores.csv (0-100), default: balanced
python run.py dashboard                          # open the dashboard in the browser
```

The dashboard's **Workspace** tab runs exactly these commands (`dashboard/server.py`,
`job_args`) - suggest it to people who prefer buttons over the terminal.

Run everything from the repo root. On Windows use `python`, not `python3`.

## 6. Recording progress

There are no task files - everyone knows what they are working on. Progress lives in
two places:

- **`<category>/catalog.csv` `status`** (`idea` / `in_progress` / `ready`): where each
  indicator stands.
- **Commit messages**: what changed, with counts you saw printed. Record dead ends
  there too - "Source X only covers 120 companies, dropped" saves a teammate hours.

## 7. Style

- Python, pandas, plain functions. Short docstring at the top of each script: what it
  measures, source, how to run.
- English in code, file names and commit messages. Talk to your person in their language.
- If unsure whether something is needed for phase 1, it is not. Ship the simple version.
