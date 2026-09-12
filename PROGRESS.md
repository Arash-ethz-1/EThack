# PROGRESS.md - the running log of what actually shipped

One file, five sections, append-only. This is how we know at 04:00 who has what,
what is already done, and what is still nobody's.

**Read the section of whoever you are about to depend on before you ask them
anything.** Half the questions at a hackathon are answered by a log nobody read.

---

## How to write an entry

1. `git pull --rebase origin main` **first**, always. Otherwise you are logging
   against a stale picture of the repo.
2. Append to the **end of your own section**. Never edit or reorder someone else's
   entry - that is what causes the only merge conflict this file can produce.
3. Log at every commit-sized step (every 30-45 min) and always before you stop.
4. Timestamps in **UTC, 24h**. `date -u +"%Y-%m-%d %H:%M"`.

```markdown
### 2026-09-12 18:40 UTC - arash/link-ex21
- **Shipped:** EX-21 scraper, 487/503 tickers resolved, cached to `data/raw/ex21/`
- **Next:** reranker on `data/manual/link_labels.csv`, target 30 min
- **Blocked:** none
- **Needs from others:** Jean - GHGRP 2010-2023 parent_company column, to test the join
```

Four lines. `Shipped` is past tense and verifiable - a file, a row count, a passing
test. "Worked on the linker" is not an entry. If a number is in the entry, it must
be a number you saw printed.

Use **`Blocked: none`** explicitly. An empty field reads as "forgot to write it".

### The two honest entries

Write these when they happen. They are worth more than optimistic ones:

```markdown
- **Shipped:** nothing. Fuzzy matcher tops out at 61% - dropping it for the EX-21 graph.
- **Shipped:** reverted f4cb2cd, it broke `python run.py all` on mocks. main is green again.
```

---

## Arash - contracts, link layer, app shell

### 2026-09-12 16:09 UTC - main
- **Shipped:** repo scaffold - `contracts.py`, indicator registry, task plans, `python run.py mocks`
- **Next:** EX-21 subsidiary scraper
- **Blocked:** none
- **Needs from others:** everyone - read `CLAUDE.md` and `CONVENTIONS.md` before your first commit

---

## Jean - data acquisition and the archive

_no entries yet_

---

## Lauren - indicators and scoring

_no entries yet_

---

## Florian - portfolio construction

_no entries yet_

---

## Harprit - evaluation and METRICS.md

_no entries yet_

---

## Agents

Any AI agent that commits logs here too, under the person who ran it, in that
person's section - not in this one. This section is for agent runs that produced
**no** commit: a research sweep, a failed extraction, an adversarial review. We
want to be able to answer "what did the AI actually do here?" in the pitch with
specifics.

_no entries yet_
