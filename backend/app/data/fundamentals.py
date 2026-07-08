"""Company fundamentals wrapper around yfinance, defensive against missing fields
(yfinance's .info coverage varies a lot for NSE tickers)."""

from __future__ import annotations

from functools import lru_cache

import pandas as pd
import yfinance as yf


@lru_cache(maxsize=64)
def get_sector(symbol: str) -> str:
    """Cached sector lookup - sector doesn't change intraday, and the allocation
    planner's per-sector exposure cap needs this for every open position on every
    trade decision, not just the symbol currently under analysis."""
    ticker = yf.Ticker(symbol)
    try:
        return ticker.info.get("sector") or "Unknown"
    except Exception:
        return "Unknown"


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


def _row(df: pd.DataFrame, label: str, col: int = 0) -> float | None:
    try:
        if label not in df.index or col >= len(df.columns):
            return None
        val = df.loc[label].iloc[col]
        return None if pd.isna(val) else float(val)
    except Exception:
        return None


def get_financial_statements(symbol: str) -> dict:
    """Annual income statement / balance sheet / cash flow, reshaped into the
    nested schema the team-contributed fundamental_analyst_agent expects.
    Fields yfinance doesn't provide (revenue quality/recurring-revenue
    disclosures, audit status, filing metadata) are left absent - that
    agent's own confidence-capping logic already degrades gracefully for
    exactly this kind of partial data rather than requiring it."""
    ticker = yf.Ticker(symbol)
    try:
        fin, bs, cf = ticker.financials, ticker.balance_sheet, ticker.cashflow
    except Exception:
        return {}
    if fin.empty or bs.empty:
        return {}

    revenue = _row(fin, "Total Revenue", 0)
    cash = _row(bs, "Cash And Cash Equivalents", 0)
    operating_cash_flow = _row(cf, "Operating Cash Flow", 0)

    filing_date = None
    try:
        filing_date = str(fin.columns[0].date())
    except Exception:
        pass

    return {
        "company_name": symbol,
        "ticker": symbol,
        "reporting_period": filing_date or "Unknown Period",
        "filing_date": filing_date or "",
        "income_statement": {
            "revenue": revenue,
            "revenue_prior_year": _row(fin, "Total Revenue", 1),
            "revenue_two_years_ago": _row(fin, "Total Revenue", 2),
            "gross_profit": _row(fin, "Gross Profit", 0),
            "operating_income": _row(fin, "Operating Income", 0),
            "net_income": _row(fin, "Net Income", 0),
        },
        "balance_sheet": {
            "cash_and_equivalents": cash,
            "current_assets": _row(bs, "Current Assets", 0),
            "current_liabilities": _row(bs, "Current Liabilities", 0),
            "total_debt": _row(bs, "Total Debt", 0),
            "short_term_debt": _row(bs, "Current Debt", 0),
            "shareholders_equity": _row(bs, "Stockholders Equity", 0),
            "goodwill_and_intangibles": _row(bs, "Goodwill And Other Intangible Assets", 0),
            "accounts_receivable": _row(bs, "Accounts Receivable", 0),
            "accounts_receivable_prior_year": _row(bs, "Accounts Receivable", 1),
            "inventory": _row(bs, "Inventory", 0),
            "inventory_prior_year": _row(bs, "Inventory", 1),
        },
        "cash_flow_statement": {
            "operating_cash_flow": operating_cash_flow,
            "free_cash_flow": _row(cf, "Free Cash Flow", 0),
        },
        "capital_allocation": {
            "shares_outstanding": _row(bs, "Ordinary Shares Number", 0),
            "shares_outstanding_prior_year": _row(bs, "Ordinary Shares Number", 1),
        },
        "data_notes": {
            "statement_coverage": "three_primary_statements" if all([revenue, cash, operating_cash_flow]) else "income_and_balance_sheet",
        },
    }
