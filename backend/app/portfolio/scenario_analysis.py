"""Scenario Analysis Agent: quick stress test of a proposed position across a
handful of plausible intraday price moves, feeding the "expected risk & return"
field required in every trade output."""

from __future__ import annotations


def stress_test(entry_price: float, quantity: float, side: str, volatility: float | None) -> dict:
    vol = volatility or 0.01
    moves_pct = sorted({-3 * vol, -2 * vol, -vol, vol, 2 * vol, 3 * vol, -0.01, 0.01})

    scenarios = []
    for move in moves_pct:
        exit_price = entry_price * (1 + move)
        pnl = (exit_price - entry_price) * quantity if side == "LONG" else (entry_price - exit_price) * quantity
        scenarios.append({"price_move_pct": round(move * 100, 2), "exit_price": round(exit_price, 2), "pnl_inr": round(pnl, 2)})

    downside = [s["pnl_inr"] for s in scenarios if s["pnl_inr"] < 0]
    upside = [s["pnl_inr"] for s in scenarios if s["pnl_inr"] > 0]

    expected_risk = round(min(downside), 2) if downside else 0.0
    expected_return = round(max(upside), 2) if upside else 0.0
    risk_reward_ratio = round(abs(expected_return / expected_risk), 2) if expected_risk else None

    return {
        "scenarios": scenarios,
        "expected_risk_inr": expected_risk,
        "expected_return_inr": expected_return,
        "risk_reward_ratio": risk_reward_ratio,
    }
