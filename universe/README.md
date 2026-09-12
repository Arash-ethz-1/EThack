# universe/ - owner: Arash

| file | columns | what |
|---|---|---|
| `sp500.csv` | `ticker, name, sector, cik` | the company list. **Every indicator joins on `ticker` from here.** |
| `financials.csv` | `ticker, year, revenue_usd, employees` | shared denominators for size-neutral indicators. Not scored. |

Both are built by scripts in this folder so they can be recreated. Status: **not built yet** (see `docs/tasks/arash.md`).
