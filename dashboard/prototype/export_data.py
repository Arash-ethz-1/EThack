"""Prototype data export: real indicators, scores via common/score.py (in_progress included).

    python dashboard/prototype/export_data.py dashboard/prototype/data.js   (run from repo root)
"""
import itertools, json, re, sys
import pandas as pd
sys.path.insert(0, ".")
from common import score as S
from common.config import CATEGORIES, catalog_path, indicator_path

cats = []
for c in CATEGORIES:
    cat = pd.read_csv(catalog_path(c), dtype=str, keep_default_na=False).assign(category=c)
    cats.append(cat)
catalog = pd.concat(cats, ignore_index=True)
raw, keep = {}, []
for _, r in catalog.iterrows():
    p = indicator_path(r["category"], r["indicator_id"])
    if not p.exists(): continue
    df = pd.read_csv(p)
    if df.ticker.nunique() < 100: continue
    raw[r["indicator_id"]] = df; keep.append(r.name)
catalog = catalog.loc[keep].reset_index(drop=True)
universe = pd.read_csv("universe/sp500.csv", dtype=str)
vals, yrs, lat = {}, {}, {}
for iid, df in raw.items():
    l = S.latest(df); vals[iid], yrs[iid] = l["value"], l["year"]
    lat[iid] = df.sort_values("year").groupby("ticker").tail(1).set_index("ticker")
values = pd.DataFrame(vals).reindex(universe.ticker); years = pd.DataFrame(yrs).reindex(universe.ticker)
values.index.name = years.index.name = "ticker"
data = S.Dataset(universe[["ticker","name","sector"]], catalog, values, years)

base = S.load_profile("balanced")
res = S.score_profile(data, base)
t = res.table
cik = universe.set_index("ticker")["cik"]

def human_url(iid, tk, row):
    note = str(row["note"]); url = row["source_url"]
    m = re.search(r"accn=(\d{10}-\d{2}-\d{6})", note)
    if m and "companyfacts" in url:
        a = m.group(1); return f"https://www.sec.gov/Archives/edgar/data/{int(cik[tk])}/{a.replace('-','')}/{a}-index.htm", "10-K filing"
    return url, row["source"]

# outliers (IQR rule, latest value) - for badges + histogram
outl = {}
for iid in raw:
    s = values[iid].dropna(); q1, q3 = s.quantile(.25), s.quantile(.75); k = 3*(q3-q1)
    outl[iid] = set(s[(s < q1-k) | (s > q3+k)].index)

companies = []
for _, row in t.iterrows():
    tk = row["ticker"]; inds = []
    for _, ind in catalog.iterrows():
        iid = ind["indicator_id"]
        if tk not in lat[iid].index: continue
        lr = lat[iid].loc[tk]; u, label = human_url(iid, tk, lr)
        rk = res.ranks.at[tk, iid]
        inds.append(dict(id=iid, cat=ind["category"], v=round(float(lr["value"]),4), y=int(lr["year"]),
            pts=None if pd.isna(rk) else round(float(rk)*100), url=u, src=label, note=str(lr["note"])[:160],
            out=tk in outl[iid]))
    f = lambda x: None if pd.isna(x) else float(x)
    companies.append(dict(t=tk, n=row["name"], s=row["sector"], tot=f(row["total_score"]),
        e=f(row["economic_score"]), so=f(row["social_score"]), en=f(row["environmental_score"]), ind=inds))

# weight presets, totals computed by score.py
presets = {}
for w in itertools.product([0,1,2], repeat=3):
    if sum(w)==0: continue
    p = S.Profile(name="x", category_weights=dict(zip(CATEGORIES, w)), min_weight_share=base.min_weight_share)
    r = S.score_profile(data, p).table.set_index("ticker")["total_score"]
    presets["".join(map(str,w))] = [None if pd.isna(r[c["t"]]) else float(r[c["t"]]) for c in companies]

# evidence
ev = {}
rs = values["resource_supply_risk"]; sec = universe.set_index("ticker")["sector"]
ev["sector_strip"] = {s: sorted(round(float(v),4) for v in rs[sec[sec==s].index].dropna()) for s in sorted(sec.unique())}
stab = {}
for iid, df in raw.items():
    w = df.pivot_table(index="ticker", columns="year", values="value")
    rhos = []
    for y in w.columns[1:]:
        if y-1 in w.columns:
            pair = w[[y-1, y]].dropna()
            if len(pair) >= 100: rhos.append((int(y), round(float(pair[y-1].rank().corr(pair[y].rank())),3), len(pair)))
    stab[iid] = rhos
ev["stability"] = stab
ids = list(raw); corr = values[ids].rank().corr(min_periods=50)
ev["corr"] = dict(ids=ids, m=[[None if pd.isna(x) else round(float(x),2) for x in row] for row in corr.values])
tg = raw["tax_rate_gap"]; ly = int(tg.groupby("year").size().loc[lambda s: s>=300].index.max())
tv = tg[tg.year==ly]
q1,q3 = tv.value.quantile(.25), tv.value.quantile(.75); k=3*(q3-q1)
ev["tax_hist"] = dict(year=ly, values=[round(float(x),4) for x in tv.value], lo=round(float(q1-k),4), hi=round(float(q3+k),4),
    out=[dict(t=r.ticker, v=round(float(r.value),4), note=str(r.note)[:120]) for r in tv[(tv.value<q1-k)|(tv.value>q3+k)].sort_values("value").itertuples()])
tot_rows = sum(len(d) for d in raw.values()); with_src = sum(d.source_url.notna().sum() for d in raw.values())
ev["kpi"] = dict(rows=tot_rows, with_src=int(with_src), indicators=len(raw), scored=int(t.total_score.notna().sum()),
    retrieved=max(str(d.retrieved.max()) for d in raw.values()))
emp = pd.read_csv("universe/raw/employees_10k.csv")
ev["emp_example"] = emp[emp.ticker.isin(["AAPL","JNJ","CAT"])].sort_values("year").groupby("ticker").tail(1)[["ticker","year","employees","quote","url"]].to_dict("records")
meta = [dict(id=r.indicator_id, name=r["name"], cat=r.category, unit=r.unit, hib=r.higher_is_better, status=r.status, owner=r.owner, source=r.source) for _, r in catalog.iterrows()]
import math
def clean(o):
    if isinstance(o, float): return None if math.isnan(o) else o
    if isinstance(o, dict): return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if isinstance(o, str) and o == "nan": return ""
    return o
out = dict(meta=meta, companies=companies, presets=presets, ev=ev)
print(json.dumps(ev["kpi"]), {k: len(v) for k,v in ev["sector_strip"].items()}, ev["stability"], ev["corr"], len(ev["tax_hist"]["out"]), ly, file=sys.stderr)
print(t[["ticker","total_score","economic_score","environmental_score"]].head(5).to_string(), file=sys.stderr)
open(sys.argv[1], "w", encoding="utf-8").write("window.DATA=" + json.dumps(clean(out), separators=(",",":"), allow_nan=False) + ";")
