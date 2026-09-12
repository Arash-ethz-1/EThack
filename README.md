# EThack - sustainability impact of the S&P 500

Challenge: quantify and compare the sustainability of S&P 500 companies for an
ETH-affiliated fund, and use it to weight a portfolio.

```
economic/  social/  environmental/      >= 3 sub-indicators each, one shared data format
        \      |      /
      python run.py score               impact score 0-100 per category per company
               |
          portfolio/                    allocation weights (phase 3)
```

| Category | Who |
|---|---|
| Economic | Arash |
| Social | Florian, Lauren |
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
| `docs/tasks/<name>.md` | your assignment, candidate indicators, your log |
| `docs/DATA_FORMAT.md` | the one format everybody's data uses |
| `docs/SCORING.md` | how sub-indicators become a 0-100 score |
