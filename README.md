# EThack - sustainability impact of the S&P 500

Challenge: quantify and compare the sustainability of S&P 500 companies for an
ETH-affiliated fund, and use it to weight a portfolio.

```
economic/  social/  environmental/      >= 3 sub-indicators each, one shared data format
        \      |      /
               |
      profiles/<name>.toml              the user picks indicators + weights
               |
      python run.py score / dashboard   0-100 score per category + total, per company
               |
          portfolio/                    allocation weights (phase 3, placeholder)
```

| Category | Who |
|---|---|
| Economic | Lauren |
| Social | Florian, Lauren, Arash |
| Environmental | Jean |

## First time on your laptop

You need [Python 3.11+](https://www.python.org/downloads/), [git](https://git-scm.com/downloads)
and [Claude Code](https://claude.com/claude-code).

```bash
git clone https://github.com/Arash-ethz-1/EThack.git
cd EThack
python run.py setup
```

## Every time you work

**With Claude Code (recommended):** open the `EThack` folder, type `/start`, say what you
want to do. Type `/save` whenever something works and before you stop. The agent
follows `AGENTS.md` and handles git for you.

**With the dashboard:** `python run.py dashboard` opens it in the browser. The
**Workspace** tab does everything below with buttons: get latest, save & push, check,
build indicators, add an indicator, export scores.

**Without an agent:**

```bash
python run.py start                          # get everyone's latest work
# ... work in YOUR folder only ...
python run.py save "[social] what you did"   # commit + pull + check + push
```

If `save` prints **STOP**, do not try git commands - read the message, it tells you what to do.

## Where things are

| | |
|---|---|
| `AGENTS.md` | rules for AI agents (and a good summary for humans) |
| `docs/PLAN.md` | phases, goals, decisions |
| `docs/DATA_FORMAT.md` | the one format everybody's data uses |
| `docs/SCORING.md` | how sub-indicators + a profile become 0-100 scores |
| `python run.py dashboard` | choose indicators, see rankings, explain a company's score; Workspace tab = all commands as buttons |
