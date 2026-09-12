# Fitting this project to a real ETH endowment fund

**Status:** research + proposal. Nothing in this document has been implemented.
**Written:** 2026-09-13. **Author:** research session (Florian's area, proposal only).
**Ownership:** everything proposed here touches `profiles/` and `portfolio/`, which are
**Arash's** files (`AGENTS.md` section 2). This document proposes; Arash decides and merges.
No file outside this one was created or changed.

**How to read the evidence markers:**

- **[verified]** - I opened the cited URL and read the claim there.
- **[derived]** - my own arithmetic on a cited number, or a number I printed from this repo.
- **[unverified]** - I could not confirm it from a primary source. Treat as a question, not a fact.

All repo numbers in this document were printed by code run against the working tree on
**2026-09-13 00:00 CEST**. The catalogs changed twice while I was writing (teammates are
committing live), so re-run before quoting them on stage.

---

## 0. The one-paragraph summary

ETH Zürich publishes an annual sustainability report on its own financial assets, and it
is far more specific than anyone on this team assumed. It does **not** run a stock-picking
endowment: ~CHF 376m sits in three mixed mandates at UBS, ZKB and Vontobel, mostly in
indexed sustainable fund building blocks. Its real policy is a **three-layer stack**:
(1) norm- and product-based exclusions above a 5%-of-revenue threshold, on top of the
SVVK-ASIR list; (2) **best-in-class selection within each sector** (ZKB keeps the top
80-85% per sector; MSCI SRI the top 25% per industry); (3) stewardship - voting and
engagement with an escalation path, divestment as the last resort. This project currently
implements *none* of layer 1, an *absolute* rather than sector-relative version of layer 2,
and nothing of layer 3. The two changes that would make it credible to an ETH fund are
small: set `sector_relative = true`, and add a product-exclusion step *before* the score
tilt. The evidence that this matters is in our own output: **both S&P 500 tobacco companies,
Philip Morris (96th) and Altria (98th), sit in the top fifth of 503** - and every university
fund in the world excludes tobacco outright.

---

## 1. What ETH Zürich actually commits to

### 1.0 The legal mandate - and the sentence this whole project should be sold on

**[verified]** The binding instrument is the **«Anlagerichtlinien des ETH-Rats vom 14. Juli
2021»** (in force 1 August 2021), issued under Art. 34c(2) ETH-Gesetz:
<https://ethz.ch/content/dam/ethz/main/eth-zurich/organisation/rechtssammlung/120.4.pdf>
(the ethz.ch host returns 503 to automated fetches; I read the PDF text after retrieving it
in this session).

Scope, verbatim: it applies to «die beiden ETH (ETH Zürich und EPFL) und die vier
Forschungsanstalten (PSI, WSL, Empa und Eawag)», and only to **«andere Mittel»** - third-party
and donated funds - explicitly **not** to federal appropriations («Sie gelten nicht für direkte
und indirekte Bundesmittel»). So the fund this challenge is about is legally the *donated*
money, not ETH's operating budget.

Two clauses matter enormously for how we pitch this tool.

**§2(b) - the reputational mandate:**

> «Die Auswahl und die Bewirtschaftung der Anlagen haben sorgfältig und im Einklang mit der
> **Vorbildfunktion des ETH-Bereichs bezüglich verantwortungsvollem Investieren** zu erfolgen,
> damit negative Auswirkungen auf die **Reputation** der Institutionen des ETH-Bereichs
> vermieden werden.»

The legal test is a *role-model* and *reputation* test - not a risk-adjusted-return test, and
not a score. That is the strongest possible argument for why a policy exclusion cannot be
delegated to a percentile rank: owning tobacco is a reputational fact regardless of how the
company ranks on our indicators.

**§10 - sustainability, and the clause this repo was accidentally built for:**

> «Sie investieren verantwortungsbewusst, indem sie ESG-Kriterien in den Anlageprozess
> integrieren [...]. Der Nachhaltigkeitsansatz ist als Bestandteil des Anlageprozesses
> ganzheitlich gefasst, damit möglichst alle Anlageklassen berücksichtigt werden können.
> Er **folgt objektiven Kriterien und ist transparent und nachvollziehbar**.»

*Objective criteria, transparent and comprehensible.* A deterministic open-source pipeline
where every value carries a `source_url` a human can open, and `explain()` breaks a score into
per-indicator points, is a direct answer to that sentence. **This is the single best line to
open the presentation with.**

**Governance [verified]:** the institutions file an annual investment report and, separately,
«einmal jährlich einen **Nachhaltigkeits-Report** bzgl. der getätigten Anlagen» to the ETH
Board, and the ETH Board's Internal Audit checks compliance with the guidelines annually. The
document in §1.1 is that mandated report.

### 1.1 The primary source nobody had read: ETH's own report on its financial assets

**[verified]** ETH Zürich publishes *«Nachhaltigkeitsbericht 2025 - Finanzmittel der ETH
Zürich»*, dated **17 April 2026**, describing the sustainability characteristics of its own
invested assets as at 31.12.2025:
<https://ethz.ch/content/dam/ethz/associates/services/finance-and-controlling/open/Nachhaltigkeitsbericht_2025_Finanzmittel_ETH_Zuerich.pdf>
(the 2024 edition is at the same path with `2024` in the filename:
<https://ethz.ch/content/dam/ethz/associates/services/finance-and-controlling/open/Nachhaltigkeitsbericht_2024_Finanzmittel_ETH_Zuerich.pdf>)

This is the single most important document for this challenge. What it says:

**Structure of the portfolio [verified]**

> «ETH Zürich investiert ihre Finanzmittel in drei gemischte Vermögensverwaltungsmandate.
> Im Sinne einer effizienten und kostengünstigen Umsetzung werden zwei dieser Mandate
> indexiert umgesetzt. [...] Das dritte gemischte Vermögensverwaltungsmandat verfolgt einen
> aktiven Anlagestil und investiert sowohl in Einzeltitel als auch in Kollektivanlagen.»

Managers are **UBS, ZKB (Swisscanto) and Vontobel**. Equities and corporate bonds are
**65.7% of the Finanzmittel**; Swiss real estate is **8.6%**.

**[derived]** Total financial assets ≈ **CHF 376m**: the report gives "Aktien Schweiz ESG,
UBS, 43.2 CHF Mio., 11.5%" and "Aktien Welt Climate Aware, UBS, 45.5 CHF Mio., 12.1%";
43.2/0.115 = 375.7 and 45.5/0.121 = 376.0. The report does not print a headline total, so
this is my arithmetic, not a quoted figure.

**Exclusions - layer 1 [verified]**

> «Bei allen Investitionen der ETH Zürich in Unternehmen werden neben den SVVK-Titeln
> zusätzlich weitergehende Ausschlusskriterien umgesetzt, die über die Ausschlussliste des
> SVVK-ASIR hinausgehen.»
>
> «Dabei werden alle Unternehmen ausgeschlossen, welche mehr als 5% der Einnahmen aus dem
> jeweiligen Sektor generieren. Alle Vermögensverwalter gaben zudem an, dass sie teilweise
> bereits ab einem Anteil von mehr als 0% der Einnahmen Ausschlüsse vornehmen.»

The excluded sectors, per manager (✓ = applied):

| Sector | UBS | ZKB | Vontobel (single stocks) |
|---|---|---|---|
| Kohle (coal) | ✓ | ✓ | ✓ |
| Andere fossile Brennstoffe | ✓ | | ✓ |
| Verteidigungs- oder zivile Feuerwaffen | ✓ | ✓ | ✓ |
| Tabak | ✓* | | ✓ |
| Alkohol | ✓* | | ✓ |
| Erwachsenenunterhaltung | ✓* | ✓ | ✓ |
| Glücksspiel | ✓* | | ✓ |
| Internationale Normen | ✓ (UN Global Compact) | ✓ (UN Global Compact) | ✓ (UN Global Compact, OECD Guidelines) |

(* except World and Emerging Market equities.)

Two things matter here for us. First, the criterion is a **revenue share threshold (5%)**,
not a name list. Second, **UN Global Compact / OECD Guidelines norms-based exclusion** is
applied by all three managers.

**Best-in-class within sector - layer 2 [verified]**

This is the finding that maps directly onto `sector_relative`:

> **ZKB Responsible:** «Pro Sektor wird durchschnittlich nur in die rund 80% bis 85% der
> Unternehmen mit den höchsten Nachhaltigkeitsbewertungen investiert. [...] Die
> CO2-Intensität wird gegenüber dem Gesamtmarkt der jeweiligen Anlagekategorie um
> mindestens 20% reduziert.»
>
> **MSCI Socially Responsible Investment (SRI):** «Die MSCI SRI Indexes nehmen nur
> Unternehmen mit den höchsten ESG-Scores auf und berücksichtigen dabei nur die besten 25%
> jeder Branche nach ESG-Bewertung.»
>
> **Vontobel (active mandate):** «ein quantitativer Nachhaltigkeitsfilter [...], welcher bei
> den globalen Aktien (MSCI World Index) zur Folge hat, dass nur in die rund 53% der Firmen
> mit den höchsten Nachhaltigkeitsbewertungen investiert wird (Best-in-Class-Ansatz)»,
> plus «eine Reduktion des CO2-Fussabdrucks um mindestens 30% im Vergleich zur Benchmark»
> and «eine Mindestquote von 15% in Anlagen mit positiven Nachhaltigkeitsauswirkungen».
>
> **UBS Climate Aware:** «verfolgt einen Absenkpfad für den CO2-Fussabdruck, indem er
> gegenüber dem CO2-Fussabdruck des Gesamtmarkts (MSCI World ex CH) im Jahr 2019 eine
> jährliche Reduktion von 7% anstrebt. Der Absenkpfad ist auf einen impliziten
> Temperaturanstieg von 1.5 Grad Celsius ausgerichtet.»
>
> **SIX ESG:** companies must earn «weniger als 5% ihres Umsatzes in umstrittenen Sektoren
> (Erwachsenenunterhaltung, Alkohol, Waffen, Glücksspiel, Gentechnologie, Energieerzeugung
> aus Kernkraft, Kohle, Ölsande, Tabakprodukte)» and must not be on the SVVK-ASIR list;
> rated with the **Inrate ESG Impact Rating**.

Note: every single one of these is **relative to a sector, industry or benchmark** - never an
absolute cross-market ranking. That is the strongest single argument in this document for
changing our default.

**Stewardship - layer 3 [verified]**

- «In allen Aktienprodukten übt die Fondsleitung die Stimmrechte aus.» Per sub-mandate the
  share of equity capital voted is **at least 72%**; several are at 100%.
- All managers run engagement; all have an escalation procedure: «Ein Vermögensverwalter hat
  zum Beispiel angegeben, dass er Emittenten bei nicht erfolgreichen Engagements und sehr
  schwerwiegenden Verstössen untergewichtet oder als letztes Mittel veräussert.»
- Managers hold **>30 ESG memberships**, explicitly including **Climate Action 100+** and **CDP**.

**Climate metrics actually reported [verified]** - t CO2e per CHF m revenue, Scope 1&2,
portfolio (PF) vs benchmark (BM), as at 31.12.2025:

| Sub-mandate | PF | BM | PF vs BM |
|---|---|---|---|
| Aktien Welt Climate Aware (UBS) | 57.1 | 115.4 | −51% |
| Aktien Welt Einzeltitel (Vontobel) | 36.8 | 110.2 | −67% |
| Aktien Schweiz ESG (UBS) | 94.8 | 142.1 | −33% |
| Aktien EMMA ESG Screened (UBS) | 244.3 | 347.1 | −30% |

Coal exposure is reported separately (e.g. Aktien Welt Climate Aware: 0.5% PF vs 1.2% BM).
Every metric carries a **Transparenzquote (TQ)** - the share of the portfolio for which the
data exists. This is a coverage discipline identical in spirit to our `min_weight_share`.

**Reporting standards [verified]**

- Metrics are consolidated «in Anlehnung an den ASIP ESG-Reporting Standard» (ASIP is the
  Swiss pension fund association).
- Swiss Climate Scores are named as an example of what managers supply: «einen Bericht,
  welcher die Swiss Climate Scores beinhaltet».
- **[unverified]** The report does not state a net-zero target date for the portfolio, an
  absolute decarbonisation trajectory for the total assets, a PRI signatory status for ETH
  Zürich itself, or TCFD-aligned reporting by ETH. I looked for all four and did not find
  them in this document. Do not claim them.

### 1.2 SVVK-ASIR - the Swiss reference exclusion list

**[verified]** The Schweizer Verein für verantwortungsbewusste Kapitalanlagen (SVVK-ASIR)
publishes its exclusion recommendations: <https://svvk-asir.ch/en/exclusion-list> and
describes its approach at <https://svvk-asir.ch/en/activities/controversial-weapons>.

Its logic, which a university fund will recognise immediately:

- **Product-based, no dialogue:** for manufacturers of cluster munitions, anti-personnel
  mines and nuclear weapons there is no engagement, because the product itself violates
  norms Switzerland has ratified (Ottawa and Oslo Conventions, the Non-Proliferation Treaty).
  These are excluded outright.
- **Conduct-based, dialogue first:** for behavioural violations SVVK-ASIR engages, and
  **exclusion is the outcome of failed engagement**, not the first move.

That split - *product = exclude immediately, conduct = engage then exclude* - is exactly the
distinction our `[portfolio]` settings do not currently make.

### 1.3 ETH Zürich's institutional climate target

**[verified]** ETH Zürich targets **net zero by 2030** for its own emissions:
<https://ethz.ch/en/the-eth-zurich/sustainability/net-zero.html> and the white paper
*"ETH Zurich strives for Net Zero by 2030"* (September 2022):
<https://ethz.ch/content/dam/ethz/main/eth-zurich/nachhaltigkeit/05_netzero/ETH-Whitepaper_Nettonull_EN_Sept22_final.pdf>.
As a decentralised unit of the federal administration it is also bound to at least a **50%
reduction by 2030** under the 2019 Federal Administration climate package.

**[unverified]** I found no document extending the 2030 net-zero target to the *investment
portfolio*. The campus target and the portfolio policy are separate in ETH's own publications.
A fund judge will know this; do not blur them.

### 1.4 The ETH Zürich Foundation

The ETH Zürich Foundation (<https://ethz-foundation.ch/en/foundation/>) is a legally separate
entity from ETH Zürich that raises and manages donations.

**[unverified]** It publishes **no exclusion list, no named managers, no AUM figure and no
PRI signatory status** that I could find - only a general statement that it attaches
importance to sustainable investment and includes sustainability in its investment strategy
per current ESG criteria. The report in §1.1 covers *«Finanzmittel der ETH Zürich»* - the
school's own assets - and does not state that it covers Foundation assets.

**Treat the Foundation's investment policy as effectively undisclosed**, and say so if asked.
Claiming the Foundation applies the policy in §1.1 would be the kind of error a fund judge
catches. Note the useful flip side: **the Foundation is the part of the ETH ecosystem with the
least public methodology, which is exactly where a transparent, reproducible tool has the most
to offer.**

### 1.5 Swiss regulatory context

**[verified] Swiss Climate Scores.** Voluntary transparency standard introduced by the
Federal Council in 2022; the Federal Council decided on **8 December 2023** to develop them
further (<https://www.admin.ch/gov/en/start/documentation/media-releases.msg-id-99293.html>,
overview at <https://www.sif.admin.ch/en/swiss-climate-scores-en>). Swiss Sustainable Finance
and the Asset Management Association Switzerland published template **version 2.0 on 30 May
2024** (<https://www.sustainablefinance.ch/en/resources/climate-finance/swiss-climate-scores.html>).
The indicators fall into two groups: current state - "greenhouse gas emissions and exposure
to fossil fuel activities" - and transition to net zero - "verified commitments to net-zero
and management to net-zero, credible stewardship and global warming potential".
**[unverified]** I did not obtain the exact per-indicator wording from the official PDF; cite
the two groups, not invented indicator names.

**[verified] EU Paris-Aligned Benchmarks - the numeric exclusion standard.** Commission
Delegated Regulation (EU) 2020/1818, Article 12
(<https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32020R1818>) requires exclusion of:

- controversial weapons;
- cultivation and production of tobacco;
- companies "in violation of the United Nations Global Compact (UNGC) principles or the OECD Guidelines";
- ≥**1%** of revenue from hard coal and lignite;
- ≥**10%** of revenue from oil fuels;
- ≥**50%** of revenue from gaseous fuels;
- ≥**50%** of revenue from electricity generation with GHG intensity >**100 g CO2e/kWh**.

It also requires at least a **50%** lower GHG intensity than the investable universe (Art. 11;
30% for Climate Transition Benchmarks, Art. 9), an average **7% p.a.** reduction in GHG
intensity (Art. 7), and exposure to high-climate-impact sectors "at least equivalent to the
aggregated exposure of the underlying investable universe" (Art. 3).

That last clause is the regulator saying, in effect, *do not decarbonise by dumping the Energy
sector*. It is the regulatory twin of `sector_neutral = true`. Note also that UBS Climate
Aware's 7% p.a. path in ETH's portfolio is the same number as Article 7 - these standards are
the water ETH's managers swim in.

**[verified] Swiss corporate climate disclosure.** Switzerland's Ordinance on Climate
Disclosures makes TCFD-aligned reporting binding for large Swiss companies from financial
year 2024 (<https://www.sif.admin.ch/en/swiss-climate-scores-en> links the wider agenda; the
ordinance itself is Swiss federal law). This applies to *investee* companies, not to ETH as
an asset owner. **[unverified]** I did not confirm any TCFD reporting obligation or practice
for a Swiss university endowment.

---

## 2. What comparable university endowments do

### 2.1 The norm is not divestment - it is a screen plus a target plus stewardship

Only a minority of endowments run an active responsible-investment programme at all, so
"we screen" is not a given in this market. **[verified]** In the 2024
NACUBO-Commonfund Study of Endowments, among institutions reporting a responsible-investing
strategy, **28.6% had implemented an ESG strategy** and **15.2% employed negative screening**;
84% of respondents reference ESG in their investment policy
(<https://www.commonfund.org/blog/ncse-key-highlights-infographic-fy24>,
<https://www.nacubo.org/Events/2025/ELS25-Results-From-the-2024-NACUBO-Commonfund-Study-of-Endowments>).
**[verified]** The following year's study reports ESG integration at **27.1%**, with **63.7%
reporting no active responsible investing practice**
(<https://www.pnc.com/insights/corporate-institutional/manage-nonprofit-enterprises/key-takeaways-from-the-nacubo-study.html>).

Read that honestly: a tool that lets a fund *define its own screen and see what it removes*
is useful precisely because most funds have not built one.

### 2.2 EPFL - the closest possible comparator, and it has a written charter

**[verified - I extracted the PDF myself]** EPFL is governed by the *same* ETH Board
investment guidelines as ETH Zürich (§1.0 names both). It has published a
**Socially Responsible Investment Charter, Version 1.0, approved by EPFL on 5 December 2023**:
<https://www.epfl.ch/about/vice-presidencies/wp-content/uploads/2024/04/ChartePlacementResponsable_2023_newDesign_EN.pdf>

Its criteria, verbatim:

> **2. Fossil fuels.** "we exclude companies that generate over **10% of their revenue** from
> the extraction, transmission or distribution of fossil fuels or from fossil-fuel-based power
> generation." Footnote: "This exclusion can be applied only to investments we make directly.
> For our strategies involving investment funds [...] for now we can exclude only companies
> involved in fossil-fuel extraction."
>
> **3. Controversial weapons.** Excluded "regardless of the percentage of revenue generated
> from this activity" - weapons banned under the **1999 Anti-Personnel Mine Ban Convention, the
> 2008 Convention on Cluster Munitions, the 1972 Biological and Toxin Weapons Convention and
> the 1993 Chemical Weapons Convention**, plus "companies involved in nuclear weapons in
> countries that are not party to the 1968 Treaty on the Non-Proliferation of Nuclear Weapons".
>
> **4. Food staples.** No direct or indirect investment in **wheat, rice, corn, soja** -
> speculation on food commodities.
>
> **5. Category 5 controversies** as defined by **Sustainalytics**: "severe violations of
> international standards and principles such as those set forth in the UN Global Compact, the
> OECD Guidelines for Multinational Enterprises, the UN Guiding Principles on Business and
> Human Rights".
>
> **7. Shareholder engagement.** "we are represented by **Ethos** or by fund managers whenever
> possible".

Three things to take from this. First, **a Swiss federal institute of technology under the
identical legal mandate chose an explicit numeric revenue threshold (10%)** where ETH's
managers use 5% - so a threshold is the expected form of the answer, and our sub-industry
proxy (§3.3) is visibly not one. Second, the **controversial-weapons exclusion is written as
absolute** - no threshold at all. Third, EPFL's honest footnote that the rule can only be
applied to *direct* holdings is the same coverage honesty this project needs.

**[verified]** Note also that in Switzerland controversial-weapons exclusion is partly
statutory, not discretionary: the **War Material Act (KMG) Art. 8b/8c** prohibits direct - and
circumventing indirect - financing of prohibited war material (nuclear, biological and chemical
weapons, cluster munitions, anti-personnel mines). See SVVK-ASIR's framing of the same
conventions at <https://svvk-asir.ch/en/activities/controversial-weapons>.

### 2.3 Concrete policies at named peers

| Institution | Policy | Year | Source |
|---|---|---|---|
| **Cambridge** (CUEF, £3.5bn) | Divest endowment from fossil fuels **by 2030**; net zero across all investments **by 2038**; withdraw from energy-focused public equity managers; 5-year ramp into renewables | 2020 | [cam.ac.uk](https://www.cam.ac.uk/news/cambridge-to-divest-from-fossil-fuels-with-net-zero-plan) |
| **Oxford** (OUem, >£3bn) | Divest from fossil fuels **and** require fund managers to evidence **net-zero carbon business plans**; framed explicitly as "not mere divestment"; based on the Oxford Martin Principles | 2020 | [ox.ac.uk](https://www.ox.ac.uk/news/2020-04-27-oxford-announces-historic-commitment-fossil-fuel-divestment), [Oxford Martin](https://www.oxfordmartin.ox.ac.uk/news/oxford-university-divestment-oxford-martin-principles) |
| **Harvard** (HMC) | Endowment **net zero by 2050** (first US endowment to pledge it); **no direct exposure** to fossil-fuel explorers/developers as of FY2020; legacy indirect LP exposure <2% and no new commitments since 2019 | 2020-21 | [Harvard Gazette](https://news.harvard.edu/gazette/story/2020/04/harvard-endowment-to-go-greenhouse-gas-neutral-by-2050/), [HMC 2021 Climate Report](https://www.hmc.harvard.edu/wp-content/uploads/2021/02/2021-Climate-Report.pdf) |
| **Princeton** (PRINCO) | **Dissociation from 90 named companies** in the **thermal coal and tar sands** segments - an explicit, published company list, not a sector rule; eliminate publicly traded fossil-fuel holdings; net-zero endowment over time | 2022 | [princeton.edu](https://www.princeton.edu/news/2022/09/29/princeton-dissociates-segments-fossil-fuel-industry), [list](https://fossilfueldissociation.princeton.edu/) |
| **Yale** (ACIR/CCIR) | **Five Fossil Fuel Investment Principles**: companies must avoid high-GHG production, minimise emissions, support effective climate policy, support accurate climate science, and be transparent with Yale. Applied case-by-case by a standing committee | 2021 | [Yale News](https://news.yale.edu/2021/04/16/new-principles-regarding-fossil-fuels-guide-yales-endowment), [ACIR](https://acir.yale.edu/implementation-fossil-fuel-investment-principles) |

Three details that change how the table should be read:

- **[verified]** **Oxford is the only one with a clean published exclusion list**
  (<https://www.ouem.co.uk/restrictions/>): weapons illegal under UK law; tobacco; fossil fuel
  exploration and extraction including a ban on thermal coal and oil sands; and funds investing
  primarily in those. But the restriction covers **direct** holdings only - look-through
  exposure is requested of managers, in private equity via a side letter. Its headline "2035"
  target is that portfolio companies have *Paris-aligned net zero plans*, **not** that the
  portfolio is net zero. That is materially weaker than Cambridge's 2038.
- **[verified]** **Cambridge defines "meaningful" exposure as 0.5% of the fund's net asset
  value.** Its 2030 "no meaningful direct or indirect exposure to fossil fuels" is therefore a
  *materiality threshold*, not an absolute exclusion. Cambridge does publish a portfolio WACI
  figure; Harvard, four years into its 2050 pledge, states it is "still several years away from
  publicly reporting financed emissions" (<https://www.hmc.harvard.edu/wp-content/uploads/2024/04/2024-Climate-Report.pdf>).
  Read the targets, then read the definitions - they are where the policy actually lives.
- **[verified]** **MIT rejects divestment outright**, and says why, in the 2015 Plan for Action
  on Climate Change (<https://web.mit.edu/climateaction/ClimateChangeStatement-2015Oct21.pdf>):
  > "Divestment is incompatible with the strategy of engagement that forms the heart of today's
  > plan. [...] Serious action to confront climate change demands intense collaboration across
  > the research community, industry and government; divestment would thwart our ability to
  > collaborate and to convene opposing parties."

  For a **technical university that partners with industry**, this is the argument against our
  exclusion profile, and it deserves an honest answer rather than a dismissal - see §3.2.

**The most important recent data point, and it cuts against divestment [verified].**
In **June 2026 Princeton's endowment manager PRINCO discontinued its 2022 commitment to divest
from publicly traded oil and gas companies**, while keeping the trustee-mandated dissociation
from thermal coal and tar sands. PRINCO's own statement is at
<https://princo.princeton.edu/update-on-net-zero-endowment-goal/>; see also
[Princeton Alumni Weekly](https://paw.princeton.edu/article/princeton-reverses-course-fossil-fuel-divestment)
and [The Daily Princetonian](https://www.dailyprincetonian.com/article/2026/06/princeton-news-adpol-princo-discontinues-divestment-publicly-traded-oil-gas-companies).
PRINCO simultaneously adopted a **net-zero endowment target of 2046**, and had in February 2026
cut its long-run return assumption from 10.2% to 8%. The reversal was justified on
**fiduciary and flexibility grounds** - energy companies were said to have a necessary role in
the transition.

This is the first major reversal of a US endowment fossil-fuel divestment pledge. **Any pitch
built on "everyone is moving toward divestment" is out of date as of three months ago.** It is
also the best possible reason to ship the two-profile design in §3.2 rather than a single
divestment engine.

**Where they agree:** every one of them (a) names a *segment* or *behaviour*, not a score
threshold; (b) pairs the screen with a **dated climate target**; (c) keeps a **governance
body** that decides, with the quantitative work as input rather than as the decision.

**Where they differ:** Cambridge and Princeton(-on-coal) exclude by construction; Yale and
Oxford decide **company by company against principles**; MIT refuses to exclude at all.
Harvard's target is portfolio-emissions-based and deliberately avoids a name list.

ETH sits nearer the Oxford/Yale end than the Princeton end: §1.1 shows ETH's managers running
engagement with an escalation path in which «als letztes Mittel veräussert» - sell as a last
resort. A proposal to this fund that is *only* a divestment engine misreads the client.

### 2.4 The reference exclusion list everyone copies - and its current status

**A correction before the content.** **[verified]** The GPFG's *Guidelines for Observation and
Exclusion* were **replaced by Interim Ethical Guidelines adopted on 7 November 2025**
(<https://www.regjeringen.no/en/documents/interim-ethical-guidelines-for-the-government-pension-fund-global/id3138527/>).
Under them **Norges Bank may no longer decide new exclusions or observations - only revoke
existing ones** - and the Council on Ethics now merely *informs* the Bank rather than
recommending exclusion. A committee reports on the permanent framework by **15 October 2026**.
So describing Norges as *actively* excluding today is wrong. The **criteria themselves are
unchanged**, and they remain the template most institutional lists copy
(<https://www.nbim.no/en/responsible-investment/exclusion-of-companies/>,
Council on Ethics <https://etikkradet.no/en/>):

- **Product-based:** weapons that violate fundamental humanitarian principles (biological,
  chemical and nuclear weapons, cluster munitions, anti-personnel mines), **tobacco
  production**, and recreational cannabis.
- **Thermal coal:** mining companies deriving **≥30% of income from thermal coal
  extraction**; power producers with ≥30% of income or operations from thermal coal, or
  >20 Mt/year extraction, or >10,000 MW coal generation capacity
  (<https://www.regjeringen.no/en/documents/annual-report-2023/id3029746/?ch=4>).
- **Conduct-based:** exclusion follows a **recommendation from the Council on Ethics**, i.e.
  a documented process, not a metric crossing a line.

Note the number: Norges uses **30%** of revenue for coal, the EU PAB (§1.5) uses **1%**, and
ETH's managers use **5%** for a list of sectors. A university fund will ask which threshold we
implement. The honest answer today is *none of them* - see §5.

---

## 3. What this implies for THIS project

### 3.0 The finding that drives everything below

I ran the current pipeline against the current working tree and joined it to
`universe/raw/sp500_constituents.csv`, which carries a **`GICS Sub-Industry`** column (this
is the only exclusion-relevant classification the repo already has).

Take the crudest possible stand-in for ETH's product exclusions - drop every company whose
GICS Sub-Industry is Tobacco, Aerospace & Defense, any Oil & Gas / Integrated Oil,
Casinos & Gaming, Brewers, or Distillers & Vintners. **[derived]**

- That removes **42 of 503 companies (8.3%)**.
- Their mean total score is **43.8** vs **50.2** for the universe - so the score does lean
  the right way on average.
- But **29 of those 42 would survive an `exclude_bottom_pct = 0.2` score cut.** The score and
  the policy disagree about two thirds of the names the policy removes.

And the individual names are worse than the average:

| Ticker | Company | GICS Sub-Industry | Rank (of 503) | Total score |
|---|---|---|---|---|
| PM | Philip Morris International | Tobacco | **96** | 62.1 |
| MO | Altria | Tobacco | **98** | 62.0 |
| WYNN | Wynn Resorts | Casinos & Gaming | **111** | 60.6 |
| CVX | Chevron | Integrated Oil & Gas | 376 | 40.7 |
| RTX | RTX Corporation | Aerospace & Defense | 432 | 34.6 |
| LMT | Lockheed Martin | Aerospace & Defense | 483 | 21.7 |
| NOC | Northrop Grumman | Aerospace & Defense | 484 | 21.5 |
| XOM | ExxonMobil | Integrated Oil & Gas | *no score* | - |

(ExxonMobil falls below the coverage bar at `min_weight_share = 0.6` and is therefore held at
benchmark weight rather than excluded - a good illustration of why a policy exclusion cannot
be delegated to the score: **the score's answer for ExxonMobil is "I don't know".**)

**Both tobacco companies are in our top fifth.** That is not a bug in the indicators - Philip
Morris genuinely scores well on payout ratio, PAC spending and material supply risk. It is a
category error: *a sustainability score measures how a company behaves; an exclusion policy
decides what a university is willing to own at all.* Conflating them is the single mistake
that would lose this pitch.

**Therefore: exclusions must be a separate, earlier step than the score tilt** - which is
exactly the architecture ETH's own report describes (Negativkriterien, then Positivkriterien).

### 3.1 Proposed profile: `profiles/eth_endowment.toml`

Proposed content. **Do not create this file** - it belongs to Arash.

```toml
# ETH Endowment - modelled on ETH Zürich's published policy for its own financial assets:
# Nachhaltigkeitsbericht 2025 "Finanzmittel der ETH Zürich" (17.04.2026).
# Three layers, in ETH's own order: Negativkriterien -> Positivkriterien -> Stewardship.
name = "ETH Endowment"
description = """A Swiss university fund: exclude by product and norm first, then favour \
the better half of each sector, then keep the rest of the market for engagement. \
Sector-relative because every screen ETH's managers actually use (ZKB Responsible, \
MSCI SRI, Vontobel best-in-class) selects within a sector, not across the market."""

# Higher than the 0.5 default: an endowment reports a Transparenzquote next to every
# climate metric and will not act on a company it can only half-see. 0.6 is the highest
# value that still admits 2-of-3 indicators in a three-indicator category - see the
# cliff table below. Do NOT set 0.7: with today's catalog it scores only 354 of 503.
min_weight_share = 0.6

# The single most important setting in this file.
# ZKB Responsible: "Pro Sektor ... rund 80% bis 85% der Unternehmen mit den hoechsten
# Nachhaltigkeitsbewertungen". MSCI SRI: "die besten 25% jeder Branche".
# EU 2020/1818 Art. 3 requires high-climate-impact sector exposure at least equal to the
# investable universe - i.e. do not decarbonise by dumping a sector.
sector_relative = true

[categories]
# Environmental x2: ETH's report leads with climate metrics and fossil-fuel exposure and
# reports them for every sub-mandate; nothing social or economic gets that treatment.
# Not x3 (the net_zero profile's weight) because ETH's policy is explicitly a *combination*
# of approaches under "marktkonformer Rendite" - not a single-issue climate mandate.
environmental = 2
social = 1
economic = 1

[indicators]
# Switch off: its own catalog description opens "NOT an environmental measure -
# political/contractor concentration risk". It is currently 50% of the environmental
# category. Turning it off moves the environmental ranking materially (Spearman 0.76).
federal_contract_exposure = 0

# Weight up when it reaches status = ready. This is the metric ETH's managers actually
# report - tonnes CO2e per CHF m revenue, Scope 1&2, portfolio vs benchmark.
# ghg_intensity = 3

[portfolio]
method = "exclude"
exclude_bottom_pct = 0.15   # ZKB Responsible keeps "rund 80% bis 85%" per sector
sector_neutral = true       # EU 2020/1818 Art. 3; keeps this a company view, not a sector bet
max_weight = 0.05           # UCITS 5/10/40 habit; also caps single-name idiosyncratic risk
```

**Why `sector_relative = true`, with numbers [derived].** With the current indicator set,
absolute ranking hands out large systematic sector bonuses and penalties:

| Sector | n | Mean total score, `sector_relative = false` | ... `= true` | Sector effect removed |
|---|---|---|---|---|
| Utilities | 31 | 39.1 | 49.7 | **+10.6** |
| Industrials | 83 | 43.7 | 50.0 | +6.3 |
| Materials | 25 | 46.2 | 50.4 | +4.2 |
| Consumer Staples | 34 | 55.1 | 50.6 | −4.5 |
| Financials | 76 | **58.5** | 50.4 | **−8.1** |

A tilt on absolute scores systematically overweights Financials and underweights Utilities.
That is a **sector bet dressed as a sustainability view**, and it is the first thing an
investment committee will spot. Switching the flag changes the ranking substantially
(Spearman 0.85 between the two orderings) - it is not cosmetic.

**Why `min_weight_share = 0.6`, and a warning about this setting [derived].** ETH prints a
*Transparenzquote* beside every climate number (§1.1), so raising our coverage bar above the
0.5 default is the right instinct. But the setting has a **cliff**, because it is compared
against a share of *category weight*, and categories have few indicators. With the catalog as
it stood when I re-ran this (economic: 2 ready, social: 3 ready, environmental: 2 ready):

| `min_weight_share` | Companies with a total score | Economic | Social | Environmental |
|---|---|---|---|---|
| 0.5 (default) | 501 | 499 | 495 | 503 |
| **0.6** | **490** | 440 | 495 | 473 |
| 0.7 | **354** | 440 | 410 | 473 |

At 0.7 a three-indicator category demands all three (2/3 = 0.667 < 0.7) and a two-indicator
category demands both, and we lose **147 companies (29% of the universe)**. 0.6 buys real
coverage discipline for 11 companies. **I originally proposed 0.7 and it was wrong** - a
teammate moved `labor_litigation_intensity` to `ready` while this document was being written
and the cliff appeared. Re-run the table before shipping the profile; the right value is a
function of how many indicators are `ready`, not a constant.

### 3.2 A second profile worth shipping: `profiles/eth_engagement.toml`

ETH's managers escalate and sell **as a last resort** (§1.1); Oxford and Yale decide company
by company (§2.2). A profile that models *engagement* rather than exclusion makes the tool
look like it understands its client:

```toml
name = "ETH Engagement"
description = """Same evidence, opposite instrument: hold the whole investable universe and \
tilt, rather than divest. Models the escalation path in ETH's report, where selling is the \
last resort after unsuccessful engagement. The bottom decile is the engagement list, \
not the divestment list."""
min_weight_share = 0.6
sector_relative = true

[categories]
environmental = 2
social = 1
economic = 1

[indicators]
federal_contract_exposure = 0

[portfolio]
method = "tilt"
tilt_strength = 0.6     # the default in docs/superpowers/plans/2026-09-12-portfolio-allocation.md
sector_neutral = true
max_weight = 0.05
```

The pitch line this enables: *"Run both profiles. The difference between them is the list of
companies you would be talking to instead of selling."* That is a deliverable a stewardship
team can actually use, and it costs no new code - both profiles run on the allocation plan
already written.

**Why shipping both is the defensible choice, not a hedge.** The evidence in §2 does not point
one way. MIT refuses to divest because divestment "would thwart our ability to collaborate and
to convene opposing parties" - an argument that lands hard at a technical university with deep
industry partnerships. Princeton reversed its oil and gas divestment in June 2026 on fiduciary
grounds. ETH's own managers treat selling as the last step of an escalation path, not the
first. A tool that *assumes* divestment is the right instrument would be taking a side its
client has not taken; a tool that produces both answers from the same evidence, and shows
exactly which companies the choice is about, respects the governance body whose job that
decision actually is (§1.0: the ETH Board's mandate is a Vorbildfunktion and reputation test,
decided by people, informed by objective criteria).

### 3.3 Exclusions: what a university fund applies, and what this repo can support

| Exclusion | Who requires it | Threshold used in practice | Can this repo do it today? |
|---|---|---|---|
| Controversial weapons (cluster munitions, AP mines, nuclear) | SVVK-ASIR (Ottawa/Oslo/NPT), Norges, EU PAB Art. 12(a) | Any involvement | **No.** Needs the SVVK-ASIR list or an equivalent; it is published as a list, not derivable from our data. |
| Tobacco | ETH managers (>5% revenue), Norges, EU PAB Art. 12(b) | Production; PAB = any cultivation/production | **Partly.** `GICS Sub-Industry == "Tobacco"` → exactly **2 names (MO, PM)**. A classification, not a revenue test. |
| Thermal coal | ETH (coal, >5%), Norges (≥30% income), EU PAB (≥1% revenue) | 1% / 5% / 30% depending on the standard | **No.** There is **no `Coal & Consumable Fuels` company in the S&P 500** today, so the rule would have to bind through diversified miners and utilities - i.e. through revenue segments we do not have. |
| Other fossil fuels | ETH (UBS, Vontobel), EU PAB (≥10% oil, ≥50% gas) | Revenue share | **Partly.** 21 companies across 5 Oil & Gas sub-industries; again a classification, not a revenue share. |
| Weapons / firearms | ETH (all three managers) | >5% revenue | **Partly.** `Aerospace & Defense` = 13 names, but that bundles Boeing and GE with Lockheed - defence revenue share is exactly what we cannot see. |
| Alcohol, gambling, adult entertainment | ETH (UBS*, Vontobel), SIX ESG (<5%) | >5% revenue | **Partly.** Brewers (1), Distillers & Vintners (2), Casinos & Gaming (3). |
| **UN Global Compact / OECD violators** | **All three ETH managers**, EU PAB Art. 12(c), Norges conduct criteria | Assessed case by case | **No, and this is the biggest gap.** It is the one exclusion every single source in this document requires, and we have no controversy or norms data at all. |

**How this maps onto the planned `[portfolio]` settings.** The implementation plan in
`docs/superpowers/plans/2026-09-12-portfolio-allocation.md` gives `allocate()` a
`method = "exclude"` path (`exclude_worst`, which drops the bottom `exclude_bottom_pct` of
**scored** companies). That is layer 2 of ETH's stack. **Layer 1 does not exist in the plan.**

Proposal to Arash - one new pure function, consistent with the plan's architecture:

```python
def exclude_policy(benchmark: pd.Series, sub_industries: pd.Series,
                   excluded: list[str]) -> pd.Series:
    """Zero out companies whose GICS Sub-Industry is on the fund's exclusion list.

    Runs BEFORE exclude_worst/tilt. A policy exclusion is not a score: Philip Morris
    ranks 106/503 on the balanced profile and every university fund excludes tobacco.
    Sub-industry is a proxy for the revenue-share tests real policies use (ETH: >5% of
    revenue from the sector; EU 2020/1818: 1% coal / 10% oil) - it over-excludes
    diversified firms and under-excludes segment exposure inside conglomerates.
    That limitation belongs in the `reason` column, visibly.
    """
```

with a profile block such as:

```toml
[portfolio]
method = "exclude"
exclude_sub_industries = ["Tobacco", "Casinos & Gaming", "Brewers", "Distillers & Vintners",
                          "Oil & Gas Exploration & Production", "Integrated Oil & Gas",
                          "Oil & Gas Refining & Marketing", "Aerospace & Defense"]
exclude_bottom_pct = 0.15
sector_neutral = true
max_weight = 0.05
```

Two consequences a fund will want stated up front **[derived]**:

- Applying that list removes **42 names (8.3% of the universe)**; adding a sector-neutral
  bottom-15% score cut on top leaves **392 of 503 companies**.
- **A sector can be emptied, and the planned code would then silently undo the exclusion.**
  [derived] The S&P 500's Energy sector is **exactly** the 21 Oil & Gas companies
  (9 Exploration & Production, 4 Storage & Transportation, 3 Equipment & Services,
  3 Refining & Marketing, 2 Integrated) - I checked the set equality. The illustrative list
  above names only three of those five sub-industries, leaving 7 Energy companies to carry
  the sector. But a fund that excludes all five - which is what "no fossil fuels" means -
  empties the sector completely, and `sector_neutralise()` in
  `docs/superpowers/plans/2026-09-12-portfolio-allocation.md` (Task 4) falls back to
  `out.loc[members] = benchmark.loc[members]` when a sector's tilted weight is zero. That
  fallback would **re-admit every excluded oil company at benchmark weight**.
  **Arash should be told before Task 4 is implemented.** The fix is to redistribute an
  emptied sector's weight across the surviving sectors and report it, rather than restore
  the benchmark shape. Note this is a deliberate policy choice against EU 2020/1818 Art. 3,
  which asks a Paris-aligned benchmark to keep high-climate-impact sector exposure "at least
  equivalent to the aggregated exposure of the underlying investable universe" - i.e. the
  regulator would rather you held the *best* oil companies than none.

### 3.4 Indicators: what matters most, and what is missing

**What this audience cares about most, of what exists today:**

1. `ghg_intensity` (environmental, **`in_progress`**) - t CO2e per unit of revenue is *the*
   number in ETH's report and in the Swiss Climate Scores' "current state" group. Getting
   this to `ready` is worth more to this audience than any two other indicators combined.
2. `resource_supply_risk` (`ready`) - genuinely differentiated and defensible, and critical
   materials are a live topic for a technical university. Caveat below.
3. `shareholder_payout_ratio` (`ready`) - maps to the stakeholder-vs-shareholder question
   that JUST Capital-style frameworks use; a credible "S" indicator.
4. `tax_rate_gap` (`ready`) - contribution to public finances is a natural fit for a
   publicly funded institution. This is arguably our most ETH-appropriate economic indicator.

**Missing, in priority order for this audience:**

| Missing | Why it matters here | Feasible? |
|---|---|---|
| **Fossil-fuel revenue share** | Every standard in §1.5/§2.3 is defined on it (1%/5%/10%/30%). Without it we cannot implement a single real exclusion rule, only a sub-industry proxy. | Hard. Needs segment revenue; SEC XBRL segment data is messy but exists. |
| **UN Global Compact / OECD norms violations** | Required by **all three** ETH managers and by EU PAB Art. 12(c). The only screen with unanimous support in this entire document. | Hard without a commercial feed (Sustainalytics/ISS/RepRisk - all paid). An open proxy (e.g. enforcement actions, OECD NCP cases) would be a genuinely novel contribution. |
| **Scope 3 / value-chain emissions** | Swiss Climate Scores' forward-looking group asks about net-zero commitments and management, not just current emissions. | Hard; self-reported and sparse. |
| **A stated net-zero / SBTi target per company** | Directly matches Swiss Climate Scores' "verified commitments to net-zero". Binary and checkable. | **Feasible.** SBTi publishes its target list openly - a genuinely achievable new indicator with high relevance to this audience. |
| **Board/workforce indicators** | Cheap to compute from proxy statements and expected in an "S" pillar. | Medium. |

**A caveat we must state, not hide [derived].** `resource_supply_risk` is computed at
**GICS Sub-Industry level**: 503 companies take only **79 distinct values**. Within
Financials, 76 companies share **4** distinct values. So in sector-relative mode the
environmental score for a bank is a 4-level categorical, not a company-level measurement.
It is a real and well-sourced indicator (USGS + World Bank WGI), but it measures an
*industry's* exposure, not a *company's* behaviour. Say this before a judge finds it.

**And one we must fix, not caveat.** `federal_contract_exposure` is `ready` in
`environmental/catalog.csv` and its own description begins *"NOT an environmental measure -
political/contractor concentration risk"*. It is currently **half of the environmental
category score**. Any fund professional reading the catalog will ask why US federal
procurement is an environmental indicator. The proposed profile sets it to `0`; switching it
off changes the environmental ranking materially (Spearman 0.76) **[derived]**.

### 3.5 Fiduciary and return constraints

An endowment is a **perpetual, spending-committed** pool. ETH frames this itself:
«den Grundsätzen von "marktkonformer Rendite und Kosten" sowie einer "angemessenen
Diversifikation" Rechnung zu tragen» - market-conforming return and cost, and appropriate
diversification **[verified, §1.1]**. That has four concrete implications for `allocate()`:

1. **Tracking error is the binding constraint, not the score.** A committee approves a
   deviation from the benchmark, not a ranking. The multiplicative tilt in the plan
   (`w ∝ benchmark · exp(λz)`) is the right shape because `λ = 0` returns the benchmark
   exactly, so `tilt_strength` *is* the risk dial. What is missing is reporting the
   consequence: **active share** and, once market caps exist, ex-ante tracking error.
   **[derived]** We cannot compute tracking error today - there are no market caps and no
   return series in this repo (`grep -rl market_cap` over `universe/`, `common/`,
   `portfolio/` returns nothing but the plan document itself). Say so; do not fake it.
2. **The benchmark must be market-cap weighted eventually.** The plan's equal-weight
   fallback is a defensible placeholder, but an equal-weighted S&P 500 is itself a large
   size-factor bet - bigger, most likely, than the sustainability tilt on top of it. This
   is the honest answer to "what is the cost of your screen": *we cannot yet separate the
   cost of the screen from the cost of the equal weighting.*
3. **Sector neutrality is a fiduciary control, not an ESG preference.** It is why
   `sector_neutral = true` belongs in the endowment profile: it converts "we dislike
   Utilities' data" into "we prefer the better Utilities".
4. **Liquidity and turnover.** A perpetual fund rebalances slowly; an annual indicator
   refresh implies at most annual rebalancing, which is fine. But note **[derived]** that
   `common/score.py` takes each company's *latest available year*, so companies are compared
   across different years. For a fund report that has to be dated, this needs the
   year-alignment decision already open in `docs/SCORING.md`.
5. **Unscored companies must keep their benchmark weight.** The plan already does this
   (`score_z` returns 0.0 for NaN; `exclude_worst` only drops scored companies). This is
   exactly right and worth saying out loud: *a data gap is our failure, not evidence about
   the company* - and it is the same discipline as ETH's Transparenzquote.

---

## 4. What to say in the presentation

### 4.1 Five sentences a university-fund judge would find credible

> The ETH Board's own investment guidelines require that the sustainability approach «folgt
> objektiven Kriterien und ist transparent und nachvollziehbar» - objective criteria,
> transparent and comprehensible - so we built exactly that: every number has a source URL you
> can open, the scoring is deterministic code, and any score breaks down into the indicators
> that produced it.
>
> ETH already publishes exactly what it does with its own CHF ~376m: exclusions above a
> 5%-of-revenue threshold on top of the SVVK-ASIR list, best-in-class selection *within each
> sector* - ZKB keeps the top 80-85% per sector, MSCI SRI the top 25% per industry - and
> engagement in which selling is the last resort.
>
> So we built the tool around that structure rather than around a single ESG number: a
> profile is a written policy, and running it produces the exclusion list, the sector-neutral
> weights, and a per-company reason you can put in front of a committee.
>
> The reason exclusions are a separate step from the score is in our own output: Philip
> Morris and Altria rank 96th and 98th of 503 on our own score, and 29 of the 42 companies a
> standard product screen removes would survive a bottom-20% score cut - a score tells you how
> a company behaves, not whether a university is willing to own it.
>
> And we default to sector-relative ranking, because on absolute ranking our data hands
> Financials +8 points and Utilities −12 purely for being in those sectors, which is a sector
> bet dressed up as a sustainability view - the same reason EU 2020/1818 Article 3 requires a
> Paris-aligned benchmark to keep its high-climate-impact sector exposure.

### 4.2 The two hardest questions, and honest answers

**Q1. "Your environmental score is mostly an industry classification, and one of your two
'ready' environmental indicators says in its own description that it is not an environmental
measure. Why should I trust the environmental pillar?"**

You should not, yet - and here is precisely how far it goes. `federal_contract_exposure` is
currently half the environmental category and its catalog description opens *"NOT an
environmental measure"*; our proposed ETH profile sets its weight to `0`, which changes the
environmental ranking (Spearman 0.76). That leaves `resource_supply_risk`, which is real and
well-sourced (USGS Mineral Commodity Summaries + World Bank governance indicators) but is
computed at GICS Sub-Industry level: 503 companies take 79 distinct values, and within
Financials, 76 companies share 4. So it measures an *industry's* critical-material exposure,
not a *company's* behaviour. The indicator that would fix this - `ghg_intensity`, tonnes CO2e
per million of revenue, the exact metric ETH's own report leads with - is built and
`in_progress` in our catalog, not `ready`. We would rather show you a pillar with a stated
limitation than a pillar with an invented number. What we are claiming today is the
*machinery* - profile → score → exclusion → weights, with a reason on every line - not that
these three indicators are a finished ESG rating.

**Q2. "What does this cost me in return, and what is my tracking error?"**

We cannot tell you, and anyone who gives you a number from this repo today is guessing. There
are no market capitalisations and no return series in this project - the benchmark in our
allocation plan is equal weight, with a market-cap path already stubbed behind a column
check. That matters more than it sounds: an equal-weighted S&P 500 is itself a large
size-factor bet, probably larger than the sustainability tilt on top of it, so we cannot yet
separate the cost of the screen from the cost of the weighting scheme. What we can tell you
today is the *structural* impact, which is measured, not modelled: the product screen removes
42 of 503 names (8.3% of an equally weighted universe), a sector-neutral bottom-15% cut on
top leaves 392 companies, and `sector_neutral = true` guarantees every sector's weight still
matches the benchmark, so the deviation is a company-selection deviation and not a sector
call. Adding `universe/marketcaps.csv` turns that structural statement into a real active
share and ex-ante tracking error with no change to the allocation code.

And we would rather you press us on this than not, because the question is live: **Princeton
discontinued its oil and gas divestment commitment in June 2026 on exactly these grounds**,
having cut its long-run return assumption from 10.2% to 8% four months earlier. That is why we
ship an exclusion profile and an engagement profile side by side rather than assuming the
answer - the difference between the two outputs is the list of companies the fiduciary
judgement is actually about.

---

## 5. Honest audit: what today's data supports vs. what needs new work

### Supported today, with no new data

| Recommendation | Status |
|---|---|
| `sector_relative = true` as the endowment default | **Works now.** One flag; measured effect above. |
| `min_weight_share = 0.6` | **Works now**, but re-check it: the setting has a cliff (§3.1) and the right value depends on how many indicators are `ready`. 0.7 would drop 29% of the universe today. |
| `environmental = 2` category weighting | **Works now.** |
| `federal_contract_exposure = 0` | **Works now.** |
| `method = "exclude"`, `exclude_bottom_pct`, `sector_neutral`, `max_weight` | **Designed, not built.** The plan in `docs/superpowers/plans/2026-09-12-portfolio-allocation.md` specifies all four with tests; `portfolio/allocate.py` still raises `NotImplementedError`. |
| Product exclusions by GICS Sub-Industry | **One new function.** The `GICS Sub-Industry` column already exists in `universe/raw/sp500_constituents.csv`; it is not currently loaded into `universe/sp500.csv`, which carries only `ticker, name, sector, cik`. |
| Running two profiles (exclude vs. engage) and diffing them | **Works as soon as `allocate()` exists.** No new data. |

### Needs new work, in order of value to this audience

1. **`ghg_intensity` to `ready`** - the metric ETH itself reports. Already written
   (`environmental/scripts/ghg_intensity.py`, EPA GHGRP + SEC XBRL), status `in_progress`.
   Highest value per hour of anything on this list.
2. **Market caps** (`universe/marketcaps.csv`) - unlocks a real benchmark, active share and
   tracking error. Until then every portfolio statement is equal-weight-conditioned.
3. **Revenue by segment / fossil-fuel revenue share** - without it we cannot implement a
   single real exclusion *rule* (1% / 5% / 10% / 30%), only a sub-industry proxy that
   over-excludes diversified firms and misses segment exposure inside conglomerates.
4. **UN Global Compact / OECD norms screen** - required by all three of ETH's managers and by
   EU PAB Art. 12(c); we have nothing. Commercial feeds are paid; an open proxy would be a
   real contribution and is the most interesting unsolved problem here.
5. **SBTi validated-target flag** - openly published, binary, and maps directly to the Swiss
   Climate Scores' forward-looking group. The cheapest genuinely new indicator for this audience.
6. **Year alignment** - `common/score.py` uses each company's latest available year, so
   companies are compared across different years. A dated fund report needs this resolved
   (already an open question in `docs/SCORING.md`).

### Explicitly not supported - do not claim these

- Any statement about the **ETH Zürich Foundation's** investment policy beyond "it publishes
  no exclusion list, managers, AUM or PRI status" (§1.4).
- Any claim that the ETH Board's **Anlagerichtlinien** cover ETH's federal operating funds -
  they explicitly do not (§1.0); they govern *andere Mittel*, the donated money.
- Any claim that ETH's **net-zero-by-2030** target applies to its **portfolio** (§1.3 - it is
  an operational target in the sources I found).
- PRI signatory status or TCFD reporting for ETH Zürich or the Foundation (§1.1, §1.5 - not found).
- Any return, tracking error, backtest or "cost of the screen" figure.
- Any coal, weapons or tobacco exclusion described as a **revenue-threshold** rule. Ours is a
  sub-industry classification, and the difference is exactly the kind of thing this audience
  checks.

### Sources, collected

ETH Zürich: [Anlagerichtlinien des ETH-Rats, 14.07.2021 (the legal basis)](https://ethz.ch/content/dam/ethz/main/eth-zurich/organisation/rechtssammlung/120.4.pdf) ·
[Nachhaltigkeitsbericht 2025 Finanzmittel](https://ethz.ch/content/dam/ethz/associates/services/finance-and-controlling/open/Nachhaltigkeitsbericht_2025_Finanzmittel_ETH_Zuerich.pdf) ·
[2024 edition](https://ethz.ch/content/dam/ethz/associates/services/finance-and-controlling/open/Nachhaltigkeitsbericht_2024_Finanzmittel_ETH_Zuerich.pdf) ·
[Net Zero](https://ethz.ch/en/the-eth-zurich/sustainability/net-zero.html) ·
[Net Zero white paper 2022](https://ethz.ch/content/dam/ethz/main/eth-zurich/nachhaltigkeit/05_netzero/ETH-Whitepaper_Nettonull_EN_Sept22_final.pdf) ·
[ETH Zürich Foundation](https://ethz-foundation.ch/en/foundation/)

EPFL: [Socially Responsible Investment Charter v1.0, 05.12.2023](https://www.epfl.ch/about/vice-presidencies/wp-content/uploads/2024/04/ChartePlacementResponsable_2023_newDesign_EN.pdf) ·
[EPFL SRI policy page](https://www.epfl.ch/about/vice-presidencies/vice-presidency-for-finances-vpf/planning-treasury-and-institutional-data-department/socially-responsible-investing-policy/)

Switzerland: [SVVK-ASIR exclusion list](https://svvk-asir.ch/en/exclusion-list) ·
[SVVK-ASIR controversial weapons](https://svvk-asir.ch/en/activities/controversial-weapons) ·
[Swiss Climate Scores (SIF)](https://www.sif.admin.ch/en/swiss-climate-scores-en) ·
[Federal Council, 8 Dec 2023](https://www.admin.ch/gov/en/start/documentation/media-releases.msg-id-99293.html) ·
[SSF Swiss Climate Scores](https://www.sustainablefinance.ch/en/resources/climate-finance/swiss-climate-scores.html)

EU: [Delegated Regulation (EU) 2020/1818](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32020R1818)

Peers: [Cambridge](https://www.cam.ac.uk/news/cambridge-to-divest-from-fossil-fuels-with-net-zero-plan) ·
[Cambridge Council statement 01.10.2020](https://www.cam.ac.uk/notices/news/council-statement-1-october-2020) ·
[OUem investment restrictions](https://www.ouem.co.uk/restrictions/) ·
[HMC 2024 Climate Report](https://www.hmc.harvard.edu/wp-content/uploads/2024/04/2024-Climate-Report.pdf) ·
[MIT Plan for Action on Climate Change 2015](https://web.mit.edu/climateaction/ClimateChangeStatement-2015Oct21.pdf) ·
[PRINCO, Update on Net-Zero Endowment Goal (2026)](https://princo.princeton.edu/update-on-net-zero-endowment-goal/) ·
[Princeton Alumni Weekly on the reversal](https://paw.princeton.edu/article/princeton-reverses-course-fossil-fuel-divestment) ·
[Daily Princetonian on the reversal](https://www.dailyprincetonian.com/article/2026/06/princeton-news-adpol-princo-discontinues-divestment-publicly-traded-oil-gas-companies) ·
[Oxford](https://www.ox.ac.uk/news/2020-04-27-oxford-announces-historic-commitment-fossil-fuel-divestment) ·
[Harvard Gazette](https://news.harvard.edu/gazette/story/2020/04/harvard-endowment-to-go-greenhouse-gas-neutral-by-2050/) ·
[HMC 2021 Climate Report](https://www.hmc.harvard.edu/wp-content/uploads/2021/02/2021-Climate-Report.pdf) ·
[Princeton](https://www.princeton.edu/news/2022/09/29/princeton-dissociates-segments-fossil-fuel-industry) ·
[Princeton dissociation list](https://fossilfueldissociation.princeton.edu/) ·
[Yale](https://news.yale.edu/2021/04/16/new-principles-regarding-fossil-fuels-guide-yales-endowment) ·
[Yale ACIR](https://acir.yale.edu/implementation-fossil-fuel-investment-principles)

Benchmarks/surveys: [GPFG Interim Ethical Guidelines, 07.11.2025](https://www.regjeringen.no/en/documents/interim-ethical-guidelines-for-the-government-pension-fund-global/id3138527/) ·
[Norges Bank exclusions](https://www.nbim.no/en/responsible-investment/exclusion-of-companies/) ·
[Council on Ethics](https://etikkradet.no/en/) ·
[Norwegian product-based criteria](https://www.regjeringen.no/en/documents/annual-report-2023/id3029746/?ch=4) ·
[NCSE FY24 highlights](https://www.commonfund.org/blog/ncse-key-highlights-infographic-fy24) ·
[NACUBO 2024 study](https://www.nacubo.org/Events/2025/ELS25-Results-From-the-2024-NACUBO-Commonfund-Study-of-Endowments) ·
[PNC on the 2025 study](https://www.pnc.com/insights/corporate-institutional/manage-nonprofit-enterprises/key-takeaways-from-the-nacubo-study.html)

### Reproducing the repo numbers in this document

```bash
/venvs/python_general/bin/python -c "
import pandas as pd
from common.score import load_dataset, Profile, score_profile
d = load_dataset()
u = pd.read_csv('universe/raw/sp500_constituents.csv').rename(columns={'Symbol':'ticker'})[['ticker','GICS Sub-Industry']]
PROD = 'Tobacco|Aerospace & Defense|Oil & Gas|Integrated Oil|Casinos & Gaming|Brewers|Distillers'
for sr in (False, True):
    t = score_profile(d, Profile(name='x', sector_relative=sr)).table.merge(u, on='ticker')
    ex = t[t['GICS Sub-Industry'].str.contains(PROD)]
    print('sector_relative', sr, '| mean by sector:')
    print(t.groupby('sector').total_score.mean().round(1).to_string())
    print('excluded', len(ex), 'of', len(t), '| surviving a bottom-20% cut:', (ex.position <= len(t)*0.8).sum())
"
```

**Nothing in this document has been implemented.** `profiles/`, `portfolio/`, `common/`,
`universe/`, `dashboard/`, `run.py` and every catalog and indicator are unchanged; this file
is the only thing that was created.
