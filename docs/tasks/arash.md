# Arash - Architect and Integrator


> **This is a proposal, not an order.** You own this file - if you see a better
> route, edit it, commit it, and tell the team in one line. The only things that are
> not yours to change alone are the contracts in `src/ethack/contracts.py` and the
> file ownership table in `CONVENTIONS.md`.


You are the only person who touches the seams. Your job is that nobody else is ever
blocked, and that the parts fit at 06:00 without a night of surprises.

**Your files:** `CLAUDE.md` `CONVENTIONS.md` `Makefile` `contracts.py` `config.py`
`sources/sec.py` `sources/ex21.py` `link.py` `indicators/base.py`
`indicators/registry.py` `blackout.py` `app/main.py` `app/pages/1_explorer.py`
`app/pages/2_blackout.py` `data/manual/link_labels.csv`

---

## 16:00 - 17:00 | Unblock everyone

The repo scaffold, contracts and mock generator already exist. Your first hour is
spent making sure four other people can start without asking you anything.

- [ ] Push the repo, add everyone as collaborators
- [ ] Everyone runs `python run.py mocks && python run.py test` and confirms 9 tests pass
- [ ] Walk the team through `CONVENTIONS.md` section 1 out loud. Two minutes.
      **Nobody edits a file they do not own** - this is what lets five people push
      to `main` all night with zero conflicts.
- [ ] Confirm each person has read `docs/THESIS.md`. If they have not, the code
      they write will not fit the argument.

## 17:00 - 21:00 | SEC + EX-21, then the link layer

`sources/sec.py`: tickers, CIK map, XBRL revenue/EBITDA. Needs a User-Agent header
(`config.SEC_USER_AGENT`) or SEC returns 403.

`sources/ex21.py` is the one that matters. For each S&P 500 CIK:
1. `data.sec.gov/submissions/CIK{cik:010d}.json` -> newest 10-K accession
2. `.../Archives/edgar/data/{cik}/{acc_nodashes}/index.json` -> find `*exx21*.htm`
3. strip tags, one subsidiary per line, label with the parent ticker

Verified working: Duke (CIK 1326160) yields 186 subsidiaries including
*Cinergy Corp*, *Caldwell Power Company*, *Catamount Energy Corporation*.

Not every filer puts EX-21 in a separate exhibit - some bury it in the 10-K body.
Expect maybe 70-85% to parse cleanly. **That is fine.** Log the misses and move on.

## 21:00 - 00:00 | link.py - the critical path

> **Model decision: YES, embeddings, plus a small trained reranker.**
> Levenshtein cannot get "Cinergy Corp" to "Duke Energy" - the registry is doing the
> real work and embeddings handle suffix noise, abbreviations and d/b/a variants.
> Call it *retrieval over a ground-truth registry with a learned reranker*, not
> "we used AI to match companies". Precision is what makes it credible.

1. normalise: strip `(100%)`, legal suffixes, punctuation, casefold
2. exact match on normalised names - this alone should get you most of the way
3. embeddings + cosine top-k over the registry for the remainder
4. rerank on `confidence = f(cosine, token overlap, state match, NAICS plausibility)`,
   fitted on ~300 labels in `data/manual/link_labels.csv`
5. **publish precision and recall on held-out labels.** An unmeasured join is a guess.

Hard gate: if you are not done by **00:00**, ship exact-match plus manual overrides
for the top 200 facilities by tonnage (~80% of emissions) and state coverage openly.
Partial coverage stated beats full coverage fabricated, and judges can tell.

## 00:00 - 06:00 | Indicator framework, then the blackout engine

`base.py` and `registry.py` are already written and tested - check they fit what
Lauren actually needs and adjust with her, not around her.

Then `blackout.py`. `impact()` must return four exact numbers: indicators lost,
companies gone dark, rank churn (Kendall tau vs. full score), mean CI widening.
**Those four numbers are the slide.** Sleep 03:00-06:00 if the link layer is clean.

## 06:00 - 09:00 | Dashboard integration

Wire `1_explorer` and `2_blackout` to real output. Florian and Harprit deliver their
own pages against `_shared.load()`; you own the shell and you own the demo.

Rehearse the blackout toggle until it takes 15 seconds and never errors.

## Your wow contribution

**The blackout simulator.** It is the single most memorable thing in the project.
Protect the time for it - it is worth more than a better join.

## Done when

- [ ] `python run.py all` runs clean from a fresh clone on mock data
- [ ] link precision/recall in `METRICS.md`
- [ ] blackout page produces four real numbers and never crashes
- [ ] every teammate's page renders inside the shell
