"""Tests for the vendored team technical_analyst_agent package and its
integration into our TechnicalAnalyst - no network, no LLM key required."""

import numpy as np
import pandas as pd

from app.agents.analysts.technical import TechnicalAnalyst
from app.agents.base import AnalysisContext
from technical_analyst_agent import PriceBar, TechnicalAnalystAgent, generate_demo_prices


def _synthetic_bars(n=80, start=1000.0, seed=1, vol=0.01) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, vol, n)
    closes = start * np.cumprod(1 + returns)
    idx = pd.date_range("2026-07-08 09:15", periods=n, freq="5min")
    return pd.DataFrame(
        {
            "Open": closes * (1 - 0.001), "High": closes * (1 + 0.003), "Low": closes * (1 - 0.003),
            "Close": closes, "Volume": rng.integers(50_000, 200_000, n),
        },
        index=idx,
    )


def _synthetic_daily_bars(n=120, start=1000.0, seed=1, drift=0.0004, vol=0.015) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, n)
    closes = start * np.cumprod(1 + returns)
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "Open": closes * (1 - 0.002), "High": closes * (1 + 0.006), "Low": closes * (1 - 0.006),
            "Close": closes, "Volume": rng.integers(500_000, 2_000_000, n),
        },
        index=idx,
    )


def test_vendored_agent_runs_standalone():
    demo = generate_demo_prices(days=200)
    result = TechnicalAnalystAgent().analyze(demo, symbol="DEMO")
    assert result.action in ("BUY", "SELL", "HOLD")
    assert 0 <= result.directional_score <= 100
    assert 0 <= result.confidence_score <= 100


def test_vendored_agent_requires_min_bars():
    import pytest

    short_bars = [PriceBar(date=f"2026-01-{i+1:02d}", open=100, high=101, low=99, close=100, volume=1000) for i in range(10)]
    with pytest.raises(ValueError):
        TechnicalAnalystAgent().analyze(short_bars, symbol="DEMO")


def test_technical_analyst_blends_without_metric_collision():
    ctx = AnalysisContext(
        symbol="RELIANCE.NS",
        bars=_synthetic_bars(vol=0.003),
        fundamentals={},
        symbol_news=[],
        market_news=[],
        daily_bars=_synthetic_daily_bars(),
    )
    vote = TechnicalAnalyst().vote(ctx)

    assert vote.agent_name == "Technical Analyst"
    assert vote.action in ("BUY", "SELL", "HOLD")
    # Own intraday macd_histogram must not be clobbered by the team model's daily-scale value.
    assert "macd_histogram" in vote.metrics
    assert "daily_trend" in vote.metrics
    assert "action" in vote.metrics["daily_trend"]


def test_technical_analyst_degrades_gracefully_without_daily_bars():
    ctx = AnalysisContext(
        symbol="TCS.NS", bars=_synthetic_bars(), fundamentals={}, symbol_news=[], market_news=[], daily_bars=None,
    )
    vote = TechnicalAnalyst().vote(ctx)
    assert vote.action in ("BUY", "SELL", "HOLD", "WAIT")
    assert "daily_trend" not in vote.metrics
    assert any("skipped" in e for e in vote.evidence)
