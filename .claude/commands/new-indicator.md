---
description: Add a new sub-indicator (catalog row + script) in the shared format
---

Indicator the person wants: $ARGUMENTS

1. Make sure `python run.py start` ran this session.
2. Agree with the person on: category, `indicator_id` (lowercase_snake_case), what it measures,
   why it is *impact*, direction (higher or lower is better), unit, and the source.
   Check the "strong indicator" criteria in AGENTS.md section 4 - say honestly if it looks weak
   (low coverage, size-driven, duplicate of an existing indicator).
3. Run `python run.py new-indicator <category> <indicator_id>`.
4. Fill in name, description, unit, higher_is_better, source in `<category>/catalog.csv`; status `in_progress`.
5. Before building everything: download a small sample and estimate coverage of the S&P 500.
   Report it to the person and decide together whether to continue.
6. Implement `build()` in `<category>/scripts/<indicator_id>.py` using `common.io`
   (`cached_json`/`cached_download`, `write_indicator`). Run `python run.py build <category> <indicator_id>`.
7. Spot-check a few values against the source with the person. Only then set status `ready`.
8. `/save` after each working step, not only at the end.
