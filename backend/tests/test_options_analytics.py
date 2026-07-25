"""Unit tests for options chain analytics (IV rank, PCR, max pain) - pure
Python over a synthetic OptionChainSnapshot, no network/LLM required."""

from app.data.options_data import OptionChainSnapshot, OptionLeg
from app.tools import options_analytics


def _leg(strike, call_iv=20.0, call_oi=1000, call_ltp=10.0, put_iv=22.0, put_oi=1000, put_ltp=10.0, expiry="2026-08-25"):
    return OptionLeg(
        strike=strike, expiry=expiry, call_iv=call_iv, call_oi=call_oi, call_ltp=call_ltp, call_bid=call_ltp - 0.5, call_ask=call_ltp + 0.5,
        put_iv=put_iv, put_oi=put_oi, put_ltp=put_ltp, put_bid=put_ltp - 0.5, put_ask=put_ltp + 0.5,
    )


def _chain(spot=1000.0):
    legs = [_leg(s) for s in (940, 960, 980, 1000, 1020, 1040, 1060)]
    return OptionChainSnapshot(symbol="TEST.NS", underlying_price=spot, expiries=["2026-08-25", "2026-09-29"], legs=legs)


def test_iv_rank_needs_minimum_history():
    assert options_analytics.iv_rank(25.0, [20.0] * 5) is None  # below IV_HISTORY_MIN_DAYS


def test_iv_rank_at_extremes():
    history = [10.0 + i for i in range(25)]  # 10..34
    assert options_analytics.iv_rank(34.0, history) == 100.0
    assert options_analytics.iv_rank(10.0, history) == 0.0
    assert options_analytics.iv_rank(22.0, history) == 50.0


def test_put_call_oi_ratio_balanced_chain_is_one():
    chain = _chain()
    assert options_analytics.put_call_oi_ratio(chain) == 1.0


def test_put_call_oi_ratio_put_heavy():
    legs = [_leg(1000, call_oi=1000, put_oi=3000)]
    chain = OptionChainSnapshot(symbol="TEST.NS", underlying_price=1000.0, expiries=["2026-08-25"], legs=legs)
    assert options_analytics.put_call_oi_ratio(chain) == 3.0


def test_max_pain_picks_lowest_writer_loss_strike():
    # Concentrate OI heavily at 1000 on both sides - writers lose least if price pins there.
    legs = [
        _leg(960, call_oi=100, put_oi=100),
        _leg(980, call_oi=100, put_oi=100),
        _leg(1000, call_oi=5000, put_oi=5000),
        _leg(1020, call_oi=100, put_oi=100),
        _leg(1040, call_oi=100, put_oi=100),
    ]
    chain = OptionChainSnapshot(symbol="TEST.NS", underlying_price=1000.0, expiries=["2026-08-25"], legs=legs)
    assert options_analytics.max_pain(chain) == 1000.0


def test_analyze_degrades_gracefully_with_no_chain():
    result = options_analytics.analyze(None, [], 0.0, 20.0)
    assert result["action"] == "HOLD"
    assert result["confidence"] < 0.3
    assert "No live options chain" in result["evidence"][0]


def test_analyze_returns_structured_signal_with_chain():
    chain = _chain()
    result = options_analytics.analyze(chain, [15.0] * 25, spot_change_pct=1.5, days_to_expiry=20)
    assert result["action"] in ("BUY", "SELL", "HOLD")
    assert 0.0 < result["confidence"] <= 1.0
    assert "atm_iv" in result["metrics"]
