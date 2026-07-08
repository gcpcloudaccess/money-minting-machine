"""Execution Advisor Agent: recommends order type/timing given the risk
regime and conviction level (kept simple - this is paper trading, so the
"advice" mainly documents the reasoning behind using a market order now vs
waiting)."""

from __future__ import annotations


def advise(verdict: str, directional_confidence_pct: float, risk_level: str) -> dict:
    if verdict in ("WAIT", "HOLD"):
        return {"order_type": None, "timing": "No order this tick.", "note": "Consensus did not clear the conviction threshold for action."}

    if risk_level == "HIGH" and directional_confidence_pct < 65:
        return {
            "order_type": "LIMIT",
            "timing": "Place a limit order near the current bid/ask rather than crossing the spread market-order style.",
            "note": "High volatility regime with moderate conviction - avoid paying up for immediacy.",
        }

    return {
        "order_type": "MARKET",
        "timing": "Execute immediately this tick.",
        "note": "Conviction and risk regime support immediate execution rather than waiting for a better price.",
    }
