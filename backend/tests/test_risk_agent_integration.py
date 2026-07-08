"""Tests for the vendored team risk_agent package and its integration into
our RiskAnalyst - no network, no LLM key required."""

import numpy as np
import pandas as pd

from app.agents.analysts.risk import RiskAnalyst
from app.agents.base import AnalysisContext
from risk_agent import OHLCVBar, PortfolioPosition, RiskAssessmentAgent, RiskAssessmentInput


def _synthetic_bars(n=80, start=1000.0, seed=1, vol=0.01) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, vol, n)
    closes = start * np.cumprod(1 + returns)
    idx = pd.date_range("2026-07-08 09:15", periods=n, freq="5min")
    return pd.DataFrame(
        {
            "Open": closes * (1 - 0.001),
            "High": closes * (1 + 0.003),
            "Low": closes * (1 - 0.003),
            "Close": closes,
            "Volume": rng.integers(50_000, 200_000, n),
        },
        index=idx,
    )


def test_vendored_agent_runs_standalone():
    agent = RiskAssessmentAgent()
    request = RiskAssessmentInput(
        symbol="TEST.NS",
        price_data=[OHLCVBar(date=f"2026-07-0{i%9+1}", open=100, high=102, low=99, close=100 + i, volume=10_000) for i in range(10)],
        benchmark_data=[OHLCVBar(date=f"2026-07-0{i%9+1}", open=1000, high=1010, low=990, close=1000 + i * 2, volume=100_000) for i in range(10)],
        portfolio=[PortfolioPosition(symbol="TEST.NS", weight=0.3, sector="IT")],
    )
    result = agent.assess(request, store_decision=False)
    assert result.recommendation in ("BUY", "HOLD", "SELL")
    assert 0 <= result.risk_score <= 100
    assert result.risk_level in ("LOW", "MEDIUM", "HIGH", "EXTREME")


def test_risk_analyst_blends_without_metric_collision():
    ctx = AnalysisContext(
        symbol="RELIANCE.NS",
        bars=_synthetic_bars(vol=0.003),
        fundamentals={"sector": "Energy"},
        symbol_news=[],
        market_news=[],
        daily_bars=_synthetic_bars(vol=0.015, seed=3),
        benchmark_bars=_synthetic_bars(vol=0.012, seed=2),
        open_positions=[{"symbol": "RELIANCE.NS", "weight": 5000.0, "sector": "Energy"}],
    )

    vote = RiskAnalyst().vote(ctx)

    assert vote.agent_name == "Risk Assessment Analyst"
    assert vote.action in ("BUY", "SELL", "HOLD", "WAIT")
    # Our own per-bar volatility must stay small (this feeds position sizing / scenario analysis directly)
    assert vote.metrics["volatility"] < 0.5
    # The team model's richer (annualized, much larger scale) numbers must live in their own namespace
    assert "advanced" in vote.metrics
    assert vote.metrics["advanced"]["volatility"] >= vote.metrics["volatility"]
    assert vote.metrics["risk_level"] in ("LOW", "MEDIUM", "HIGH")  # collapsed 3-tier, never EXTREME here


def test_risk_analyst_degrades_gracefully_without_benchmark():
    ctx = AnalysisContext(
        symbol="TCS.NS",
        bars=_synthetic_bars(),
        fundamentals={},
        symbol_news=[],
        market_news=[],
        benchmark_bars=None,
        open_positions=[],
    )
    vote = RiskAnalyst().vote(ctx)
    assert vote.action in ("BUY", "SELL", "HOLD", "WAIT")
    assert "advanced" not in vote.metrics
    assert any("skipped" in e for e in vote.evidence)
