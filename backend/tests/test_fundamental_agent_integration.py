"""Tests for the vendored team fundamental_analyst_agent and its integration
into our FundamentalAnalyst - no network, no LLM key required."""

import pandas as pd

from app.agents.analysts.fundamental import FundamentalAnalyst, _team_signal
from app.agents.base import AnalysisContext
from fundamental_analyst_agent import analyze as analyze_statements

_GOOD_STATEMENTS = {
    "company_name": "TEST", "ticker": "TEST.NS", "reporting_period": "2026-03-31", "filing_date": "2026-03-31",
    "income_statement": {
        "revenue": 1_000_000, "revenue_prior_year": 800_000, "revenue_two_years_ago": 650_000,
        "gross_profit": 400_000, "operating_income": 200_000, "net_income": 150_000,
    },
    "balance_sheet": {
        "cash_and_equivalents": 300_000, "current_assets": 500_000, "current_liabilities": 200_000,
        "total_debt": 100_000, "short_term_debt": 20_000, "shareholders_equity": 600_000,
        "goodwill_and_intangibles": 50_000, "accounts_receivable": 80_000, "accounts_receivable_prior_year": 70_000,
        "inventory": 60_000, "inventory_prior_year": 55_000,
    },
    "cash_flow_statement": {"operating_cash_flow": 180_000, "free_cash_flow": 120_000},
    "capital_allocation": {"shares_outstanding": 1_000_000, "shares_outstanding_prior_year": 1_000_000},
    "data_notes": {"statement_coverage": "three_primary_statements"},
}


def _synthetic_bars(n=40, start=1000.0) -> pd.DataFrame:
    idx = pd.date_range("2026-07-08 09:15", periods=n, freq="5min")
    closes = [start + i for i in range(n)]
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": [10000] * n}, index=idx)


def test_vendored_agent_runs_standalone():
    result = analyze_statements(_GOOD_STATEMENTS)
    assert result["final_view"] in (
        "Fundamentally Excellent", "Fundamentally Strong", "Fundamentally Mixed",
        "Fundamentally Weak", "Financially Distressed", "Insufficient Data",
    )
    assert 0 <= result["composite_fundamental_quality_score"] <= 100


def test_team_signal_maps_strong_company_to_buy():
    signal = _team_signal(_GOOD_STATEMENTS)
    assert signal is not None
    assert signal["action"] in ("BUY", "HOLD")  # healthy synthetic company should not read as a sell
    assert "composite_quality_score" in signal["metrics"]


def test_team_signal_none_without_revenue():
    assert _team_signal({}) is None
    assert _team_signal({"income_statement": {}}) is None


def test_fundamental_analyst_uses_team_model_when_available():
    ctx = AnalysisContext(
        symbol="TEST.NS", bars=_synthetic_bars(), fundamentals={}, symbol_news=[], market_news=[],
        financial_statements=_GOOD_STATEMENTS,
    )
    vote = FundamentalAnalyst().vote(ctx)
    assert vote.agent_name == "Fundamental Analyst"
    assert "composite_quality_score" in vote.metrics


def test_fundamental_analyst_falls_back_without_statements():
    ctx = AnalysisContext(
        symbol="TEST.NS", bars=_synthetic_bars(), fundamentals={"pe_ratio": 20, "revenue_growth": 0.1},
        symbol_news=[], market_news=[], financial_statements={},
    )
    vote = FundamentalAnalyst().vote(ctx)
    assert "composite_quality_score" not in vote.metrics
    assert any("lighter valuation model" in e for e in vote.evidence)
