"""Company fundamentals wrapper around yfinance, defensive against missing fields
(yfinance's .info coverage varies a lot for NSE tickers)."""

from __future__ import annotations

import yfinance as yf


def get_fundamentals(symbol: str) -> dict:
    ticker = yf.Ticker(symbol)
    try:
        info = ticker.info
    except Exception:
        info = {}

    def g(key, default=None):
        val = info.get(key, default)
        return val if val is not None else default

    return {
        "symbol": symbol,
        "short_name": g("shortName", symbol),
        "sector": g("sector", "Unknown"),
        "industry": g("industry", "Unknown"),
        "pe_ratio": g("trailingPE"),
        "forward_pe": g("forwardPE"),
        "eps": g("trailingEps"),
        "market_cap": g("marketCap"),
        "revenue_growth": g("revenueGrowth"),
        "profit_margins": g("profitMargins"),
        "debt_to_equity": g("debtToEquity"),
        "return_on_equity": g("returnOnEquity"),
        "dividend_yield": g("dividendYield"),
        "beta": g("beta"),
        "fifty_two_week_high": g("fiftyTwoWeekHigh"),
        "fifty_two_week_low": g("fiftyTwoWeekLow"),
    }
