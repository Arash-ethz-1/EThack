# METRICS.md

Every number we claim, with its method and its n. OWNER: Harprit.
A judge opens this file to decide whether we are serious. Empty rows are honest;
invented rows are fatal.

## Entity resolution (L2, Arash)

| Metric | Value | n | Method |
|---|---|---|---|
| Link precision | | | held-out hand labels |
| Link recall | | | held-out hand labels |
| Facilities matched | | | of total GHGRP facilities |
| Tonnage coverage | | | matched CO2e / total CO2e |

## Extraction (L1 reports, Jean)

| Metric | Value | n | Method |
|---|---|---|---|
| Extraction precision | | 30 | random hand audit |
| Agreement with hand-collected benchmark | | 50 | largest emitters |
| Rows with full citation | | | must be 100% |

## Score validation (L6, Harprit)

| Metric | Value | n | Method |
|---|---|---|---|
| Enforcement odds ratio (Q1 vs Q5) | | | score through 2021, outcomes 2022-24 |
| p-value | | | |
| Same test, vendor ESG score | | | benchmark |
| Event-study abnormal return, high vs low CaR | | | +/-3d, market model |
| Information half-life (tau vs. data age) | | | see eval/validate.py |

## Coverage and honesty

| Metric | Value | Notes |
|---|---|---|
| Companies scored | | of 500 |
| Companies below rankable coverage | | we flag rather than rank these |
| Median visibility | | |
| Indicators surviving full US federal blackout | | must be > 0 |
