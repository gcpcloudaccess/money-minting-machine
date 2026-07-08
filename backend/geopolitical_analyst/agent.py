"""Expert geopolitical analyst agent."""

from __future__ import annotations

from .calibration import precision
from .models import Assessment, Observation, Recommendation, Signal
from .scoring import score_domain


class GeopoliticalAnalyst:
    """Scores geopolitical signals for trading and risk workflows."""

    def assess(self, observations: list[Observation]) -> Assessment:
        domain_scores = {
            signal: score_domain(signal, observations)
            for signal in (Signal.CONFLICT, Signal.SANCTIONS, Signal.TRADE)
        }
        overall_score = self._overall_score(domain_scores)
        overall_confidence = self._overall_confidence(domain_scores)
        return Assessment(
            overall_score=overall_score,
            overall_confidence=overall_confidence,
            recommendation=self._recommend(overall_score, overall_confidence),
            domain_scores=domain_scores,
            affected_regions=sorted({item.region for item in observations}),
            affected_countries=sorted({country for item in observations for country in item.countries}),
            affected_asset_classes=sorted({asset for item in observations for asset in item.asset_classes}),
            summary=self._summary(domain_scores, overall_score, overall_confidence),
        )

    @staticmethod
    def _overall_score(domain_scores: dict[Signal, object]) -> float:
        scores = [score.score for score in domain_scores.values()]
        if not scores:
            return 0.0
        # Blend the average with the max so acute single-domain shocks remain visible.
        return precision(0.45 * (sum(scores) / len(scores)) + 0.55 * max(scores))

    @staticmethod
    def _overall_confidence(domain_scores: dict[Signal, object]) -> float:
        active = [score for score in domain_scores.values() if score.score > 0]
        if not active:
            return 0.0
        weighted = sum(score.confidence * max(score.score, 0.05) for score in active)
        denominator = sum(max(score.score, 0.05) for score in active)
        return precision(weighted / denominator)

    @staticmethod
    def _recommend(score: float, confidence: float) -> Recommendation:
        if score < 0.20:
            return Recommendation.IGNORE
        if score < 0.45:
            return Recommendation.MONITOR
        if score >= 0.78 and confidence >= 0.64:
            return Recommendation.REDUCE_EXPOSURE
        if score >= 0.58:
            return Recommendation.HEDGE
        return Recommendation.EVENT_DRIVEN_OPPORTUNITY

    @staticmethod
    def _summary(domain_scores: dict[Signal, object], score: float, confidence: float) -> str:
        leader = max(domain_scores.values(), key=lambda item: item.score)
        if leader.score == 0:
            return "No actionable geopolitical signals were supplied."
        return (
            f"Overall geopolitical risk is {score:.4f} with {confidence:.4f} confidence. "
            f"Primary driver is {leader.signal.value} at {leader.score:.4f} "
            f"over {GeopoliticalAnalyst._article(leader.horizon.value)} {leader.horizon.value} horizon."
        )

    @staticmethod
    def _article(word: str) -> str:
        return "an" if word[:1].lower() in {"a", "e", "i", "o", "u"} else "a"
