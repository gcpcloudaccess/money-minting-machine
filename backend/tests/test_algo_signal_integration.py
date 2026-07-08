"""Tests for the vendored team algo_agent package and its integration into
our new Algo Signal Analyst - no network, no LLM key required."""

import numpy as np
import pandas as pd

from algo_agent.agent import recommend
from algo_agent.data import generate_demo_prices
from app.agents.analysts.algo_signal import AlgoSignalAnalyst, _skill_factor
from app.agents.base import AnalysisContext


def _synthetic_bars(n=150, start=1000.0, seed=1, drift=0.0003, vol=0.006) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, n)
    closes = start * np.cumprod(1 + returns)
    idx = pd.date_range("2026-07-08 09:15", periods=n, freq="5min")
    return pd.DataFrame(
        {
            "Open": closes * (1 - 0.001), "High": closes * (1 + 0.003), "Low": closes * (1 - 0.003),
            "Close": closes, "Volume": rng.integers(50_000, 200_000, n),
        },
        index=idx,
    )


def test_vendored_agent_runs_standalone():
    demo = generate_demo_prices(days=300)
    rec = recommend(demo, symbol="DEMO")
    assert rec.action in ("BUY", "SELL", "HOLD")
    assert 0 <= rec.model_probability_up <= 1
    assert rec.model_metrics.samples > 0


def test_vendored_critic_runs_standalone():
    from critic_agent.critic import review_recommendation

    demo = generate_demo_prices(days=300)
    rec = recommend(demo, symbol="DEMO")
    critique = review_recommendation(rec.to_dict())
    assert critique.verdict in ("PASS", "CAUTION", "REJECT")
    assert 0 <= critique.score <= 100


def test_skill_factor_discounts_no_edge_models():
    no_edge = _skill_factor(accuracy=0.50, baseline=0.55)  # negative edge
    good_edge = _skill_factor(accuracy=0.65, baseline=0.52)  # solid positive edge
    assert no_edge < good_edge
    assert no_edge >= 0.2  # floor, never zero


def test_algo_signal_analyst_runs_on_synthetic_bars():
    ctx = AnalysisContext(symbol="RELIANCE.NS", bars=_synthetic_bars(), fundamentals={}, symbol_news=[], market_news=[])
    vote = AlgoSignalAnalyst().vote(ctx)

    assert vote.agent_name == "Algo Signal Analyst"
    assert vote.action in ("BUY", "SELL", "HOLD", "WAIT")
    assert "model_probability_up" in vote.metrics
    assert "validation_edge" in vote.metrics
    assert vote.metrics["critic_verdict"] in ("PASS", "CAUTION", "REJECT")


def test_critic_reject_forces_wait_action():
    ctx = AnalysisContext(symbol="RELIANCE.NS", bars=_synthetic_bars(seed=3), fundamentals={}, symbol_news=[], market_news=[])
    vote = AlgoSignalAnalyst().vote(ctx)

    if vote.metrics.get("critic_verdict") == "REJECT":
        assert vote.action == "WAIT"


def test_algo_signal_analyst_degrades_gracefully_with_too_few_bars():
    short_bars = _synthetic_bars(n=20)
    ctx = AnalysisContext(symbol="TCS.NS", bars=short_bars, fundamentals={}, symbol_news=[], market_news=[])
    vote = AlgoSignalAnalyst().vote(ctx)
    assert vote.action == "WAIT"
    assert vote.metrics == {}
