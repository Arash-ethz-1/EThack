# CLAUDE.md - context for every AI agent working in this repo

You are working on **Sightline**, a 20-hour hackathon project for an ETH-affiliated
fund. Read this whole file before your first edit. Then read
`docs/tasks/<the-person-you-are-helping>.md` and `CONVENTIONS.md`.

**Before your first tool call, run `git pull --rebase origin main` and read
`PROGRESS.md`.** Five people are committing to this repo in parallel. Your view of
it is stale the moment you start, and the most expensive thing you can do is build
something a teammate finished twenty minutes ago. Section 7 is the full loop - it is
not optional and it is not advice.

---

## 1. What we are building and why it is not the obvious thing

The challenge: "build a data-driven framework to quantify and compare the
sustainability of companies in the S&P 500."

Almost every other team will download a vendor ESG score, pick 15 indicators,
min-max normalise, apply arbitrary weights, and ship a leaderboard. That approach
measures **disclosure quality**, not sustainability, and different ESG vendors
famously disagree with each other (correlations around 0.5, versus ~0.99 for
credit ratings). Adding a sixteenth disagreeing opinion is worthless.

**Our thesis, in one sentence:** US climate and environmental data is actively
disappearing, so we score companies on regulator-metered physical reality, rate
every indicator by how likely it is to still exist next year, and give the fund a
tool that keeps working as its inputs die.

Three pillars:

| Pillar | What it measures | Why it is defensible |
|---|---|---|
| **Measured intensity** | EPA-metered Scope 1 CO2e per dollar of revenue, sector-relative | A regulator physically metered it. Not a claim. |
| **Say-Do gap** | Company-reported Scope 1 vs. metered Scope 1 | It is a credibility discount and a disclosure liability. No vendor publishes it. |
| **Carbon earnings at risk** | metered tonnes x carbon price / EBITDA | Converts sustainability into a number a PM acts on. |

Plus a **Visibility** axis running orthogonal to all of it: how much of this
company can we actually see, from sources that will still exist?

## 2. The architectural rule - do not violate this

```
LLMs and agents live at the EDGES, turning unstructured documents into structured rows.
DETERMINISTIC CODE owns the CORE - every score, weight, percentile, portfolio weight.
```

If a judge asks "why 0.40?" the answer must be a line of code, not a model's
preference. Agents fetch and extract. **Agents never score.** Anything that
produces a number in `score.py`, `portfolio/` or `eval/` must be reproducible by
re-running the code, with no model call in the path.

Corollary: every agent-extracted value carries `verbatim_quote`, `source_url` and
`page`. **No citation, no row.** An uncited number is a hallucination with good posture.

## 3. Contracts are frozen

`src/ethack/contracts.py` defines the dataframe schema between every layer. It is
the one file nobody edits alone.

- Need a new column? Post in the team channel, get the downstream owner's OK, then
  change `contracts.py` **and** `scripts/make_mocks.py` in the same commit.
- Every layer reads its input contract and writes its output contract. Nothing else.
- `python run.py mocks` generates schema-valid fake data so any layer can be built and
  tested before its upstream layer exists. **Use it.** Do not wait for real data.

## 4. The indicator registry - our flexibility requirement

Indicators are plugins, not a hardcoded list. Adding one means adding one file in
`src/ethack/indicators/impl/` that declares an `IndicatorSpec` and a `compute()`.
The dashboard reads the registry at runtime and generates its own controls, so a
new indicator appears in the UI with zero UI work.

Every spec must declare `durability`, which is what powers the blackout simulator:

| Durability | Meaning | Examples |
|---|---|---|
| `PERMANENT` | No government can rescind it | ESA/Sentinel satellite observations, market prices |
| `STATUTORY` | Core securities law, very hard to remove | 10-K financials, EX-21 subsidiary lists |
| `AT_RISK` | Mandatory environmental disclosure under active rollback | EPA GHGRP, EPA ECHO |
| `VOLUNTARY` | Company controls whether it exists at all | sustainability reports, CDP |
| `DERIVED` | Computed from the above | ratios, gaps |

This taxonomy is the project's spine. An indicator without an honest durability
rating is not finished.

## 5. Verified data sources

All tested live and working. No API keys required for any of these.

| Source | Endpoint | Gives us |
|---|---|---|
| EPA GHGRP | `data.epa.gov/efservice/pub_dim_facility/year/2023/JSON` | 11,281 facilities, `parent_company`, NAICS, lat/lon |
| EPA GHGRP | `data.epa.gov/efservice/pub_facts_sector_ghg_emission/year/2023/JSON` | CO2e per facility per gas |
| SEC tickers | `sec.gov/files/company_tickers.json` | ticker <-> CIK <-> name |
| SEC XBRL | `data.sec.gov/api/xbrl/frames/us-gaap/Revenues/USD/CY2024.json` | revenue, EBITDA inputs |
| SEC EX-21 | `sec.gov/Archives/edgar/data/{cik}/{accession}/index.json` -> `*exx21.htm` | **legally required subsidiary list** |
| EPA ECHO | `echodata.epa.gov/echo/cwa_rest_services.get_facilities` | violations, penalties |
| Climate TRACE | `api.climatetrace.org/v6/assets` | satellite-inferred emissions |

**SEC requires a User-Agent header** with a contact email or it returns 403.

### Why EX-21 matters more than it looks

EPA gives you `"CINERGY CORP (100%)"`. You need `DUK`. String distance from
"Cinergy Corp" to "Duke Energy" is enormous - fuzzy matching cannot solve this,
which is why most teams' facility joins will silently lose most of their tonnage
and they will never notice. Duke's EX-21 lists 186 subsidiaries including Cinergy
Corp, Caldwell Power Company and Catamount Energy Corporation. Scrape EX-21 for all
500 constituents and you have a ground-truth ownership graph. That is `src/ethack/link.py`.

## 6. Commands

```bash
python run.py mocks     # generate schema-valid fake data into data/mock/
python run.py fetch     # L1: pull and cache all real sources  (Jean)
python run.py link      # L2: facility -> ticker resolution     (Arash)
python run.py score     # L3+L4: indicators and scores          (Lauren)
python run.py portfolio # L5: the $1B book                      (Florian)
python run.py eval      # L6: validation and METRICS.md         (Harprit)
python run.py app       # launch the dashboard
python run.py test      # pytest
python run.py all       # the whole pipeline, end to end

python run.py sync                    # pull main before you branch
python run.py ship you/thing   # rebase, test, ff-only merge into main, push
python run.py progress                # print a PROGRESS.md entry stub
```

`python run.py all` must work from a clean clone on mock data at all times. If your change
breaks it, you fix it before you sleep.

## 7. The working loop - git, branches and PROGRESS.md

**Never commit on `main`.** Every change lives on a short-lived branch that gets
rebased onto `main` and fast-forwarded in. `CONVENTIONS.md` section 2 has the full
command list; this is the part you must not skip.

```bash
git switch main && git pull --rebase origin main   # 1. BEFORE you plan anything
git switch -c <person>/<thing>                     # 2. one task, one branch
# ... work, python run.py test, commit every 30-45 min ...
git pull --rebase origin main && python run.py test         # 3. BEFORE you merge
git switch main && git pull --rebase origin main
git merge --ff-only <person>/<thing> && git push origin main
```

`python run.py sync` is step 1. `python run.py ship <person>/<thing>` is step 3 onward.

**Pull twice, not once.** Once before you start, so you are not building against
contracts that changed an hour ago. Once before you merge, so `python run.py test` passes
against everyone else's work and not just your own. An agent that skips the second
pull is how `main` breaks at 03:00.

If a rebase conflicts in a file you do not own: **stop, do not resolve it.** Say
which file and which owner, and ask. Resolving someone else's file from a stale
branch silently reverts their work - exactly the failure the ownership table exists
to prevent.

### PROGRESS.md is part of the deliverable

`PROGRESS.md` is the log the whole team reads to know what exists. Every person has
their own section, and **you append to the end of the section of the person you are
working for, never to anyone else's.** That per-person split is the only reason five
people can append to one file all night without conflicting.

Log at every commit-sized step and always before you stop:

```markdown
### 2026-09-12 18:40 UTC - arash/link-ex21
- **Shipped:** EX-21 scraper, 487/503 tickers resolved, cached to `data/raw/ex21/`
- **Next:** reranker on `data/manual/link_labels.csv`
- **Blocked:** none
- **Needs from others:** Jean - GHGRP parent_company for 2010-2023, to test the join
```

`python run.py progress` prints that stub with the timestamp and branch filled in.

Rules that apply to you specifically as an agent:

1. **`Shipped` is past tense and verifiable** - a file that exists, a row count you
   saw printed, a test that passed. Never write a number you did not observe in
   output. "Implemented the linker" is not an entry; "487/503 resolved" is.
2. **Log the entry in the same branch as the work it describes.** A progress entry
   that lands without its code is a lie with a timestamp.
3. **Log failures and dead ends too.** "Fuzzy matcher tops out at 61%, dropping it"
   saves the next person three hours and is worth more than a success line.
4. **Say what you were.** If an agent did the work, the commit body says so, per
   section 9. A run that produced no commit - a research sweep, a failed extraction,
   an adversarial review - goes in the `## Agents` section at the bottom instead.
5. Never edit, reorder, summarise or "tidy" an existing entry, yours or anyone's.
   The log is append-only. Its value is that it is a record, not a status page.

## 8. Hard rules

1. **Never edit a file you do not own.** See the ownership table in `CONVENTIONS.md`.
   Need a change in someone else's file? Ask them. In 20 hours, a merge conflict at
   03:00 costs more than a message costs.
2. **Never commit on `main`, and pull twice - before you start and before you merge.**
   Log what you shipped in `PROGRESS.md` in the same branch. See section 7.
3. **Never commit real numbers you have not seen produced.** No placeholder figures
   that look like results. Mark every mock as mock.
4. **Cache every network call to disk.** Never hit an API twice for the same data.
   `data/raw/` is committed - it is our archive and part of the thesis.
5. **Record provenance.** Every fetch appends to `data/PROVENANCE.md`: source, URL,
   UTC timestamp, row count, durability rating. This file is a deliverable, not admin.
6. **No new dependencies** without asking. `requirements.txt` is small on purpose.
7. **Do not build a chatbot over sustainability reports.** Four other teams will.
   It demos as a search box and proves nothing.
8. **If you are unsure whether something is on the critical path, it is not.**
   Ship the boring version and move on.

## 9. When to reach for a model or an agent

Say so explicitly in your commit message when you do.

| Situation | Use | Do not use |
|---|---|---|
| Resolving `parent_company` to a ticker | Embeddings over the EX-21 registry + a small trained reranker on hand labels | An LLM asked "which company is this?" one row at a time |
| Getting reported Scope 1 out of PDFs | An extraction agent per company, strict schema, mandatory citations | Hand-typing 500 numbers |
| Predicting future abatement | Gradient boosting on the ~150k facility-year panel, time-split, vs. a persistence baseline | Anything trained on 500 company rows - a finance judge spots it instantly |
| Assigning weights or computing scores | Deterministic code | An LLM. Ever. |
| Sanity-checking our own rankings before the pitch | An adversarial agent told to argue we are wrong | - |

Report the error rate of every model you train. A model without a baseline
comparison is not a result.

## 10. Tone of the output

The client is an institutional fund, not a sustainability team. Write like a risk
memo: specific, quantified, honest about what is unknown. Every chart labels its
units. Every claim has a source. When coverage is partial, say the coverage number
out loud - partial coverage stated openly beats full coverage quietly fabricated,
and judges can tell the difference.
