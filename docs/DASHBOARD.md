# Dashboard - build plan

Owner: Arash. **Status: agreed with Arash, not built yet.** Whoever builds it: read this whole
file first, then `AGENTS.md`. Ask Arash before deviating from anything marked **must**.

Goal: one calm page that answers three questions for a judge or fund manager:
1. Who scores best? 2. Why does this company score that way? 3. Can I trust the data?

---

## 0. Reference prototype

- Clickable prototype (layout reference, **not** the final style):
  https://claude.ai/code/artifact/d9cd62cc-54d2-4af5-b560-4f7fb1175226
- Its source is in `dashboard/prototype/` (`index.html` + `export_data.py`). To open it locally:
  ```bash
  python dashboard/prototype/export_data.py dashboard/prototype/data.js
  # then open dashboard/prototype/index.html in a browser
  ```
- The prototype shows the **structure** Arash liked (ranking, company chain, evidence split into
  exhibits). The **visual style** must be the Swiss style from section 2, not the Caslon/yellow
  look of the prototype.

## 1. Rules (must)

- The dashboard **only displays**. Scores come from `common/score.py`; check results come
  from `checks/results/*.json`. No scoring, ranking or model call in the browser or on page load.
- Real data only. Remove the demo toggle (demo data stays available on the command line).
- Every number on screen that comes from an indicator links back to its source document.
- Never show a number that the code did not produce. Checks that have not run show
  "not run", never a placeholder number.
- No new frontend libraries. Charts are hand-written SVG (the prototype shows how).
  New Python dependency allowed: `anthropic` (for agent checks only, section 5).
- Minimalist: no sidebar, no workspace tab, nothing that is not needed for the demo.

## 2. Visual style: Swiss (must)

Classic Swiss typography: strict grid, lots of white space, black/white plus one red,
strong horizontal rules, big confident numbers. Serious, no gimmicks, no gradients, no
rounded cards, no shadows except the company drawer.

Tokens (light is the default; dark mode redefines the same tokens):

| token | light | dark | use |
|---|---|---|---|
| `--bg` | `#ffffff` | `#0c0c0c` | page ground |
| `--surface` | `#f1f1f1` | `#171717` | hover rows, selected items |
| `--ink` | `#0a0a0a` | `#f2f2f2` | text, bars, strong rules |
| `--muted` | `#595959` | `#a3a3a3` | secondary text, axis labels |
| `--rule` | `#d6d6d6` | `#2a2a2a` | thin dividers |
| `--rule-strong` | `#0a0a0a` | `#f2f2f2` | section top rules (1px) |
| `--accent` | `#d52b1e` | `#ff4d40` | the one red: active tab, key number in a verdict, environmental |
| `--econ` | `#0a0a0a` | `#f2f2f2` | economic category |
| `--soc` | `#7a7a7a` | `#8f8f8f` | social category |
| `--env` | `#d52b1e` | `#ff4d40` | environmental category |
| `--pass` / `--pending` / `--flag` | `#1f7a3f` / `#8a8a8a` / `#b36b00` | `#5cc08d` / `#7c7c7c` / `#e0a64a` | check status only |

- Font: **Archivo** (Google Fonts, weights 400/500/700/800) for everything, fallback
  `"Helvetica Neue", Arial, sans-serif`. Numbers use `font-variant-numeric: tabular-nums`.
- Type scale: 11 (uppercase labels, letter-spacing .08em) / 14 (body) / 20 / 26 (page title,
  800) / 40 (verdicts and big scores, 800, letter-spacing -.025em).
- Radius 0 everywhere. Status = small dot + text, never a coloured card.
- Layout: max width 1200px, 12-column grid, 32px side gutter (16px on phones). Must work at
  400px width.
- Respect light and dark theme (`prefers-color-scheme`), keyboard focus visible.

## 3. Views

Top bar: title `S&P 500 Impact` + one-line motto `Every number has a source.`, two tabs
**Ranking** and **Evidence**, profile dropdown (`profiles/*.toml`).

### 3.1 Ranking (home)

- Line under the title: `N companies · M indicators · data retrieved <date>` (from the data).
- Controls: search (company or ticker), sector filter, button **Adjust weights**.
- **Adjust weights** opens a thin row with the 3 categories, each `Off / 1x / 2x`. Changing it
  calls the server, which rescored with `common/score.py`. Not saved.
- Table, one row per company: rank, company + ticker, sector, **indicator fingerprint**,
  economic, social, environmental, total (big number, right-aligned).
- **Fingerprint** = one small vertical bar per indicator, grouped by category, height = points
  0-100, hatched = no data. Shows at a glance where a company is strong and where data is missing.
- A missing score shows `-`, never `0`. First 50 rows, then "Show all".

### 3.2 Company detail (drawer from the right, click a row)

1. Header: name, ticker, sector. Score line: total (biggest) + 3 category scores.
2. **Chain of evidence**: a flow diagram in 4 columns
   `source document -> indicator (points) -> category (score) -> total`,
   line width = points. Hover highlights one chain.
3. **Ledger**: one row per indicator: name, category, fiscal year, raw value + unit, points,
   link to the **human-readable** source (see section 6), the `note` (quote / calculation),
   and check status badges for this value (e.g. `outlier - explained`, `agent: confirmed`).

### 3.3 Evidence

Split into **exhibits** (term from SEC filings). Left: a list of all exhibits with their status
(`passed` / `flagged` / `not run`). Right: **one exhibit at a time**:

- small label `Exhibit A` + kind (`Code check` / `Agent check`) + status
- **verdict**: one sentence in big type, the key number in red
  (e.g. "13,964 of 13,964 values carry a link to their public source.")
- **one** chart (or one table)
- "How this is checked" collapsed at the bottom

| Exhibit | Claim | Check(s) | Chart |
|---|---|---|---|
| A | Every value points to a document | `traceability` | horizontal bars: companies with a sourced value per indicator (x/503) |
| B | The numbers are in the filings | `agent_quote_verify` | stacked bar per indicator (confirmed / mismatch / not found) + 3 example cards: our value next to the highlighted quote from the filing |
| C | Recomputed independently, same result | `cross_source_tax`, `agent_blind_reextract` | two scatter plots with a diagonal, verdict = share within 1% |
| D | Outliers are real, not errors | `plausibility`, `agent_outlier_explain` | histogram with outlier fences + list of outliers with the agent's classification and quote |
| E | Company traits persist over time | `stability` | line chart of year-to-year rank correlation per indicator (the 2017 US tax reform shows as a dip in the tax gap line - label it) |
| F | No two indicators measure the same thing | `redundancy`, `sector_pattern` | correlation matrix (lower triangle) + sector strip plot of resource risk |

## 4. Checks framework

One file per check in `checks/<check_id>.py` (new top-level folder, owner Arash):

```python
TITLE = "Every value points to a document"
KIND = "code"          # or "agent"
EXHIBIT = "A"

def run() -> dict:
    return {
        "status": "passed",        # passed | flagged | failed
        "verdict": "13964 of 13964 values carry a source link",
        "numbers": {...},          # what the chart needs
        "rows": [...],             # flagged rows: ticker, year, indicator_id, value, detail, url
    }
```

- `python run.py verify [check_id]` runs checks and writes `checks/results/<check_id>.json`
  (plus `ran_at`, and for agent checks `model`). Add the command to `run.py` and `AGENTS.md`.
- The server exposes `GET /api/checks` (all result files). An exhibit whose result file is
  missing shows `not run`.
- Adding a check = adding one file. No dashboard change needed unless it needs a new chart.
- Tests in `tests/` for every code check (small fixture data).

### Code checks

| id | what |
|---|---|
| `traceability` | rows with source_url + retrieved + note, per indicator; flag rows whose source_url is a generic API/search endpoint instead of one company's document |
| `plausibility` | impossible values, future years, year-over-year jumps > 5x, values beyond 3x IQR |
| `stability` | Spearman rank correlation year t vs t-1 per indicator, companies in both years, min 100 |
| `redundancy` | Spearman correlation of latest values between indicator pairs, min 50 overlap; flag abs >= 0.8 |
| `sector_pattern` | distribution per GICS sector for indicators with an expected pattern |
| `cross_source_tax` | our effective rate (tax / pretax) vs XBRL `EffectiveIncomeTaxRateContinuingOperations` (download via `common.io.cached_json`) |

Note: pandas `corr(method="spearman")` needs scipy, which is not installed. Use
`a.rank().corr(b.rank())`.

### Agent checks (Claude API)

A model **verifies, never scores**. It never changes a value or a score.

- API key from `.env` as `ANTHROPIC_API_KEY` (never commit it). Model `claude-sonnet-5`.
- Documents are downloaded with `common.io.cached_download` (SEC needs `SEC_CONTACT_EMAIL`).
  Send only the relevant excerpt (search the document for the number/keyword, pass a window
  of text around it) to keep cost low.
- Ask for structured JSON output: `{"verdict": "confirmed|mismatch|not_found", "quote": "...", "found_value": ...}`.
- Fixed random seed for the sample so reruns check the same rows. Results cached in
  `checks/results/`; the demo reads the files and costs nothing.
- Spot-check 10 agent verdicts by hand before showing the exhibit.

| id | what |
|---|---|
| `agent_quote_verify` | 30 random values per document-based indicator: does the document state this value? |
| `agent_blind_reextract` | an agent extracts headcount (and later other values) from the 10-K **without seeing ours**; compare |
| `agent_outlier_explain` | for each `plausibility` outlier: read the tax footnote, classify real (one-off charge, near-zero pretax income) vs data error, with quote |
| `agent_match_audit` | for name-matched data (court dockets, 10-K material mentions): is this really this company / this meaning? Sample of 30 |

## 5. Server and files

- Keep `dashboard/server.py` (stdlib HTTP) and `dashboard/static/`. Rewrite the static files;
  remove workspace/job/demo endpoints and the old tabs.
- Endpoints: `GET /api/meta`, `POST /api/score` (profile + category weights -> table incl.
  per-indicator points for the fingerprint), `POST /api/explain` (ticker -> ledger + chain),
  `GET /api/checks`.
- `python run.py dashboard` stays the way to open it. Update `AGENTS.md` section 5 (no
  Workspace tab any more) and delete `dashboard/prototype/` when the real one works.

## 6. Known data issues to handle

- `economic/*`: `source_url` is the raw companyfacts JSON. The `note` contains `accn=...`;
  link the filing instead: `https://www.sec.gov/Archives/edgar/data/<cik>/<accn without dashes>/<accn>-index.htm`
  (the prototype's `export_data.py` does this).
- `social/labor_litigation_intensity`: `source_url` is the generic CourtListener search
  endpoint for every row - not openable per company. `traceability` should flag it; tell Florian.
- `resource_supply_risk` is industry-level: every year identical, many ties. Exclude it from
  the stability chart and say why in the caption.
- `run.py check` coverage warning only looks at the single latest year in a file (e.g. one
  company in a future fiscal year). Reported by Lauren, not fixed yet.

## 7. Build order

1. Swiss style + Ranking + Company drawer on real data, old UI removed.
2. `checks/` framework + `run.py verify` + code checks `traceability`, `plausibility`,
   `stability`, `redundancy` -> Exhibits A, D (without agent), E, F.
3. `cross_source_tax` + `agent_quote_verify` -> Exhibits B, C. Strongest proof for the pitch.
4. `agent_outlier_explain`, `agent_blind_reextract`, `agent_match_audit` if time allows.

**Done when:** `python run.py dashboard` shows all three parts on real data, every exhibit
shows either a real result or `not run`, `python run.py check` passes, and it looks right at
400px width and in dark mode.
