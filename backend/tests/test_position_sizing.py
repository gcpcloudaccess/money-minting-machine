"""Tests for confidence-scaled, capped leverage in position sizing - no
network, no LLM key required.

Regression context: the first version of this scaling used the full 0-100%
directional_confidence range, but real trades in this system only ever fire
in the ~18-40% band (see trust_weighted_consensus.py's decisive threshold),
so leverage never actually got exercised - real executed trades sized well
under available *cash*, let alone margin. These tests lock in that leverage
is meaningfully used for any trade that actually fires, not just in theory."""

from app.portfolio import position_sizing


def test_leverage_never_exceeds_configured_ceiling():
    result = position_sizing.size_position(
        directional_confidence_pct=100.0, risk_level="LOW", price=1000.0,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    assert result["leverage_used"] <= result["max_leverage"]
    assert result["max_leverage"] == 2.0  # settings default


def test_realistic_decisive_confidence_meaningfully_uses_leverage():
    """The actual bug report: a trade at a realistic just-cleared-the-bar
    confidence (~19%, matching real production decisions) must draw
    meaningfully on leverage, not size so conservatively it never even
    spends available cash."""
    result = position_sizing.size_position(
        directional_confidence_pct=19.0, risk_level="MEDIUM", price=1290.40,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    assert result["leverage_used"] > 1.4  # meaningfully above the 1.4x base, not stuck near 1x
    assert result["notional"] > 0.0


def test_leverage_scales_up_with_confidence():
    low_conf = position_sizing.size_position(
        directional_confidence_pct=18.0, risk_level="LOW", price=1000.0,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    high_conf = position_sizing.size_position(
        directional_confidence_pct=30.0, risk_level="LOW", price=1000.0,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    assert high_conf["leverage_used"] > low_conf["leverage_used"]
    assert high_conf["leverage_used"] == 2.0  # at/above STRONG_CONFIDENCE_PCT with LOW risk -> full ceiling


def test_leverage_scales_down_with_risk():
    low_risk = position_sizing.size_position(
        directional_confidence_pct=25.0, risk_level="LOW", price=1000.0,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    high_risk = position_sizing.size_position(
        directional_confidence_pct=25.0, risk_level="EXTREME", price=1000.0,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    assert low_risk["leverage_used"] > high_risk["leverage_used"]


def test_strong_low_risk_signal_actually_draws_margin():
    result = position_sizing.size_position(
        directional_confidence_pct=30.0, risk_level="LOW", price=100.0,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    assert result["notional"] > 10_000.0  # exceeds own cash -> genuinely using leverage
    assert result["margin_used_inr"] > 0.0
    assert result["notional"] <= 10_000.0 * result["max_leverage"]


def test_never_exceeds_portfolio_wide_exposure_cap():
    # Exposure budget already exhausted -> no new position regardless of confidence.
    result = position_sizing.size_position(
        directional_confidence_pct=100.0, risk_level="LOW", price=1000.0,
        current_open_exposure=20_000.0, cash_available=10_000.0,  # at the 2x cap already
    )
    assert result["quantity"] == 0


def test_symbol_cap_blocks_new_position_when_exhausted():
    """Investment Planner's per-symbol allocation cap (allocation_planner.py) must be
    enforced even when cash/leverage/portfolio-exposure budget would otherwise allow it."""
    result = position_sizing.size_position(
        directional_confidence_pct=30.0, risk_level="LOW", price=1000.0,
        current_open_exposure=0.0, cash_available=10_000.0,
        symbol_cap_inr=5_000.0, current_symbol_exposure=5_000.0,  # already at this symbol's cap
    )
    assert result["quantity"] == 0
    assert "symbol" in result["reason"].lower()


def test_sector_cap_blocks_new_position_when_exhausted():
    result = position_sizing.size_position(
        directional_confidence_pct=30.0, risk_level="LOW", price=1000.0,
        current_open_exposure=0.0, cash_available=10_000.0,
        sector_cap_inr=7_000.0, current_sector_exposure=7_000.0,  # already at this sector's cap
    )
    assert result["quantity"] == 0
    assert "sector" in result["reason"].lower()


def test_expensive_foreign_share_gets_zero_quantity_without_fractional_shares():
    """The actual bug report: AAPL at ~Rs28,000/share (FX-converted) is worth
    more than the entire Rs7,000 per-symbol cap - without fractional shares,
    this permanently rounds down to 0 and the trade never executes, even
    though the committee cleared the decisive threshold with a real BUY."""
    result = position_sizing.size_position(
        directional_confidence_pct=19.0, risk_level="MEDIUM", price=28_153.0,
        current_open_exposure=0.0, cash_available=10_000.0,
        symbol_cap_inr=7_000.0, sector_cap_inr=10_000.0,
    )
    assert result["quantity"] == 0


def test_allow_fractional_lets_the_same_expensive_share_actually_execute():
    result = position_sizing.size_position(
        directional_confidence_pct=19.0, risk_level="MEDIUM", price=28_153.0,
        current_open_exposure=0.0, cash_available=10_000.0,
        symbol_cap_inr=7_000.0, sector_cap_inr=10_000.0, allow_fractional=True,
    )
    assert result["quantity"] > 0
    assert result["quantity"] < 1  # a fraction of a share, not a whole one
    assert result["notional"] > 0.0


def test_fractional_quantity_respects_symbol_cap():
    result = position_sizing.size_position(
        directional_confidence_pct=30.0, risk_level="LOW", price=28_153.0,
        current_open_exposure=0.0, cash_available=10_000.0,
        symbol_cap_inr=7_000.0, allow_fractional=True,
    )
    assert result["notional"] <= 7_000.0 + 1.0  # rounding slack


def test_symbol_cap_limits_notional_without_blocking_entirely():
    """A partially-used symbol cap should shrink the trade, not zero it out or get
    ignored in favor of the (larger) portfolio-wide exposure budget."""
    uncapped = position_sizing.size_position(
        directional_confidence_pct=30.0, risk_level="LOW", price=100.0,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    capped = position_sizing.size_position(
        directional_confidence_pct=30.0, risk_level="LOW", price=100.0,
        current_open_exposure=0.0, cash_available=10_000.0,
        symbol_cap_inr=2_000.0, current_symbol_exposure=0.0,
    )
    assert capped["notional"] < uncapped["notional"]
    assert capped["notional"] > 0.0
    assert capped["binding_constraint"] == "symbol_cap"
