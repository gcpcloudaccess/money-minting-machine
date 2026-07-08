"""Alert Agent: rule-based flags for high-risk situations or notable
opportunities, surfaced to the UI and audit log."""

from __future__ import annotations


def evaluate(symbol: str, verdict: str, directional_confidence: float, risk_level: str, alternatives: list[dict]) -> list[dict]:
    alerts = []

    if risk_level == "HIGH" and verdict in ("BUY", "SWITCH"):
        alerts.append({"severity": "warning", "message": f"{symbol}: acting on {verdict} despite HIGH volatility regime."})

    if directional_confidence >= 80:
        alerts.append({"severity": "info", "message": f"{symbol}: very high committee conviction ({directional_confidence:.0f}%) on {verdict}."})

    if alternatives:
        best = alternatives[0]
        alerts.append({"severity": "opportunity", "message": f"{symbol}: Opportunity Critic flags {best['symbol']} as a stronger risk-adjusted setup."})

    return alerts
