"""Composite fundamental scoring: normalizes raw fundamentals against sane
reference ranges for Indian large/mid-cap equities and combines them into a
single directional signal."""

from __future__ import annotations


def _score_pe(pe: float | None) -> float:
    if pe is None or pe <= 0:
        return 0.0
    if pe < 15:
        return 0.6
    if pe < 25:
        return 0.2
    if pe < 40:
        return -0.2
    return -0.5


def _score_growth(growth: float | None) -> float:
    if growth is None:
        return 0.0
    return max(-0.6, min(0.6, growth * 2.0))


def _score_margins(margin: float | None) -> float:
    if margin is None:
        return 0.0
    if margin > 0.20:
        return 0.4
    if margin > 0.10:
        return 0.15
    if margin < 0:
        return -0.4
    return 0.0


def _score_leverage(debt_to_equity: float | None) -> float:
    if debt_to_equity is None:
        return 0.0
    if debt_to_equity < 50:
        return 0.2
    if debt_to_equity < 150:
        return 0.0
    return -0.3


def analyze(fundamentals: dict) -> dict:
    pe_score = _score_pe(fundamentals.get("pe_ratio"))
    growth_score = _score_growth(fundamentals.get("revenue_growth"))
    margin_score = _score_margins(fundamentals.get("profit_margins"))
    leverage_score = _score_leverage(fundamentals.get("debt_to_equity"))

    total = pe_score + growth_score + margin_score + leverage_score
    evidence = []

    pe = fundamentals.get("pe_ratio")
    if pe:
        evidence.append(f"P/E ratio {pe:.1f} ({'attractive' if pe_score > 0 else 'rich' if pe_score < 0 else 'neutral'}).")
    growth = fundamentals.get("revenue_growth")
    if growth is not None:
        evidence.append(f"Revenue growth {growth*100:+.1f}% YoY.")
    margin = fundamentals.get("profit_margins")
    if margin is not None:
        evidence.append(f"Profit margin {margin*100:.1f}%.")
    d2e = fundamentals.get("debt_to_equity")
    if d2e is not None:
        evidence.append(f"Debt/Equity {d2e:.0f}.")

    if not evidence:
        evidence.append("Limited fundamental data available for this symbol.")

    if total > 0.4:
        action = "BUY"
    elif total < -0.4:
        action = "SELL"
    else:
        action = "HOLD"

    confidence = round(max(0.15, min(0.9, abs(total) / 2.0 + 0.15)), 3)

    return {
        "action": action,
        "confidence": confidence,
        "evidence": evidence,
        "metrics": {
            "pe_score": round(pe_score, 2),
            "growth_score": round(growth_score, 2),
            "margin_score": round(margin_score, 2),
            "leverage_score": round(leverage_score, 2),
            "composite": round(total, 2),
        },
    }
