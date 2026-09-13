"""Carbon price stress test - the bonus question: the world commits to net zero as fast as possible.

    python portfolio/transition.py [profile]     prints the stress table for a profile's fund

A fast net-zero path means a carbon price. Question per company: how much of its profit would a
carbon bill take? Then, weighted by the fund and by the index: how much of the money sits in
companies whose profit a carbon price would eat?

    profit_at_risk_i(P) = tonnes_i x P / pretax_income_i        clipped to [0, 1]

- tonnes_i: direct (Scope 1) CO2e of the company's US facilities above 25,000 t, latest year,
  EPA GHGRP (environmental/raw/ghg_intensity_raw_ratio.csv, built by ghg_intensity.py).
  0 = no facility above the threshold -> nothing at risk under this test.
- pretax_income_i: income before taxes for the same fiscal year (SEC XBRL companyfacts, the same
  tags and cache as economic/scripts/tax_rate_gap.py). A loss-making emitter counts as 100% at risk.
- P: carbon price in USD per tonne - a scenario input, not data. Reference points: IEA "Net Zero
  by 2050" (2021) assumes USD 130/t in 2030 and USD 250/t in 2050 in advanced economies
  (https://www.iea.org/reports/net-zero-by-2050).

Deliberately simple and stated: no pass-through to customers, no abatement, Scope 1 in the US only
(no Scope 2/3, no foreign plants). An emitter without a pre-tax income on record is left out of the
average and counted in `covered_weight` - nothing is estimated. Deterministic, no model calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from common.config import ROOT

PRICES = [0, 25, 50, 75, 100, 130, 160, 200, 250]
REFERENCE = {"2030": 130, "2050": 250}
IEA_URL = "https://www.iea.org/reports/net-zero-by-2050"
HEAVY = 0.25  # a carbon bill above a quarter of pre-tax profit
FUND_USD = 1e9
ASSUMPTIONS = ("Scope 1 emissions of US facilities above 25,000 t (EPA GHGRP) x carbon price / pre-tax income of the same year (SEC). "
               "No pass-through to customers, no abatement, no Scope 2 or 3, no foreign plants - a first-order exposure, not a forecast.")


def load_exposure(universe: pd.DataFrame) -> pd.DataFrame:
    """ticker -> tonnes, ghg_year, pretax_usd, pretax_url. Tickers without a GHG row are absent."""
    from economic.scripts._headcount import CIK_OVERRIDES
    from economic.scripts._xbrl import annual_usd_facts
    from economic.scripts.tax_rate_gap import PRETAX_INCOME_TAGS

    ghg = pd.read_csv(ROOT / "environmental" / "raw" / "ghg_intensity_raw_ratio.csv")
    ghg = ghg.sort_values("year").groupby("ticker").last()
    cik = universe.set_index("ticker")["cik"].astype(str)
    rows = []
    for ticker, g in ghg.iterrows():
        row = {"ticker": ticker, "tonnes": float(g["co2e_tonnes"]), "ghg_year": int(g["year"]), "pretax_usd": None, "pretax_year": None}
        if row["tonnes"] > 0 and ticker in cik.index:
            c = str(CIK_OVERRIDES.get(ticker, cik[ticker])).zfill(10)
            path = ROOT / "economic" / "raw" / f"companyfacts_{c}.json"
            if path.exists():
                facts = annual_usd_facts(json.loads(path.read_text(encoding="utf-8")), PRETAX_INCOME_TAGS)
                same = facts[facts["year"] == row["ghg_year"]]
                if not same.empty:
                    row["pretax_usd"], row["pretax_year"] = float(same.iloc[-1]["value"]), row["ghg_year"]
                row["pretax_url"] = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c}.json"
        rows.append(row)
    return pd.DataFrame(rows).set_index("ticker")


def profit_at_risk(exposure: pd.DataFrame, price: float) -> pd.Series:
    """Share of pre-tax profit a carbon bill at `price` would take, 0..1; NaN = emitter without income on record."""
    t, p = exposure["tonnes"], exposure["pretax_usd"].astype(float)
    risk = (t * price / p.where(p > 0)).clip(0, 1)
    risk = risk.where(~((t > 0) & (p <= 0)), 1.0 if price > 0 else 0.0)  # a carbon bill on top of a loss: all of it
    return risk.where(t > 0, 0.0)


def _weighted(values: pd.Series, weights: pd.Series) -> tuple[float | None, float]:
    v = values.reindex(weights.index)
    m = v.notna() & (weights > 0)
    covered = float(weights[m].sum() / weights[weights > 0].sum()) if weights[weights > 0].sum() else 0.0
    return (float((v[m] * weights[m]).sum() / weights[m].sum()) if weights[m].sum() else None), covered


def stress(funds: dict[str, pd.Series], exposure: pd.DataFrame, info: pd.DataFrame | None = None, top: int = 10) -> dict:
    """funds: name -> weights by ticker (sum 1). Returns the curve over PRICES and the most exposed holdings."""
    curve, heavy = [], []
    covered = {}
    for price in PRICES:
        risk = profit_at_risk(exposure, price)
        point, hv = {"price": price}, {"price": price}
        for name, w in funds.items():
            point[name], covered[name] = _weighted(risk, w)
            r = risk.reindex(w.index)
            hv[name] = float(w[(r >= HEAVY) & (w > 0)].sum() / w[r.notna() & (w > 0)].sum()) if w[r.notna() & (w > 0)].sum() else None
        curve.append(point)
        heavy.append(hv)

    ref = REFERENCE["2030"]
    risk_ref, risk_end = profit_at_risk(exposure, ref), profit_at_risk(exposure, REFERENCE["2050"])
    exposed = []
    order = pd.DataFrame({"risk": risk_ref, "tonnes": exposure["tonnes"]})
    for t in order[order["risk"] > 0].sort_values(["risk", "tonnes"], ascending=False).index:
        row = {"ticker": t, "tonnes": exposure.at[t, "tonnes"], "year": int(exposure.at[t, "ghg_year"]),
               "pretax_usd": exposure.at[t, "pretax_usd"], "risk_2030": float(risk_ref[t]), "risk_2050": float(risk_end[t]),
               **{f"weight_{n}": float(w.get(t, 0.0)) for n, w in funds.items()}}
        if info is not None and t in info.index:
            row.update(name=info.at[t, "name"], sector=info.at[t, "sector"])
        exposed.append(row)
    held_exposed = [r for r in exposed if r.get(f"weight_{next(iter(funds))}", 0) > 0][:top]
    return {
        "prices": PRICES, "reference": REFERENCE, "reference_url": IEA_URL, "heavy_threshold": HEAVY,
        "curve": curve, "heavy_share": heavy, "covered_weight": covered,
        "most_exposed_held": held_exposed, "emitters": int((exposure["tonnes"] > 0).sum()),
        "emitters_without_income": int(((exposure["tonnes"] > 0) & exposure["pretax_usd"].isna()).sum()),
        "assumptions": ASSUMPTIONS, "first_fund": next(iter(funds)),
    }


def facility_map(portfolio: pd.DataFrame, info: pd.DataFrame, year: int = 2023) -> dict:
    """Every large US facility (EPA GHGRP, > 25 kt) of an S&P 500 company in `year`, with coordinates and
    what the fund does with its owner: excluded / less money (< 0.9x index weight) / about the same /
    more money (> 1.1x). Tonnes are the owner's attributed share (environmental/raw/ghg_intensity_matches.csv),
    coordinates from the EPA facility file. Totals per state for the map's side panel."""
    import glob

    matches = pd.read_csv(ROOT / "environmental" / "raw" / "ghg_intensity_matches.csv")
    matches = matches[(matches["year"] == year) & (matches["attributed_co2e_tonnes"] > 0)]
    rows = []
    for path in glob.glob(str(ROOT / "environmental" / "raw" / f"pub_dim_facility_{year}_*.json")):
        rows += json.loads(Path(path).read_text(encoding="utf-8"))
    facilities = pd.DataFrame(rows)[["facility_id", "latitude", "longitude", "state", "facility_name", "city"]].drop_duplicates("facility_id")
    df = matches.merge(facilities, on="facility_id", how="inner")

    p = portfolio.set_index("ticker")
    other = {c.strip(): t for t, classes in info["other_classes"].items() if classes for c in str(classes).split(",")}
    holding = df["ticker"].map(lambda t: t if t in p.index else other.get(t, t))

    def decision(t: str) -> str:
        if t not in p.index:
            return "same"
        r = p.loc[t]
        if r["status"] == "excluded_policy":
            return "excluded"
        rel = r["weight"] / r["benchmark_weight"] if r["benchmark_weight"] > 0 else 1.0
        return "less" if rel < 0.9 else "more" if rel > 1.1 else "same"

    df = df.assign(holding=holding, decision=holding.map(decision), name=holding.map(lambda t: info["name"].get(t, t)))
    points = [{"lat": round(float(r.latitude), 4), "lon": round(float(r.longitude), 4), "t": round(float(r.attributed_co2e_tonnes)),
               "d": r.decision, "co": r.name, "tk": r.holding, "fac": str(r.facility_name).title(), "st": r.state}
              for r in df.sort_values("attributed_co2e_tonnes", ascending=False).itertuples()]
    by_state = df.pivot_table(index="state", columns="decision", values="attributed_co2e_tonnes", aggfunc="sum", fill_value=0.0)
    for col in ("excluded", "less", "same", "more"):
        if col not in by_state:
            by_state[col] = 0.0
    by_state = by_state.assign(total=by_state.sum(axis=1)).sort_values("total", ascending=False)
    totals = df.groupby("decision")["attributed_co2e_tonnes"].sum()
    return {
        "year": year, "facilities": int(df["facility_id"].nunique()), "companies": int(df["holding"].nunique()),
        "tonnes": float(df["attributed_co2e_tonnes"].sum()), "by_decision": {k: float(v) for k, v in totals.items()},
        "states": [{"state": s, **{k: float(v) for k, v in r.items()}} for s, r in by_state.iterrows()],
        "points": points, "source": "EPA GHGRP facility data (Envirofacts), ownership shares as reported to EPA",
    }


def net_zero_answer(profile_name: str = "net_zero", fund_usd: float = FUND_USD) -> dict:
    """The bonus answer in one object: three funds side by side - the index, the index without
    fossil fuels (exclusion only, tilt 0) and the net-zero fund - with climate numbers, the carbon
    price stress curve, dollars per sector and the largest dollar moves."""
    from common.score import load_dataset, load_profile, score_profile
    from portfolio.allocate import allocate, companies, load_universe, settings_for, summary
    from portfolio.risk import risk_report

    profile = load_profile(profile_name)
    universe = load_universe()
    table = score_profile(load_dataset(), profile).table
    s = settings_for(profile, None, set(universe["sub_industry"]))
    fund = allocate(table, profile, universe)
    exclusion_only = allocate(table, profile, universe, overrides={"tilt_strength": 0.0})
    sm, sm_ex = summary(table, fund, universe), summary(table, exclusion_only, universe)
    info = companies(table, universe).set_index("ticker")

    w = fund.set_index("ticker")["weight"]
    b = fund.set_index("ticker")["benchmark_weight"]
    x = exclusion_only.set_index("ticker")["weight"]
    exposure = load_exposure(universe)
    st = stress({"fund": w, "exclusion": x, "index": b}, exposure, info)

    sec = sm["sector_weights"].rename_axis("sector").reset_index()
    sec = sec.assign(fund_usd=sec["portfolio"] * fund_usd, index_usd=sec["benchmark"] * fund_usd)
    moves = fund.assign(usd=fund["weight"] * fund_usd, index_usd=fund["benchmark_weight"] * fund_usd,
                        change_usd=fund["active_weight"] * fund_usd,
                        name=fund["ticker"].map(info["name"]), sector=fund["ticker"].map(info["sector"]),
                        sub_industry=fund["ticker"].map(info["sub_industry"]), total_score=fund["ticker"].map(info["total_score"]),
                        tonnes=fund["ticker"].map(exposure["tonnes"]))
    moves = moves.merge(pd.DataFrame({"ticker": list(exposure.index), "risk_2030": profit_at_risk(exposure, REFERENCE["2030"]).values}),
                        on="ticker", how="left")
    cols = ["ticker", "name", "sector", "sub_industry", "total_score", "usd", "index_usd", "change_usd", "tonnes", "risk_2030", "status"]
    held = moves[moves["status"] == "held"]
    return {
        "profile": {"id": profile_name, "name": profile.name, "description": profile.description,
                    "category_weights": profile.category_weights, "indicator_weights": profile.indicator_weights},
        "settings": s,
        "fund_usd": fund_usd,
        "funds": {
            "index": {"score": sm["scores"]["total_score"]["benchmark"], "climate": {k: v["benchmark"] for k, v in sm["climate"].items()},
                      "holdings": sm["companies"]},
            "exclusion": {"score": sm_ex["scores"]["total_score"]["portfolio"], "climate": {k: v["portfolio"] for k, v in sm_ex["climate"].items()},
                          "holdings": sm_ex["holdings"]},
            "fund": {"score": sm["scores"]["total_score"]["portfolio"], "climate": {k: v["portfolio"] for k, v in sm["climate"].items()},
                     "holdings": sm["holdings"], "active_share": sm["active_share"]},
        },
        "excluded": [{"ticker": r["ticker"], "name": r["name"], "sub_industry": info.at[r["ticker"], "sub_industry"],
                      "index_usd": r["benchmark_weight"] * fund_usd} for r in sm["excluded"]],
        "stress": st,
        "sectors": sec.to_dict(orient="records"),
        "added": held.sort_values("change_usd", ascending=False).head(10)[cols].to_dict(orient="records"),
        "cut": held.sort_values("change_usd").head(10)[cols].to_dict(orient="records"),
        "risk": risk_report(fund),
        "map": facility_map(fund, info),
    }


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "net_zero"
    a = net_zero_answer(name)
    print(f"profile {name}: {a['funds']['fund']['holdings']} holdings, {len(a['excluded'])} excluded")
    for k in ("index", "exclusion", "fund"):
        f = a["funds"][k]
        print(f"  {k:<10} score {f['score']:.1f}  WACI {f['climate']['waci_tco2e_per_musd']:.1f}  SBTi share {f['climate']['sbti_target_share']:.1%}")
    st = a["stress"]
    print(f"  emitters {st['emitters']}, without pre-tax income {st['emitters_without_income']}, covered weight {st['covered_weight']}")
    print("  price  profit at risk: fund / exclusion / index   |  weight with bill >= 25% of profit: fund / exclusion / index")
    for p, h in zip(st["curve"], st["heavy_share"]):
        print(f"  {p['price']:>5}  {p['fund']:.2%} / {p['exclusion']:.2%} / {p['index']:.2%}   |  {h['fund']:.1%} / {h['exclusion']:.1%} / {h['index']:.1%}")
    print("  most exposed holdings at $130/t:")
    for r in st["most_exposed_held"]:
        print(f"    {r['ticker']:<6} {r.get('name', '')[:28]:<28} {r['tonnes']:>12,.0f} t  risk {r['risk_2030']:.0%} (2050 {r['risk_2050']:.0%})  "
              f"fund {r['weight_fund']:.2%} index {r['weight_index']:.2%}")
