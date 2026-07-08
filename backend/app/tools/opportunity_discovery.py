"""Opportunity discovery: screens the watchlist universe for candidates with a
stronger risk-adjusted technical setup than the one currently under review.
Backs the "Opportunity Critic" agent's job of proposing better alternatives."""

from __future__ import annotations

import pandas as pd

from app.tools import risk_model, technical_indicators


def _risk_adjusted_score(bars: pd.DataFrame) -> float | None:
    tech = technical_indicators.analyze(bars)
    risk = risk_model.analyze(bars)
    if not tech["metrics"] or not risk["metrics"]:
        return None

    direction = {"BUY": 1.0, "SELL": -1.0, "HOLD": 0.0, "WAIT": 0.0}[tech["action"]]
    tech_score = direction * tech["confidence"]

    vol = risk["metrics"].get("volatility")
    risk_penalty = min((vol or 0.0) * 20, 1.0)  # higher vol -> bigger penalty

    return tech_score - 0.4 * risk_penalty


def find_alternatives(
    current_symbol: str,
    current_action: str,
    universe_bars: dict[str, pd.DataFrame],
    top_n: int = 3,
) -> dict:
    scores: dict[str, float] = {}
    for sym, bars in universe_bars.items():
        s = _risk_adjusted_score(bars)
        if s is not None:
            scores[sym] = s

    current_score = scores.get(current_symbol, 0.0)
    ranked = sorted((s for s in scores.items() if s[0] != current_symbol), key=lambda kv: kv[1], reverse=True)
    better = [(sym, sc) for sym, sc in ranked if sc > current_score + 0.1][:top_n]

    if not better:
        return {
            "action": "HOLD",
            "confidence": 0.3,
            "evidence": [f"No watchlist alternative meaningfully outscores {current_symbol} right now."],
            "alternatives": [],
        }

    top_sym, top_score = better[0]
    evidence = [f"{sym} risk-adjusted score {sc:+.2f} vs {current_symbol} {current_score:+.2f}." for sym, sc in better]

    action = "SWITCH" if current_action in ("BUY", "HOLD") else "HOLD"

    return {
        "action": action,
        "confidence": round(min(0.85, max(0.25, (top_score - current_score))), 3),
        "evidence": evidence,
        "alternatives": [{"symbol": sym, "score": round(sc, 3)} for sym, sc in better],
    }
