# The argument

Read this before writing code. Every technical decision in this repo follows from it.

## The client

An ETH-affiliated fund. European, institutionally supervised, and therefore subject
to its own disclosure obligations - it has to report on the climate characteristics
of what it holds, whether or not the underlying data still exists.

## The situation

US federal environmental and climate data provision has been materially rolled back:
mandatory greenhouse-gas reporting has been proposed for rescission across most
sectors, the SEC's climate disclosure rule was abandoned rather than defended, and a
range of federal climate datasets and web resources have been removed, defunded or
altered.

> **Before you put any of this on a slide, verify the current status of each item and
> cite a primary source with a date.** The argument is strong enough that it does not
> need a single unsourced claim, and an institutional audience will check. Treat
> anything you cannot source as not said.

## Why that is a portfolio problem, not a politics problem

This is the move that makes us different. We are not making an argument about
policy. We are making an argument about **information risk**.

1. Most ESG analytics silently depend on US mandatory disclosure. When the mandate
   goes, the data does not become wrong - it becomes *absent*, which is worse,
   because absence is invisible in a score. A rating that used to mean "measured
   low emissions" starts meaning "we no longer know", and it still prints as a number.
2. A European fund cannot stop reporting because its data source stopped existing.
   Its obligations are set in Brussels and Bern; its data was being collected in
   Washington. That mismatch is now a live operational risk.
3. Therefore the question is not only "how sustainable is this company?" but
   **"how much of this company can I still see, and for how long?"**

## What we build

Three things, in order of how much they differentiate us:

1. **A durability-rated indicator system.** Every indicator declares where its data
   comes from and how politically erasable that source is. Scores carry a visibility
   measure alongside the value. A company can be rated "clean and well-observed" or
   "clean but unverifiable", and those are completely different risk positions.
2. **An archive.** We snapshot the metered ground truth now, with timestamps and
   provenance, and commit it. If GHGRP reporting is rescinded, this repo contains a
   dated copy of what the meters said. That is a genuine asset, not a gesture.
3. **A blackout simulator.** The fund can switch a source off and watch what happens
   to its rankings, its confidence intervals, and its portfolio. This is the demo.
   It takes fifteen seconds and it is the thing the judges will remember.

## Why the satellite layer is strategic, not a fallback

Satellite observation is the only emissions data nobody can legislate away. European
Space Agency Sentinel instruments and the Climate TRACE coalition are outside the
reach of any US administrative decision. For a Swiss fund, a risk process grounded in
European and private observation infrastructure rather than US self-reporting is not
an ideological preference - it is a continuity requirement.

**The line for the pitch:** *a European fund should not have its risk visibility
depend on American political weather.*

## Why flexible indicators are not a gimmick

Because sources die. A fixed indicator set is a framework with an expiry date. The
registry pattern means that when a source disappears, the fund swaps the indicator,
re-runs, and sees immediately what it costs them in coverage and confidence. The
flexibility requirement and the disappearing-data thesis are the same mechanism.

## What would make us wrong

Say this out loud in the pitch; it is a strength, not a hedge.

- If US disclosure requirements are restored, the durability weighting matters much
  less and we are left with a conventional (if unusually well-grounded) score.
- If satellite estimates turn out to diverge badly from metered values at company
  level, our continuity story weakens and we would need to say so.
- Our coverage is US facilities. A company's foreign operations are measured far more
  weakly, and we report that coverage ratio per company rather than hiding it.
