"""Integration tests for the new positional-only analyst agents (IV & Options
Chain, Volatility Regime, Catalyst, Liquidity, Relative Strength) - no
network/LLM key required (LLMClient degrades to a deterministic fallback
without a configured key, same as every existing agent test in this suite).

Mainly proves graceful degradation: every one of these agents must return a
valid AgentVote when its positional-only context fields are empty/None
(the case for every existing intraday call, since only positional_scanner.py
populates them), never raise."""

import numpy as np
import pandas as pd

from app.agents.analysts.catalyst import CatalystAnalyst
from app.agents.analysts.iv_options import IVOptionsAnalyst
from app.agents.analysts.liquidity import LiquidityAnalyst
from app.agents.analysts.relative_strength import RelativeStrengthAnalyst
from app.agents.analysts.volatility_regime import VolatilityRegimeAnalyst
from app.agents.base import AnalysisContext, VALID_ACTIONS
from app.data.options_data import OptionChainSnapshot, OptionLeg


def _bare_ctx(**overrides) -> AnalysisContext:
    base = dict(symbol="RELIANCE.NS", bars=pd.DataFrame(), fundamentals={}, symbol_news=[], market_news=[])
    base.update(overrides)
    return AnalysisContext(**base)


def _daily_bars(n=40, start=1000.0, seed=1, drift=0.0, vol=0.01) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, n)
    closes = start * np.cumprod(1 + returns)
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": 1_000_000}, index=idx)


def _chain(spot=1000.0):
    legs = [
        OptionLeg(strike=s, expiry="2026-08-25", call_iv=20.0, call_oi=2000, call_ltp=15.0, call_bid=14.5, call_ask=15.5,
                  put_iv=21.0, put_oi=1800, put_ltp=15.0, put_bid=14.5, put_ask=15.5)
        for s in (940, 970, 1000, 1030, 1060)
    ]
    return OptionChainSnapshot(symbol="RELIANCE.NS", underlying_price=spot, expiries=["2026-08-25", "2026-09-29"], legs=legs)


def test_iv_options_analyst_degrades_without_chain():
    vote = IVOptionsAnalyst().vote(_bare_ctx(option_chain=None))
    assert vote.action in VALID_ACTIONS
    assert vote.confidence <= 0.2


def test_iv_options_analyst_with_chain():
    ctx = _bare_ctx(option_chain=_chain(), iv_history=[18.0 + i * 0.1 for i in range(25)], bars=_daily_bars())
    vote = IVOptionsAnalyst().vote(ctx)
    assert vote.action in VALID_ACTIONS
    assert "atm_iv" in vote.metrics


def test_volatility_regime_analyst_degrades_without_data():
    vote = VolatilityRegimeAnalyst().vote(_bare_ctx())
    assert vote.action in VALID_ACTIONS


def test_volatility_regime_analyst_with_data():
    ctx = _bare_ctx(daily_bars=_daily_bars(), option_chain=_chain())
    vote = VolatilityRegimeAnalyst().vote(ctx)
    assert vote.action in VALID_ACTIONS
    assert vote.metrics["regime"] in ("cheap", "fair", "rich", "unknown")


def test_catalyst_analyst_no_events():
    vote = CatalystAnalyst().vote(_bare_ctx(catalyst_events=[]))
    assert vote.action == "HOLD"
    assert vote.confidence < 0.3


def test_catalyst_analyst_flags_near_term_earnings():
    events = [{"date": "2026-07-28", "kind": "earnings", "label": "RELIANCE.NS earnings", "days_away": 3}]
    vote = CatalystAnalyst().vote(_bare_ctx(catalyst_events=events))
    assert vote.action == "WAIT"
    assert vote.confidence >= 0.4


def test_liquidity_analyst_degrades_without_chain():
    vote = LiquidityAnalyst().vote(_bare_ctx(option_chain=None))
    assert vote.action in VALID_ACTIONS


def test_liquidity_analyst_flags_thin_market():
    thin_legs = [
        OptionLeg(strike=1000, expiry="2026-08-25", call_iv=20.0, call_oi=50, call_ltp=15.0, call_bid=10.0, call_ask=20.0,
                  put_iv=20.0, put_oi=50, put_ltp=15.0, put_bid=10.0, put_ask=20.0)
    ]
    chain = OptionChainSnapshot(symbol="RELIANCE.NS", underlying_price=1000.0, expiries=["2026-08-25"], legs=thin_legs)
    vote = LiquidityAnalyst().vote(_bare_ctx(option_chain=chain))
    assert vote.action == "WAIT"


def test_relative_strength_analyst_degrades_without_daily_bars():
    vote = RelativeStrengthAnalyst().vote(_bare_ctx())
    assert vote.action in VALID_ACTIONS
    assert vote.confidence < 0.2


def test_relative_strength_analyst_detects_outperformance():
    ctx = _bare_ctx(
        daily_bars=_daily_bars(seed=1, drift=0.01, vol=0.005),      # strong uptrend
        benchmark_bars=_daily_bars(seed=2, drift=0.0, vol=0.005),   # flat benchmark
    )
    vote = RelativeStrengthAnalyst().vote(ctx)
    assert vote.action == "BUY"
    assert vote.metrics["relative_strength_pp"] > 0
