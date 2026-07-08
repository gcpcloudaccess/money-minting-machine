"""In-memory and JSON-file decision memory for the risk agent."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from risk_agent.models import HistoricalDecision, Recommendation, RiskMetrics


class DecisionMemory:
    """Store historical decisions and compare current risk with prior runs."""

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self.storage_path = Path(storage_path) if storage_path else None
        self._decisions: list[HistoricalDecision] = []
        if self.storage_path and self.storage_path.exists():
            self.load()

    def add(self, decision: HistoricalDecision) -> None:
        self._decisions.append(decision)
        if self.storage_path:
            self.save()

    def for_symbol(self, symbol: str) -> list[HistoricalDecision]:
        return [item for item in self._decisions if item.symbol == symbol]

    def compare(self, symbol: str, risk_score: int, metrics: RiskMetrics) -> dict[str, Any]:
        history = self.for_symbol(symbol)
        if not history:
            return {
                "has_history": False,
                "message": "No previous risk decisions stored for this symbol.",
            }
        previous = history[-1]
        return {
            "has_history": True,
            "previous_recommendation": previous.recommendation,
            "previous_risk_score": previous.risk_score,
            "risk_score_change": risk_score - previous.risk_score,
            "volatility_change": round(metrics.volatility - previous.metrics.get("volatility", 0.0), 4),
            "drawdown_change": round(metrics.max_drawdown - previous.metrics.get("max_drawdown", 0.0), 4),
            "message": "Current risk is compared with the most recent stored decision.",
        }

    def reliability_score(self) -> float | None:
        """Estimate historical correctness from realized returns if available.

        BUY is considered correct with positive realized returns, SELL with
        negative realized returns, and HOLD with small absolute realized moves.
        """

        scored = [item for item in self._decisions if item.realized_return is not None]
        if not scored:
            return None
        correct = 0
        for item in scored:
            if _decision_was_correct(item.recommendation, item.realized_return or 0.0):
                correct += 1
        return round(correct / len(scored), 4)

    def save(self) -> None:
        if not self.storage_path:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(item) for item in self._decisions]
        self.storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load(self) -> None:
        if not self.storage_path:
            return
        raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
        self._decisions = [HistoricalDecision(**item) for item in raw]


def _decision_was_correct(recommendation: Recommendation, realized_return: float) -> bool:
    if recommendation == "BUY":
        return realized_return > 0.02
    if recommendation == "SELL":
        return realized_return < -0.02
    return abs(realized_return) <= 0.03
