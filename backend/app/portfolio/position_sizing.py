"""Position Sizing Agent: turns a consensus verdict + confidence into a
concrete order quantity, respecting the ₹10,00,000 paper capital / configured
leverage cap and scaling exposure with both confidence and the risk regime.

Default configuration (settings.leverage = 1.0) is cash-only, no-margin paper
trading: leverage_used is mathematically pinned to 1.0 whenever max_leverage
<= BASE_LEVERAGE, so margin_used_inr is always 0 regardless of confidence or
risk - a trade can never draw on buying power beyond the cash actually on
hand. If settings.leverage is raised above 1.0 (e.g. back to 2.0 for 1:2),
leverage_used scales up from BASE_LEVERAGE toward that ceiling as confidence
and risk quality improve, calibrated against this system's realistic
directional-confidence range (~18-40% for trades that clear the decisive bar
- see trust_weighted_consensus.py), rather than the full 0-100% scale."""

from __future__ import annotations

from app.config import get_settings

# Any trade that fires already cleared the decisive threshold - start it here rather
# than near 1.0x, so leverage is actually exercised rather than sitting unused.
BASE_LEVERAGE = 1.4
# Directional confidence treated as "maximally convinced" for leverage-scaling purposes -
# calibrated against this system's realistic range, not the full 0-100% scale.
STRONG_CONFIDENCE_PCT = 30.0


def size_position(
    directional_confidence_pct: float,
    risk_level: str,
    price: float,
    current_open_exposure: float,
    cash_available: float,
    symbol_cap_inr: float | None = None,
    current_symbol_exposure: float = 0.0,
    sector_cap_inr: float | None = None,
    current_sector_exposure: float = 0.0,
    allow_fractional: bool = False,
) -> dict:
    """allow_fractional=True (foreign exchanges only - see portfolio_manager.py)
    permits a fractional share count, same as real fractional-share brokers
    (Robinhood, Zerodha's US-stock partners, etc). Without it, a single share
    priced above the per-symbol/sector allocation cap rounds down to a
    permanent 0 - a real problem once FX-converted US mega-cap prices (AAPL
    ~Rs28,000/share) are compared against a Rs10,000 capital base, not just a
    rare edge case. NSE stays whole-share-only, matching real Indian brokers."""
    settings = get_settings()
    max_leverage = settings.leverage  # hard ceiling, e.g. 2.0 for 1:2
    max_exposure = settings.max_exposure_inr  # starting_capital * max_leverage, portfolio-wide ceiling
    remaining_exposure_budget = max(max_exposure - current_open_exposure, 0.0)

    # Investment Planner's per-symbol/per-sector allocation caps (see
    # agents/allocation_planner.py) - None means "no cap configured", not "zero budget".
    remaining_symbol_budget = (
        max(symbol_cap_inr - current_symbol_exposure, 0.0) if symbol_cap_inr is not None else float("inf")
    )
    remaining_sector_budget = (
        max(sector_cap_inr - current_sector_exposure, 0.0) if sector_cap_inr is not None else float("inf")
    )

    if price <= 0 or remaining_exposure_budget <= 0 or remaining_symbol_budget <= 0 or remaining_sector_budget <= 0:
        if price <= 0 or remaining_exposure_budget <= 0:
            reason = "No exposure budget remaining under leverage cap."
        elif remaining_symbol_budget <= 0:
            reason = "Per-symbol allocation cap reached (Investment Planner)."
        else:
            reason = "Per-sector allocation cap reached (Investment Planner)."
        return {
            "quantity": 0, "notional": 0.0, "reason": reason,
            "leverage_used": 1.0, "margin_used_inr": 0.0, "max_leverage": max_leverage,
        }

    confidence_fraction = max(0.0, min(directional_confidence_pct / 100.0, 1.0))
    risk_multiplier = {"LOW": 1.0, "MEDIUM": 0.65, "HIGH": 0.35, "EXTREME": 0.15}.get(risk_level, 0.65)

    # Effective leverage for THIS trade: BASE_LEVERAGE for any decisive-but-modest signal,
    # scaling up to max_leverage as confidence approaches STRONG_CONFIDENCE_PCT and risk is low.
    strength = max(0.0, min(1.0, directional_confidence_pct / STRONG_CONFIDENCE_PCT))
    leverage_used = round(min(max_leverage, BASE_LEVERAGE + strength * risk_multiplier * (max_leverage - BASE_LEVERAGE)), 3)

    # Buying power for this trade: available cash amplified by the leverage above, capped by
    # the portfolio-wide exposure budget and the Investment Planner's per-symbol/per-sector
    # allocation caps, so none of those ceilings can be bypassed by a single large trade.
    budgets = {
        "cash_x_leverage": cash_available * leverage_used,
        "portfolio_exposure_cap": remaining_exposure_budget,
        "symbol_cap": remaining_symbol_budget,
        "sector_cap": remaining_sector_budget,
    }
    binding_constraint = min(budgets, key=budgets.get)
    buying_power = budgets[binding_constraint]

    # Deploy fraction now describes how much of THIS TRADE's leveraged buying power to commit
    # (not a small slice of the total portfolio budget) - 50% at minimum decisive confidence,
    # up to 90% at strong confidence and low risk, so leverage actually gets drawn on rather
    # than being capped by an unrelated, overly conservative slice of the total budget.
    deploy_fraction = 0.5 + 0.4 * confidence_fraction * risk_multiplier
    target_notional = buying_power * deploy_fraction

    quantity = round(target_notional / price, 4) if allow_fractional else int(target_notional // price)
    notional = round(quantity * price, 2)
    margin_used_inr = round(max(0.0, notional - cash_available), 2)

    return {
        "quantity": quantity,
        "notional": notional,
        "deploy_fraction": round(deploy_fraction, 3),
        "remaining_exposure_budget": round(remaining_exposure_budget, 2),
        "risk_multiplier": risk_multiplier,
        "leverage_used": leverage_used,
        "margin_used_inr": margin_used_inr,
        "max_leverage": max_leverage,
        "binding_constraint": binding_constraint,
    }
