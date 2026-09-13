"""How today's fund would have moved against its benchmark - ex-ante risk from past prices.

    from portfolio.risk import risk_report
    risk_report(portfolio)   # portfolio = allocate() output (ticker, weight, benchmark_weight)

What it is: TODAY's weights applied to the last `months` of monthly total returns
(portfolio/raw/prices_monthly.csv, dividend- and split-adjusted closes). That is the
standard ex-ante view of risk - tracking error, volatility, how closely the fund follows
the index. What it is NOT: a backtest. The weights come from today's scores, which were
not known in the past (look-ahead), and only today's S&P 500 members are in it
(survivorship). Returns shown are therefore hypothetical and labelled so.

A holding without a return in a month is left out of that month and the other weights are
re-scaled; `covered_weight` says how much of the fund had a full price history.
Deterministic, no model calls.
"""

from __future__ import annotations

import math

import pandas as pd

WINDOW_MONTHS = 36


def _series(returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    w = weights[weights > 0]
    cols = [t for t in w.index if t in returns.columns]
    r = returns[cols]
    live = r.notna().mul(w[cols], axis=1)
    return r.fillna(0).mul(w[cols], axis=1).sum(axis=1) / live.sum(axis=1)


def _stats(r: pd.Series) -> dict:
    growth = (1 + r).cumprod()
    years = len(r) / 12
    return {
        "annual_return": float(growth.iloc[-1] ** (1 / years) - 1) if years else None,
        "volatility": float(r.std(ddof=1) * math.sqrt(12)),
        "max_drawdown": float((growth / growth.cummax() - 1).min()),
        "total_return": float(growth.iloc[-1] - 1),
    }


def risk_report(portfolio: pd.DataFrame, months: int = WINDOW_MONTHS) -> dict | None:
    """None when no price data exists (run `python portfolio/marketdata.py`)."""
    from portfolio.marketdata import MarketData

    md = MarketData.load()
    if md is None:
        return None
    adj = md.adjclose.sort_index()
    returns = adj.pct_change(fill_method=None).iloc[1:].tail(months)
    if len(returns) < 12:
        return None
    p = portfolio.set_index("ticker")
    fund_w, bench_w = p["weight"].astype(float), p["benchmark_weight"].astype(float)
    full = returns.notna().all()
    covered = float(fund_w[[t for t in fund_w.index if full.get(t, False)]].sum())

    fund, bench = _series(returns, fund_w), _series(returns, bench_w)
    active = fund - bench
    growth = pd.DataFrame({"fund": (1 + fund).cumprod(), "benchmark": (1 + bench).cumprod()})
    return {
        "months": int(len(returns)),
        "from": str(returns.index[0]),
        "to": str(returns.index[-1]),
        "fund": _stats(fund),
        "benchmark": _stats(bench),
        "tracking_error": float(active.std(ddof=1) * math.sqrt(12)),
        "correlation": float(fund.corr(bench)),
        "covered_weight": covered,
        "growth": [{"month": m, "fund": float(r["fund"]), "benchmark": float(r["benchmark"])} for m, r in growth.iterrows()],
        "caveat": "today's weights on past monthly returns - hypothetical, not a backtest (look-ahead, today's members only)",
    }
