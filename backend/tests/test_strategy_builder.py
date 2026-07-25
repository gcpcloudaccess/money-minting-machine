"""Unit tests for strategy_builder: direction + IV regime -> options structure
with correctly-signed max loss/profit/breakeven. Pure Python over a synthetic
OptionChainSnapshot, no network/LLM required."""

from app.data.options_data import OptionChainSnapshot, OptionLeg
from app.tools.strategy_builder import build_strategy


def _leg(strike, call_ltp, put_ltp):
    return OptionLeg(
        strike=strike, expiry="2026-08-25", call_iv=20.0, call_oi=1000, call_ltp=call_ltp, call_bid=call_ltp - 0.5, call_ask=call_ltp + 0.5,
        put_iv=20.0, put_oi=1000, put_ltp=put_ltp, put_bid=put_ltp - 0.5, put_ask=put_ltp + 0.5,
    )


def _chain(spot=1000.0):
    # Roughly realistic decreasing call premium / increasing put premium as strikes rise.
    legs = [
        _leg(940, call_ltp=75.0, put_ltp=10.0),
        _leg(960, call_ltp=58.0, put_ltp=15.0),
        _leg(980, call_ltp=42.0, put_ltp=22.0),
        _leg(1000, call_ltp=28.0, put_ltp=30.0),
        _leg(1020, call_ltp=18.0, put_ltp=42.0),
        _leg(1040, call_ltp=10.0, put_ltp=57.0),
        _leg(1060, call_ltp=5.0, put_ltp=75.0),
    ]
    return OptionChainSnapshot(symbol="TEST.NS", underlying_price=spot, expiries=["2026-08-25"], legs=legs)


def test_no_structure_for_hold_or_missing_chain():
    assert build_strategy("HOLD", 50.0, "fair", _chain()) is None
    assert build_strategy("BUY", 50.0, "fair", None) is None


def test_cheap_iv_buys_option_outright():
    pick = build_strategy("BUY", 30.0, "cheap", _chain())
    assert pick is not None
    assert pick.structure_type == "long_call"
    assert len(pick.legs) == 1
    assert pick.legs[0].action == "BUY"
    assert pick.max_profit is None  # uncapped
    assert pick.max_loss == pick.legs[0].premium


def test_high_conviction_buys_outright_even_if_rich():
    pick = build_strategy("SELL", 45.0, "rich", _chain())
    assert pick is not None
    assert pick.structure_type == "long_put"


def test_rich_iv_moderate_conviction_uses_debit_spread():
    pick = build_strategy("BUY", 30.0, "rich", _chain())
    assert pick is not None
    assert pick.structure_type == "bull_call_debit_spread"
    assert len(pick.legs) == 2
    assert pick.legs[0].action == "BUY" and pick.legs[1].action == "SELL"
    assert pick.max_loss is not None and pick.max_profit is not None
    assert pick.max_loss >= 0 and pick.max_profit >= 0


def test_rich_iv_low_conviction_uses_credit_spread():
    pick = build_strategy("BUY", 15.0, "rich", _chain())
    assert pick is not None
    assert pick.structure_type == "bull_put_credit_spread"
    assert pick.legs[0].action == "SELL" and pick.legs[1].action == "BUY"
    assert pick.max_loss is not None and pick.max_profit is not None


def test_bear_call_credit_spread_for_sell_low_conviction():
    pick = build_strategy("SELL", 15.0, "rich", _chain())
    assert pick is not None
    assert pick.structure_type == "bear_call_credit_spread"


def test_payoff_curve_is_populated():
    pick = build_strategy("BUY", 30.0, "cheap", _chain())
    assert len(pick.payoff_points) > 10
    # Payoff at a very high spot for a long call should be strongly positive (deep ITM).
    high_spot_pnl = max(pnl for spot, pnl in pick.payoff_points if spot > 1200)
    assert high_spot_pnl > 0
