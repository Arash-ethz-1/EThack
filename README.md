# EThack - Sightline

**Sustainability intelligence that survives the disappearance of its own sources.**

Client: an ETH-affiliated fund. Challenge #1: quantify and compare the sustainability
of S&P 500 companies.

## The 30-second version

US federal environmental and climate disclosure has been materially rolled back.
Datasets that ESG analytics quietly depend on are being defunded, rescinded or
taken offline. A European fund that builds its climate risk process on
self-reported US ESG data is building on ground that is actively being removed.

Sightline does three things nobody else in the room will do:

1. **Archives** the regulator-metered ground truth while it still exists
   (EPA GHGRP facility-level emissions, ~11.3k facilities, back to 2010).
2. **Rates every indicator for durability** - can this source still be here in
   12 months? - and weights the score by how well we can actually *see*.
3. **Simulates data loss.** The dashboard has a kill switch: turn off a source,
   watch the rankings move and the confidence intervals explode, and see exactly
   which holdings go dark.

We do not publish a number. We publish a number *and how much of it you can trust*.

## Quickstart

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
make mocks        # generate fake data satisfying every contract - unblocks everyone
make app          # launch the dashboard on mock data
```

## Read these before writing code

- `CLAUDE.md` - project context. Every Claude agent on this repo reads this first.
- `CONVENTIONS.md` - git, testing, file ownership. **The ownership table prevents merge hell.**
- `docs/THESIS.md` - the argument we are making. Read it or your code will not fit it.
- `docs/tasks/<yourname>.md` - your assignment, your files, your definition of done.

## Pipeline

```
L1 sources/  ->  L2 link.py  ->  L3 indicators/  ->  L4 score.py  ->  L5 portfolio/  ->  L6 eval/
                                        ^
                              registry: add a file, get an indicator
```
