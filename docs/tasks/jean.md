# Jean - Data Acquisition and the Archive


> **This is a proposal, not an order.** You own this file - if you see a better
> route, edit it, commit it, and tell the team in one line. The only things that are
> not yours to change alone are the contracts in `src/ethack/contracts.py` and the
> file ownership table in `CONVENTIONS.md`.


You own everything that enters the repo from outside. The framing that makes your
work a headline rather than plumbing: **you are not downloading data, you are
archiving a record that is being withdrawn.**

**Your files:** `sources/epa.py` `sources/echo.py` `sources/satellite.py`
`sources/reports.py` `data/raw/*` `data/manual/reported_scope1.csv`
`data/PROVENANCE.md`

---

## 16:00 - 19:00 | EPA GHGRP, every year, not just the latest

```
https://data.epa.gov/efservice/pub_dim_facility/year/{YYYY}/rows/{a}:{b}/JSON
https://data.epa.gov/efservice/pub_facts_sector_ghg_emission/year/{YYYY}/rows/{a}:{b}/JSON
```

Verified: 11,281 facilities for 2023, with `parent_company`, NAICS, lat/lon, and
CO2e per gas. Envirofacts pages at 10k rows - loop the window until a short page.

**Pull 2010 through 2023.** Not just 2023. Two reasons: the historical panel is what
Harprit's model trains on, and the archive is the thesis. Commit the parquet.

## 19:00 - 21:00 | ECHO + provenance discipline

`echodata.epa.gov/echo/cwa_rest_services.get_facilities` - verified, returns
violation counts and penalty dollars. This feeds an indicator and it is Harprit's
validation ground truth, so tell him the moment it lands.

Every fetch appends a row to `data/PROVENANCE.md`: UTC timestamp, source id,
endpoint, row count, durability rating, notes. **Append only.** This file is a
deliverable - it is what makes our archive an archive and not a folder of parquet.

## 21:00 - 00:00 | Satellite - the layer nobody can switch off

`api.climatetrace.org/v6/assets` - verified 200 OK.

This is strategically the most important source you touch, because it is the only one
outside the reach of any administrative decision. Sentinel instruments are ESA;
Climate TRACE is a private coalition. For a Swiss fund, that continuity is the point.

The join to companies is **spatial**, not by id: match assets to EPA facilities on
lat/lon proximity, then inherit the ticker from Arash's link table. Keep a distance
threshold and record the match distance - an honest spatial join with a stated
tolerance is defensible; a silent nearest-neighbour is not.

## 00:00 - 04:00 | The "Say" side

> **Agent decision: YES, an extraction agent per company - but hand-collect first.**
> Do the 50 largest emitters by hand before you launch anything. Those 50 are your
> accuracy benchmark, and "the agents agreed with us on 47 of 50" is the sentence
> that saves the Say-Do slide under questioning.

Strict schema, and the rule is absolute: **every row carries `verbatim_quote`,
`source_url` and `page`, or it does not get written.** An uncited number is a
hallucination with good posture.

Add `assurance_provider` - whether *anyone* third-party audited the figure. It is a
sleeper signal and it costs you nothing to capture while you are already in the file.

Adjudication: if the extracted value implies >2x divergence from the metered sum, a
second agent re-reads the source and rules before the row is accepted.

Then hand-audit a random 30 and **write your own extraction precision into
`METRICS.md`.** Publishing your error rate is what makes the whole layer credible.

Sleep 04:00-08:00. Your work is upstream; the back half of the night is not yours.

## Your wow contribution

**The Data Durability Register.** For every source: what it is, who can switch it
off, what it costs us if they do. Nobody else in the room will have thought about
their data supply chain as a risk. This register is what makes the innovation in
*data selection* real rather than rhetorical.

## Done when

- [ ] GHGRP 2010-2023 cached and committed
- [ ] ECHO cached, Harprit notified
- [ ] satellite cached with a documented spatial join tolerance
- [ ] `reported_scope1.csv` with citations on every row + a stated precision figure
- [ ] `PROVENANCE.md` complete - every row, no gaps
