"""Position Sizing Agent: turns a consensus verdict + confidence into a
concrete order quantity, respecting the ₹10,000 capital / 1:2 leverage cap and
scaling exposure with both confidence and the risk regime."""

from __future__ import annotations

from app.config import get_settings


def size_position(
    directional_confidence_pct: float,
    risk_level: str,
    price: float,
    current_open_exposure: float,
    cash_available: float,
) -> dict:
    settings = get_settings()
    max_exposure = settings.max_exposure_inr
    remaining_exposure_budget = max(max_exposure - current_open_exposure, 0.0)

    if price <= 0 or remaining_exposure_budget <= 0:
        return {"quantity": 0, "notional": 0.0, "reason": "No exposure budget remaining under leverage cap."}

    confidence_fraction = max(0.0, min(directional_confidence_pct / 100.0, 1.0))

    risk_multiplier = {"LOW": 1.0, "MEDIUM": 0.65, "HIGH": 0.35, "EXTREME": 0.15}.get(risk_level, 0.65)

    # Scale how much of the *remaining* exposure budget to deploy this trade:
    # base 20%, up to 60% at max confidence and low risk.
    deploy_fraction = 0.2 + 0.4 * confidence_fraction * risk_multiplier
    target_notional = remaining_exposure_budget * deploy_fraction

    # Can't spend more cash than available (even with leverage, margin must be posted).
    target_notional = min(target_notional, cash_available * settings.leverage)

    quantity = int(target_notional // price)
    notional = quantity * price

    return {
        "quantity": quantity,
        "notional": round(notional, 2),
        "deploy_fraction": round(deploy_fraction, 3),
        "remaining_exposure_budget": round(remaining_exposure_budget, 2),
        "risk_multiplier": risk_multiplier,
    }
