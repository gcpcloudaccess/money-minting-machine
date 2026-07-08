from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
from pydantic import BaseModel


@dataclass
class AnalysisContext:
    """Everything an agent might need for one symbol at one tick."""

    symbol: str
    bars: pd.DataFrame
    fundamentals: dict
    symbol_news: list[dict]
    market_news: list[dict]
    peer_bars: dict[str, pd.DataFrame] = field(default_factory=dict)
    current_action_so_far: str | None = None
    daily_bars: pd.DataFrame | None = None  # symbol's own daily OHLCV history (~6mo)
    benchmark_bars: pd.DataFrame | None = None  # benchmark (Nifty 50) daily OHLCV history (~6mo)
    open_positions: list[dict] = field(default_factory=list)  # [{symbol, weight, sector}]


class AgentVote(BaseModel):
    agent_name: str
    agent_type: str  # analyst | debate | critic
    action: str  # BUY | SELL | HOLD | WAIT | SWITCH
    confidence: float
    reasoning: str
    evidence: list[str] = []
    metrics: dict = {}


VALID_ACTIONS = {"BUY", "SELL", "HOLD", "WAIT", "SWITCH"}


class BaseAgent:
    name: str = "BaseAgent"
    agent_type: str = "analyst"
    expertise: str = "general"

    def vote(self, ctx: AnalysisContext) -> AgentVote:  # pragma: no cover - overridden
        raise NotImplementedError


def blend_signals(signals: list[dict], weights: list[float]) -> dict:
    """Combine two or more tool outputs ({action, confidence, evidence, metrics})
    into one, weighting each signal's confidence contribution."""
    action_scores: dict[str, float] = {}
    evidence: list[str] = []
    metrics: dict = {}

    total_weight = sum(weights) or 1.0
    for signal, weight in zip(signals, weights):
        w = weight / total_weight
        action_scores[signal["action"]] = action_scores.get(signal["action"], 0.0) + signal["confidence"] * w
        evidence.extend(signal.get("evidence", []))
        metrics.update({f"{k}": v for k, v in signal.get("metrics", {}).items()})

    action = max(action_scores, key=action_scores.get)
    confidence = round(min(0.95, max(0.15, action_scores[action])), 3)
    return {"action": action, "confidence": confidence, "evidence": evidence, "metrics": metrics}
