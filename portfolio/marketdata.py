"""Market data for a market-cap benchmark: shares outstanding (SEC) x month-end price (Yahoo).

    python portfolio/marketdata.py            download what is missing (cached), rebuild the CSVs
    python portfolio/marketdata.py --offline  rebuild the CSVs from the caches only

Why: the real S&P 500 is weighted by market capitalisation; equal weight gives a
$15 bn company the same weight as a $4 tn one. Market cap = shares outstanding x price.

Sources (free, public, no key):
- Shares outstanding, SEC XBRL frames API, tag dei:EntityCommonStockSharesOutstanding
  (the share count on the cover page of every 10-K / 10-Q), one file per calendar
  quarter for all filers: https://data.sec.gov/api/xbrl/frames/dei/EntityCommonStockSharesOutstanding/shares/CY2026Q2I.json
- Companies with several share classes tag that count per class, which the frames API
  leaves out. For them we read the cover page of the filing itself (R1.htm, e.g.
  https://www.sec.gov/Archives/edgar/data/1652044/000165204426000071/R1.htm): one share
  count and one trading symbol per class. The filing is the company's latest 10-K/10-Q in
  the us-gaap:Assets frame of that quarter. Classes WITHOUT a trading symbol (e.g. Meta
  class B, Alphabet class B) are not listed, so they are not counted - the same convention
  as S&P, which only counts listed share lines.
- Prices, Yahoo Finance chart API, monthly bars (close = split-adjusted month-end close,
  adjclose = split- and dividend-adjusted, used for returns), plus split events:
  https://query1.finance.yahoo.com/v8/finance/chart/AAPL?interval=1mo&events=div,split
  Human-readable: https://finance.yahoo.com/quote/AAPL/history

Market cap of a company at a month end D = sum over its listed share lines of
shares (latest count dated <= D, at most MAX_SHARE_AGE_DAYS old) x close at D x every split
ratio after the share count's date (Yahoo back-adjusts old closes for later splits; the SEC
count is as reported on its date). Not float-adjusted (S&P is) - a known limit.
A company without a share count or a price at D has NO market cap - it is left out of the
benchmark, never filled in with an estimate.

Outputs (small, committed; the raw caches are gitignored):
    portfolio/raw/shares_outstanding.csv   cik, symbol, as_of, shares, source, source_url, note
    portfolio/raw/prices_monthly.csv       symbol, month, close, adjclose
    portfolio/raw/splits.csv               symbol, date, ratio
"""

from __future__ import annotations

import calendar
import datetime as dt
import html
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import requests  # noqa: E402

from common.config import ROOT, UNIVERSE_CSV  # noqa: E402

AREA = "portfolio"
RAW = ROOT / "portfolio" / "raw"
SHARES_CSV = RAW / "shares_outstanding.csv"
PRICES_CSV = RAW / "prices_monthly.csv"
SPLITS_CSV = RAW / "splits.csv"

FIRST_YEAR = 2018  # share counts from 2018 Q3, prices from 2018-12 (backtest starts 2019-06)
PRICE_START = dt.datetime(2018, 12, 1, tzinfo=dt.timezone.utc)
MAX_SHARE_AGE_DAYS = 400  # a share count older than ~1 year + filing lag is too stale

FRAMES_SHARES_URL = "https://data.sec.gov/api/xbrl/frames/dei/EntityCommonStockSharesOutstanding/shares/{q}.json"
FRAMES_ASSETS_URL = "https://data.sec.gov/api/xbrl/frames/us-gaap/Assets/USD/{q}.json"
COVER_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn_nodash}/R1.htm"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_PAGE = "https://finance.yahoo.com/quote/{symbol}/history"
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}

SRC_FRAMES = "SEC XBRL frames dei:EntityCommonStockSharesOutstanding"
SRC_COVER = "SEC filing cover page (R1.htm), per listed share class"


# ---------------------------------------------------------------- helpers
def yahoo_symbol(symbol: str) -> str:
    """BRK.B -> BRK-B (Yahoo's spelling of class suffixes)."""
    return symbol.strip().upper().replace(".", "-").replace("/", "-")


def quarters(first_year: int, today: dt.date) -> list[str]:
    """Calendar-quarter instant frame names from FIRST_YEAR Q3 to the current quarter, newest first."""
    out = []
    for y in range(first_year, today.year + 1):
        for q in range(1, 5):
            if (y, q) < (first_year, 3) or dt.date(y, 3 * q - 2, 1) > today:
                continue
            out.append(f"CY{y}Q{q}I")
    return out[::-1]


def month_end(month: str) -> dt.date:
    y, m = int(month[:4]), int(month[5:7])
    return dt.date(y, m, calendar.monthrange(y, m)[1])


def _get(url: str, headers: dict | None = None, tries: int = 4) -> bytes:
    from common.io import http_headers

    for attempt in range(tries):
        resp = requests.get(url, headers={**http_headers(), **(headers or {})}, timeout=120)
        if resp.status_code in (429, 500, 502, 503) and attempt < tries - 1:
            time.sleep(5 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.content
    raise RuntimeError(f"gave up on {url}")


def cached(url: str, filename: str, offline: bool, headers: dict | None = None) -> Path | None:
    """common.io.cached_download with retries on rate limits; None if offline and not cached."""
    from common.io import cached_download

    path = RAW / filename
    if path.exists():
        return path
    if offline:
        return None
    for attempt in range(4):
        try:
            return cached_download(url, AREA, filename, headers=headers, pause_s=0.15)
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            if code == 404:
                return None
            if code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(10 * (attempt + 1))
                continue
            raise
    return None


# ---------------------------------------------------------------- SEC share counts
def parse_cover(text: str) -> list[dict]:
    """Listed share classes on a cover page: [{symbol, shares, as_of}] (shares already scaled).
    Rows are grouped by the class member header rows ("rh"); the document-level block has
    no member. A class needs both a share count and a trading symbol to count."""
    header = re.search(r"<th[^>]*class=\"tl\"[^>]*>(.*?)</th>", text, re.S)
    head_txt = html.unescape(re.sub(r"<[^>]+>", " ", header.group(1))).lower() if header else ""
    scale = 1_000_000 if "in millions" in head_txt else 1_000 if "in thousands" in head_txt else 1
    dates = []
    for th in re.findall(r"<th class=\"th\"[^>]*><div>(.*?)</div></th>", text, re.S):
        try:
            dates.append(dt.datetime.strptime(re.sub(r"\s+", " ", html.unescape(th)).strip(), "%b. %d, %Y").date())
        except ValueError:
            try:
                dates.append(dt.datetime.strptime(re.sub(r"\s+", " ", html.unescape(th)).strip(), "%b %d, %Y").date())
            except ValueError:
                dates.append(None)

    sections: dict[str, dict] = {}
    current = "(document)"
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
        cls_row = row
        label_m = re.search(r"defref_([^']+)'", cls_row)
        if not label_m:
            continue
        ref = label_m.group(1)
        cells = re.findall(r"<td class=\"(?:nump|text|num)\"[^>]*>(.*?)</td>", row, re.S)
        values = [html.unescape(re.sub(r"<[^>]+>", "", c)).replace("\xa0", " ").strip() for c in cells]
        if "Axis=" in ref:
            current = ref.split("Axis=", 1)[1]
            continue
        sec = sections.setdefault(current, {})
        if ref == "dei_TradingSymbol":
            sym = next((v for v in values if v), "")
            if sym and sym.lower() not in ("none", "n/a"):
                sec["symbol"] = sym.upper()
        elif ref == "dei_EntityCommonStockSharesOutstanding":
            for i, v in enumerate(values):
                num = re.sub(r"[,$\s]", "", v)
                if re.fullmatch(r"\d+(\.\d+)?", num):
                    sec["shares"] = float(num) * scale
                    sec["as_of"] = dates[i] if i < len(dates) else None
                    break
    out = []
    for member, sec in sections.items():
        if "shares" in sec and sec.get("symbol"):
            out.append({"member": member, "symbol": sec["symbol"], "shares": sec["shares"], "as_of": sec["as_of"]})
    return out


def build_shares(universe: pd.DataFrame, today: dt.date, offline: bool) -> pd.DataFrame:
    ciks = {int(c): t for c, t in universe.groupby(universe["cik"].astype(int))["ticker"].apply(list).items()}
    rows = []
    qs = quarters(FIRST_YEAR, today)
    for q in qs:
        path = cached(FRAMES_SHARES_URL.format(q=q), f"sec_frames/dei_EntityCommonStockSharesOutstanding_{q}.json", offline)
        if path is None:
            print(f"  (no frame {q})")
            continue
        for r in json.loads(path.read_text(encoding="utf-8"))["data"]:
            tickers = ciks.get(r["cik"])
            if not tickers:
                continue
            if len(tickers) > 1:  # a total over several listed classes cannot be priced with one ticker
                continue
            rows.append({
                "cik": f"{r['cik']:010d}", "symbol": tickers[0], "as_of": r["end"], "shares": float(r["val"]),
                "source": SRC_FRAMES, "source_url": FRAMES_SHARES_URL.format(q=q), "note": f"accn {r['accn']}, frame {q}",
            })
    frames = pd.DataFrame(rows)
    print(f"  frames: {len(frames)} share counts for {frames['cik'].nunique()} companies")

    # companies with share classes: cover pages of the filings in the Assets frames
    # (Q1 of each year feeds the June rebalance, plus the latest quarters for today)
    need_dates = [dt.date(y, 6, 30) for y in range(FIRST_YEAR + 1, today.year + 1)] + [today]
    have = frames.assign(as_of=pd.to_datetime(frames["as_of"]).dt.date) if len(frames) else frames
    cover_rows = []
    for cik_int, tickers in ciks.items():
        cik = f"{cik_int:010d}"
        mine = have[have["cik"] == cik]["as_of"].tolist() if len(have) else []
        missing_dates = [d for d in need_dates if not any(0 <= (d - a).days <= MAX_SHARE_AGE_DAYS for a in mine)]
        if not missing_dates:
            continue
        cover_rows.append((cik_int, tickers, missing_dates))
    print(f"  {len(cover_rows)} companies need cover pages (share classes or missing in frames)")

    assets_q = [q for q in qs if q.endswith("Q1I") or q in qs[:3]]
    accns: dict[int, list[tuple[str, str]]] = {}
    for q in assets_q:
        path = cached(FRAMES_ASSETS_URL.format(q=q), f"sec_frames/us-gaap_Assets_{q}.json", offline)
        if path is None:
            continue
        for r in json.loads(path.read_text(encoding="utf-8"))["data"]:
            if r["cik"] in ciks:
                accns.setdefault(r["cik"], []).append((q, r["accn"]))

    out = []
    for cik_int, tickers, missing_dates in cover_rows:
        cik = f"{cik_int:010d}"
        for q, accn in sorted(set(accns.get(cik_int, [])), reverse=True):
            url = COVER_URL.format(cik=cik_int, accn_nodash=accn.replace("-", ""))
            path = cached(url, f"sec_cover/R1_{cik}_{accn}.htm", offline)
            if path is None:
                continue
            for c in parse_cover(path.read_text(encoding="utf-8", errors="replace")):
                if c["as_of"] is None:
                    continue
                out.append({
                    "cik": cik, "symbol": c["symbol"], "as_of": c["as_of"].isoformat(), "shares": c["shares"],
                    "source": SRC_COVER, "source_url": url, "note": f"accn {accn}, class {c['member']}",
                })
    covers = pd.DataFrame(out)
    if len(covers):
        print(f"  covers: {len(covers)} share counts for {covers['cik'].nunique()} companies")
    shares = pd.concat([frames, covers], ignore_index=True)
    return shares.drop_duplicates(["cik", "symbol", "as_of", "source"]).sort_values(["cik", "as_of", "symbol"])


# ---------------------------------------------------------------- Yahoo prices
def build_prices(symbols: list[str], today: dt.date, offline: bool) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    period2 = int(dt.datetime.combine(today, dt.time(), tzinfo=dt.timezone.utc).timestamp())
    prices, splits, failed = [], [], []
    for i, symbol in enumerate(sorted(set(symbols))):
        ys = yahoo_symbol(symbol)
        url = f"{YAHOO_URL.format(symbol=ys)}?period1={int(PRICE_START.timestamp())}&period2={period2}&interval=1mo&events=div%2Csplit"
        try:
            path = cached(url, f"yahoo/{ys}.json", offline, headers=BROWSER_UA)
        except requests.HTTPError as e:
            print(f"  {symbol}: {e}")
            path = None
        if path is None:
            failed.append(symbol)
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        result = (data.get("chart") or {}).get("result") or []
        if not result or not result[0].get("timestamp"):
            failed.append(symbol)
            continue
        r = result[0]
        quote = r["indicators"]["quote"][0]
        adj = (r["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(r["timestamp"])
        for ts, close, a in zip(r["timestamp"], quote.get("close", []), adj):
            if close is None:
                continue
            month = dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m")
            prices.append({"symbol": symbol, "month": month, "close": float(close), "adjclose": float(a) if a is not None else None})
        for ev in ((r.get("events") or {}).get("splits") or {}).values():
            if ev.get("denominator"):
                splits.append({
                    "symbol": symbol,
                    "date": dt.datetime.fromtimestamp(ev["date"], dt.timezone.utc).date().isoformat(),
                    "ratio": float(ev["numerator"]) / float(ev["denominator"]),
                })
        if (i + 1) % 100 == 0:
            print(f"  prices: {i + 1} symbols")
    p = pd.DataFrame(prices)
    # a month can appear twice (the running month's live bar) - keep the last
    p = p.drop_duplicates(["symbol", "month"], keep="last").sort_values(["symbol", "month"])
    s = pd.DataFrame(splits, columns=["symbol", "date", "ratio"]).drop_duplicates().sort_values(["symbol", "date"])
    return p, s, failed


def build(offline: bool = False) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    universe = pd.read_csv(UNIVERSE_CSV, dtype=str, keep_default_na=False)
    today = dt.date.today()
    shares = build_shares(universe, today, offline)
    shares.to_csv(SHARES_CSV, index=False, lineterminator="\n")
    print(f"  wrote {SHARES_CSV.relative_to(ROOT).as_posix()}: {len(shares)} rows, {shares['cik'].nunique()} companies")

    symbols = sorted(set(universe["ticker"]) | set(shares["symbol"]))
    prices, splits, failed = build_prices(symbols, today, offline)
    # the running month is not a month-end close yet
    prices = prices[prices["month"] < today.strftime("%Y-%m")]
    prices.to_csv(PRICES_CSV, index=False, lineterminator="\n")
    splits.to_csv(SPLITS_CSV, index=False, lineterminator="\n")
    print(f"  wrote {PRICES_CSV.relative_to(ROOT).as_posix()}: {len(prices)} rows, {prices['symbol'].nunique()} symbols, "
          f"months {prices['month'].min()}..{prices['month'].max()}")
    print(f"  wrote {SPLITS_CSV.relative_to(ROOT).as_posix()}: {len(splits)} splits")
    if failed:
        print(f"  no price data for {len(failed)} symbols: {failed}")


# ---------------------------------------------------------------- reading (no network)
class MarketData:
    """The committed CSVs, loaded once. All lookups are exact - nothing is estimated."""

    def __init__(self, shares: pd.DataFrame, prices: pd.DataFrame, splits: pd.DataFrame):
        self.shares = shares.assign(as_of=pd.to_datetime(shares["as_of"]).dt.date, cik=shares["cik"].astype(str).str.zfill(10))
        self.prices = prices
        self.close = prices.pivot(index="month", columns="symbol", values="close").sort_index()
        self.adjclose = prices.pivot(index="month", columns="symbol", values="adjclose").sort_index()
        self.splits = splits.assign(date=pd.to_datetime(splits["date"]).dt.date) if len(splits) else splits

    @classmethod
    def load(cls) -> "MarketData | None":
        if not (SHARES_CSV.exists() and PRICES_CSV.exists()):
            return None
        splits = pd.read_csv(SPLITS_CSV) if SPLITS_CSV.exists() else pd.DataFrame(columns=["symbol", "date", "ratio"])
        return cls(pd.read_csv(SHARES_CSV, dtype={"cik": str, "symbol": str}), pd.read_csv(PRICES_CSV), splits)

    def latest_month(self, universe_tickers: list[str], min_share: float = 0.95) -> str:
        """Most recent month-end with a close for at least `min_share` of the universe."""
        cols = [t for t in universe_tickers if t in self.close.columns]
        counts = self.close[cols].notna().sum(axis=1)
        ok = counts[counts >= min_share * len(universe_tickers)]
        if ok.empty:
            raise ValueError("no month with prices for 95% of the universe")
        return str(ok.index.max())

    def split_factor(self, symbol: str, after: dt.date) -> float:
        if not len(self.splits):
            return 1.0
        s = self.splits[(self.splits["symbol"] == symbol) & (self.splits["date"] > after)]
        return float(s["ratio"].prod()) if len(s) else 1.0

    def caps(self, universe: pd.DataFrame, month: str) -> pd.DataFrame:
        """Market cap per company (CIK) at the close of `month`.
        Returns index cik: cap_usd (NaN = missing), lines, shares_as_of, detail."""
        end = month_end(month)
        closes = self.close.loc[month] if month in self.close.index else pd.Series(dtype=float)
        out = []
        for cik, group in universe.groupby(universe["cik"].astype(str).str.zfill(10)):
            s = self.shares[(self.shares["cik"] == cik) & (self.shares["as_of"] <= end)]
            s = s[[(end - a).days <= MAX_SHARE_AGE_DAYS for a in s["as_of"]]]
            row = {"cik": cik, "cap_usd": float("nan"), "lines": "", "shares_as_of": "", "detail": ""}
            if s.empty:
                row["detail"] = f"no SEC share count dated within {MAX_SHARE_AGE_DAYS} days before {end}"
                out.append(row)
                continue
            # the most recent filing wins; prefer a whole-company frame count over cover lines of the same date
            latest = s[s["as_of"] == s["as_of"].max()]
            if (latest["source"] == SRC_FRAMES).any():
                latest = latest[latest["source"] == SRC_FRAMES].tail(1)
            else:
                latest = latest[latest["source_url"] == latest["source_url"].iloc[-1]]
            cap, parts, missing = 0.0, [], []
            for _, line in latest.iterrows():
                price = closes.get(line["symbol"], float("nan"))
                if pd.isna(price):
                    missing.append(line["symbol"])
                    continue
                factor = self.split_factor(line["symbol"], line["as_of"])
                cap += line["shares"] * price * factor
                parts.append(f"{line['symbol']} {line['shares']:,.0f} sh x {price:,.2f}" + (f" x split {factor:g}" if factor != 1 else ""))
            row["shares_as_of"] = str(latest["as_of"].max())
            row["lines"] = "; ".join(parts)
            if missing:
                row["detail"] = f"no {month} close for {', '.join(missing)}"
            elif cap > 0:
                row["cap_usd"] = cap
                row["detail"] = latest["source"].iloc[0]
            out.append(row)
        return pd.DataFrame(out).set_index("cik")


if __name__ == "__main__":
    build(offline="--offline" in sys.argv)
