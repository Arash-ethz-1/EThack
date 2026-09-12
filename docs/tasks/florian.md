# Florian - social impact (workforce)

**Area:** `social/` - shared with Lauren. **One indicator = one person:** you only edit
indicators whose `owner` in `social/catalog.csv` is you.
**Goal phase 1:** together with Lauren, >= 3 `ready` social indicators. Suggested split:
Florian = **workforce** (how a company treats its employees), Lauren = **society**
(customers, communities, governance). Agree on the split with Lauren before building.

## Getting started (no git knowledge needed)

1. Open the `EThack` folder in Claude Code.
2. Type `/start`. The agent pulls the latest work and tells you where things stand.
3. Tell it what you want in normal words, e.g. *"Let's build the CEO pay ratio indicator."*
4. Type `/save` whenever something works, and before you stop.

---

## Plan - for the team

### The idea in one paragraph

Today's scoring gives each company **one number from its most recent year**. A company
that was sued 40 times for discrimination in 2017 and cleaned up since looks identical to
one that got worse. I want social indicators that are **a time series**: one value per
company per quarter, back 10 years. That makes the score explainable over time ("this firm
improved, this one deteriorated") and it is what the portfolio simulator in `sp500/` needs,
because it rebalances every 3 months.

Important for everyone: **this does not force anyone to redo work.** See "Needs from
others" below - the proposed format change is additive and annual indicators stay valid
exactly as they are.

### What I am building

| # | Indicator | What it measures | Source | Direction |
|---|---|---|---|---|
| 1 | `labor_litigation_intensity` | employment-discrimination and labor lawsuits filed against the company, per 10k employees | CourtListener (federal court dockets, free API) | lower is better |
| 2 | `political_alignment` | corporate PAC + employee political money, per $ revenue | FEC OpenFEC API (free key) | lower is better |

Both come from **primary government/public sources with a date on every record**, so
bucketing them into quarters is real, not interpolated.

### Why lawsuits are a social indicator

Federal civil cases carry a **Nature-of-Suit code**. Codes 442 (Civil Rights: Jobs), 710
(Fair Labor Standards), 720 (Labor/Management Relations), 740, 751 (Family & Medical
Leave) and 790/791 (other Labor, ERISA) are exactly "an employee sued this company over
how it treated them". Counting those per quarter, normalised per 10k employees, is a
direct, auditable workforce-treatment signal that nobody has to self-report.

### Order of work (deliberate - lowest risk first)

| # | Step | Why this order |
|---|---|---|
| 0 | Build `social/raw/aliases.csv` - legal + former company names per CIK | without it the data is silently wrong, see "What already went wrong" |
| 1 | Download dockets once into `social/raw/` | one download, cached, never repeated |
| 2 | Emit the **annual** `labor_litigation_intensity.csv` | fits today's format, scores immediately, needs nothing from anyone |
| 3 | Write the format proposal for Arash | the architectural piece, independent of whether the data lands |
| 4 | Emit the **quarterly** panel from the same cached download | free - only needs the format decision |
| 5 | `political_alignment` from FEC | second indicator |
| 6 | Bonus if time survives | see below |

Step 2 is the guaranteed deliverable. Steps 4+ are upside on top of it, computed from data
already on disk, so nothing is wasted if we run out of time.

### What I checked before committing to this (measured, not guessed)

| Source | Result |
|---|---|
| CourtListener | works, free, no key. `suitNature` + `dateFiled` on every docket. Filtering by Nature-of-Suit cut one firm's 10-year result from 5,512 dockets to 15 - so the whole S&P 500 is ~25 min of downloading, not hours. Page size is capped at 20. |
| SEC XBRL | quarterly revenue covers **463/500 companies (93%)** for one test quarter, using a union of 5 tags. This is the denominator for normalising. |
| FEC | works with a free `api.data.gov` key. Name matching is noisy - a search for "Apple" returns *Applegate for Congress*, because Apple runs no PAC at all. |
| US lobbying (Senate LDA) | **blocked** - 403 from their firewall on every path, and the House Clerk bulk files 500/403. Conceptually the best indicator (quarterly by law); currently unreachable. |
| GDELT (news tone) | rate-limited to 1 request / 5 seconds -> 28h for our grid. Only viable via their BigQuery dataset. Parked. |
| EDGAR full-text search | works with GET (POST gives 403). Enables an NLP indicator later. |
| JUST Capital | `robots.txt` permissive, rankings page loads. **Annual and a composite of other scores**, so using it as an input would be circular - better as an external check that our score is sane. |

### What already went wrong (so nobody repeats it)

- **Company names in `constituents.csv` are display names, not legal names.** A court
  search for "Meta Platforms" in 2019 finds almost nothing, because the company was called
  *Facebook, Inc.* until October 2021. Same problem for "News Corp (Class A)", "Bunge
  Global", "Healthpeak Properties". Fix: SEC's submissions API returns `formerNames` **with
  valid-from/to dates** per CIK, so the mapping can be built automatically. That is step 0.
- **Nature-of-Suit codes must be matched exactly.** My first filter accidentally matched
  `422 Bankruptcy Appeal` and `423 Bankruptcy withdrawal` as labor cases.

### Two honest weaknesses (please attack these)

1. **Litigation measures disputes that reached federal court, not workplace harm.** A
   company with aggressive mandatory-arbitration clauses keeps cases out of court and
   therefore scores *better* while possibly treating people worse. This will go in the
   catalog `description` - it is a real limitation, not a detail to hide.
2. **Filings fell ~40% over the decade** (all federal Civil Rights: Jobs dockets: 12,055 in
   2016 -> 7,088 in 2024), because of that same shift to arbitration. This does **not**
   break the score, because `common/score.py` ranks companies *against each other*: a trend
   shared by everyone cancels out. It only breaks if ranks are ever pooled across time
   instead of computed per period. Worth writing into the scoring docs.

### Coverage risk - the thing most likely to go wrong

On a 33-company sample across all 11 sectors, 76% had at least one federal docket in 2019
(12 of the sample hit rate limits before finishing). Whether the labor-specific subset
clears the **70% bar in `AGENTS.md` section 4** is not yet known - step 2 prints the real
number. If it lands below, the indicator ships as `in_progress`, not `ready`, and we say so.

### Bonus, only if time survives

- **Human-capital disclosure quality** (NLP): since 2020 the SEC requires a "Human Capital
  Resources" section in every 10-K. Score whether a company discloses *actual numbers*
  (turnover rate, training hours, injury rate) or writes boilerplate. Great demo, but it
  only exists from 2020 and is annual, so it cannot be a headline indicator.
- **JUST Capital correlation** as an external sanity check on our score.
- **Political proximity to the current administration** - money from a company's PAC and
  employees to administration-affiliated committees. Interesting and newsworthy, but too
  sparse per company to score fairly, so: a presentation slide on the most-connected firms,
  not an indicator.

## Needs from others

### Arash - proposed format change (additive, nothing breaks)

To store a time series I need one extra column. The proposal is deliberately the smallest
possible change:

1. **`<category>/indicators/*.csv` gets an optional `quarter` column** (e.g. `2019Q3`).
   **Empty = annual**, which is exactly today's behaviour. Every existing indicator file
   stays valid without being touched. Jean and Lauren do not have to change anything.
2. **`common/validate.py`**: if `quarter` is present it must match `^\d{4}Q[1-4]$` and agree
   with `year`. Uniqueness becomes `ticker` + `year` + `quarter`.
3. **`common/score.py` gets `--as-of YYYYQn`**: for each company take the most recent row
   *published* by the end of that quarter, then rank as today. **Without the flag, scoring
   behaves exactly as it does now.**
4. **Ranks must stay cross-sectional per period** (companies vs. companies within one
   quarter), never pooled across time - see weakness 2 above.

Why it is worth it for the other categories too:
- **Economic (Arash):** SEC XBRL gives 10-Q values with `start`, `end` **and `filed`** dates.
  Your pillar is natively quarterly and gets point-in-time correctness for free.
- **Environmental (Jean):** gains least - emissions are annual and lag. An empty `quarter`
  column means Jean keeps working exactly as now.
- **Portfolio (phase 3):** `sp500/sp500_sim.py` already rebalances every 3 months. A
  quarterly score is what turns the allocation into a real 10-year backtest instead of
  today's numbers applied retroactively to the past.

I have **not** edited anything in `common/`, per `AGENTS.md` section 2. Decision is Arash's.

### Lauren - split

I am taking litigation + political money (workforce/political). Suggest you keep
consumer-side: CFPB complaints are excellent and dated, but **financial sector only**
(~70 companies), so they need pairing with something broader.

## Log

<!-- append below, never edit old entries. Format: AGENTS.md section 6 -->

### 2026-09-12 19:52 - plan: quarterly social indicators
- Done: researched and **measured** sources before building. CourtListener works free
  without a key, exposes `suitNature` + `dateFiled`; a Nature-of-Suit filter cut one
  firm's 10-year result from 5512 dockets to 15, so the full universe is ~25 min of
  downloading. SEC XBRL quarterly revenue covers 463/500 companies (93%) via a 5-tag union.
  FEC works with a free api.data.gov key (stored in .env, not committed).
- Done: wrote the plan + the additive `quarter` column proposal for Arash, above.
- Next: step 0, build `social/raw/aliases.csv` from SEC `formerNames`, then download
  dockets and emit the annual indicator first.
- Problems: Senate LDA lobbying data is firewalled (403 on every path) and the House Clerk
  bulk files return 500/403 - lobbying would have been the best indicator, currently
  unreachable. GDELT is rate-limited to 1 request/5s, so news-tone needs BigQuery. Company
  names in constituents.csv are display names: a 2019 court search for "Meta Platforms"
  fails because it was "Facebook, Inc." until 2021. All federal Civil Rights: Jobs dockets
  fell from 12055 (2016) to 7088 (2024) - a real arbitration-driven trend, harmless because
  scoring ranks companies against each other within a period.
- Needs from others: Arash - decision on the optional `quarter` column (see above).
  Lauren - confirm the workforce/society split.
