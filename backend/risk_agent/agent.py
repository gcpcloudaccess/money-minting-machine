"""Main Risk Assessment Analyst Agent."""

from __future__ import annotations

from datetime import date

from risk_agent.explainability import build_critic_report
from risk_agent.memory import DecisionMemory
from risk_agent.metrics import calculate_metrics
from risk_agent.models import HistoricalDecision, RiskAssessmentInput, RiskAssessmentResult
from risk_agent.scoring import (
    consensus_payload,
    directional_confidence,
    recommendation_from_confidence,
    risk_level,
    score_metrics,
)


class RiskAssessmentAgent:
    """Analyze risk and emit consensus-ready directional confidence.

    The agent acts as a risk-focused specialist in a larger investment
    committee. It does not try to maximize profit alone; it identifies whether
    the proposed asset can be held inside a portfolio without unacceptable
    volatility, drawdown, liquidity, concentration, or external-context risk.
    """

    name = "RiskAssessmentAgent"

    def __init__(self, memory: DecisionMemory | None = None) -> None:
        self.memory = memory or DecisionMemory()

    def assess(self, request: RiskAssessmentInput, store_decision: bool = True) -> RiskAssessmentResult:
        self._validate(request)
        metrics = calculate_metrics(
            price_data=request.price_data,
            benchmark_data=request.benchmark_data,
            portfolio=request.portfolio,
            risk_free_rate=request.risk_free_rate,
            news_sentiment=request.news_sentiment,
            macro_indicators=request.macro_indicators,
        )
        score, explanations = score_metrics(metrics)
        level = risk_level(score)
        confidence = directional_confidence(score, metrics)
        recommendation = recommendation_from_confidence(confidence)
        critic = build_critic_report(metrics, score)
        memory_comparison = self.memory.compare(request.symbol, score, metrics)
        reliability = self.memory.reliability_score()

        result = RiskAssessmentResult(
            agent=self.name,
            symbol=request.symbol,
            recommendation=recommendation,
            directional_confidence=confidence,
            risk_score=score,
            risk_level=level,
            metrics=metrics,
            score_explanations=explanations,
            top_risks=critic.top_risks,
            hidden_risks=critic.hidden_risks,
            mitigations=critic.mitigations,
            critic_notes=critic.critic_notes,
            disagreement_signals=critic.disagreement_signals,
            rejection_conditions=critic.rejection_conditions,
            memory_comparison=memory_comparison,
            reliability_score=reliability,
            consensus_payload=consensus_payload(score, confidence, level),
        )

        if store_decision:
            self.memory.add(
                HistoricalDecision(
                    symbol=request.symbol,
                    date=date.today().isoformat(),
                    recommendation=recommendation,
                    risk_score=score,
                    metrics=metrics.to_dict(),
                )
            )

        return result

    @staticmethod
    def _validate(request: RiskAssessmentInput) -> None:
        if len(request.price_data) < 3:
            raise ValueError("price_data must contain at least three OHLCV bars.")
        if len(request.benchmark_data) < 3:
            raise ValueError("benchmark_data must contain at least three OHLCV bars.")
        if any(bar.close <= 0 for bar in request.price_data + request.benchmark_data):
            raise ValueError("All close prices must be positive.")
        total_weight = sum(abs(position.weight) for position in request.portfolio)
        if request.portfolio and total_weight == 0:
            raise ValueError("Portfolio weights cannot all be zero.")
