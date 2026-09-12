# Data format

Everyone delivers data in **the same format**, so one scoring script works for all
three categories. `python run.py check` enforces everything on this page.

## Folder layout per category

```
social/
  catalog.csv              one row per indicator (metadata)
  scripts/<id>.py          downloads + computes one indicator
  raw/                     cached downloads, never edited by hand
  raw/_downloads.csv       automatic log: file, url, time, bytes
  indicators/<id>.csv      the result, in the format below
```

## `universe/sp500.csv` - the company list

| column | example | |
|---|---|---|
| `ticker` | `BRK.B` | the join key for everything. Uppercase, dot not dash. |
| `name` | `Berkshire Hathaway` | |
| `sector` | `Financials` | GICS sector |
| `cik` | `0001067983` | SEC id, 10 digits with leading zeros |

Every indicator uses **these tickers exactly**. If your source uses names or other
ids, map them to this ticker inside your script.

## `<category>/indicators/<indicator_id>.csv`

One row = one company, one year, one number.

| column | type | example | rule |
|---|---|---|---|
| `ticker` | text | `AAPL` | from `universe/sp500.csv` |
| `year` | integer | `2024` | the year the value **describes** (fiscal/reporting year), not when you downloaded it |
| `value` | number | `0.0423` | plain number in the unit from the catalog. No `%` sign, no thousands separator, no text. Missing data = no row. |
| `source` | text | `SEC XBRL companyfacts` | short name |
| `source_url` | text | `https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json` | the exact page/API a human can open |
| `retrieved` | date | `2026-09-12` | `YYYY-MM-DD`, UTC |
| `note` | text | `FY ends Sep; quote p.34: "..."` | optional |

No other columns. One row per `ticker` + `year`. Several years are welcome - scoring
uses each company's most recent one.

## `<category>/catalog.csv`

| column | example | rule |
|---|---|---|
| `indicator_id` | `ceo_pay_ratio` | lowercase_snake_case, = file name, unique across all categories |
| `name` | `CEO-to-median-worker pay ratio` | human readable |
| `description` | `Lower ratio = fairer pay distribution inside the company` | one sentence: what + why it is impact |
| `unit` | `ratio` | `%`, `tCO2e per $M revenue`, `USD per employee`, ... |
| `higher_is_better` | `false` | `true` or `false` |
| `weight` | `1` | number > 0, relative weight inside the category. Keep `1` unless the team decided otherwise. |
| `owner` | `Lauren` | one person |
| `source` | `SEC DEF 14A` | short name |
| `status` | `ready` | `idea` -> `in_progress` -> `ready`. **Only `ready` goes into the score.** |

Catalogs merge automatically when two people add rows at the same time
(`.gitattributes`). If the check reports a duplicate `indicator_id`, delete one line.
