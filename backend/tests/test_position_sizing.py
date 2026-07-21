"""Tests for confidence-scaled position sizing under the default no-margin
configuration (settings.leverage = 1.0) - no network, no LLM key required.

Regression context: an earlier version of this scaling used the full 0-100%
directional_confidence range, but real trades in this system only ever fire
in the ~18-40% band (see trust_weighted_consensus.py's decisive threshold).
The app now runs cash-only (no margin) by default, so these tests lock in
that leverage_used is pinned at 1.0 and margin is never drawn, while sizing
still scales sensibly with confidence and risk via notional/deploy_fraction."""

from app.portfolio import position_sizing


def test_leverage_never_exceeds_configured_ceiling():
    result = position_sizing.size_position(
        directional_confidence_pct=100.0, risk_level="LOW", price=1000.0,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    assert result["leverage_used"] <= result["max_leverage"]
    assert result["max_leverage"] == 1.0  # settings default - no margin


def test_realistic_decisive_confidence_draws_no_margin():
    """A trade at a realistic just-cleared-the-bar confidence (~19%, matching
    real production decisions) should still size a real position, but under
    the no-margin default it must never draw on buying power beyond cash."""
    result = position_sizing.size_position(
        directional_confidence_pct=19.0, risk_level="MEDIUM", price=1290.40,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    assert result["leverage_used"] == 1.0  # no-margin ceiling, always
    assert result["margin_used_inr"] == 0.0
    assert result["notional"] > 0.0


def test_notional_scales_up_with_confidence():
    """Leverage itself is pinned at 1.0 (no margin), but higher confidence
    should still deploy a larger share of available cash via deploy_fraction."""
    low_conf = position_sizing.size_position(
        directional_confidence_pct=18.0, risk_level="LOW", price=1000.0,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    high_conf = position_sizing.size_position(
        directional_confidence_pct=30.0, risk_level="LOW", price=1000.0,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    assert low_conf["leverage_used"] == high_conf["leverage_used"] == 1.0
    assert high_conf["notional"] > low_conf["notional"]


def test_notional_scales_down_with_risk():
    low_risk = position_sizing.size_position(
        directional_confidence_pct=25.0, risk_level="LOW", price=1000.0,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    high_risk = position_sizing.size_position(
        directional_confidence_pct=25.0, risk_level="EXTREME", price=1000.0,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    assert low_risk["leverage_used"] == high_risk["leverage_used"] == 1.0
    assert low_risk["notional"] > high_risk["notional"]


def test_no_margin_is_ever_drawn_even_for_a_strong_low_risk_signal():
    """Even the most aggressive case (high confidence, LOW risk) must stay
    within available cash under the no-margin default - this is the direct
    guarantee the ₹10,00,000 cash-only paper capital configuration relies on."""
    result = position_sizing.size_position(
        directional_confidence_pct=30.0, risk_level="LOW", price=100.0,
        current_open_exposure=0.0, cash_available=10_000.0,
    )
    assert result["notional"] <= 10_000.0
    assert result["margin_used_inr"] == 0.0


def test_never_exceeds_portfolio_wide_exposure_cap():
    # Exposure budget already exhausted -> no new position regardless of confidence.
    # settings default: ₹10,00,000 capital x 1.0 leverage (no margin) = ₹10,00,000 cap.
    result = position_sizing.size_position(
        directional_confidence_pct=100.0, risk_level="LOW", price=1000.0,
        current_open_exposure=1_000_000.0, cash_available=10_000.0,  # at the cap already
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
