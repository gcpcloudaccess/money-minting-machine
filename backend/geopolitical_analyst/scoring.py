"""Domain scoring logic for conflicts, sanctions, and trade risk."""

from __future__ import annotations

from collections.abc import Iterable

from .calibration import (
    clamp,
    confidence_interval,
    corroboration_boost,
    logistic,
    precision,
    recency_decay,
)
from .models import DomainScore, FactorContribution, Observation, Signal, TimeHorizon


DOMAIN_WEIGHTS: dict[Signal, dict[str, float]] = {
    Signal.CONFLICT: {
        "source_reliability": 0.18,
        "intensity": 0.24,
        "market_relevance": 0.20,
        "recency": 0.11,
        "corroboration": 0.09,
        "novelty": 0.06,
        "escalation_velocity": 0.12,
    },
    Signal.SANCTIONS: {
        "source_reliability": 0.20,
        "intensity": 0.14,
        "market_relevance": 0.20,
        "recency": 0.08,
        "corroboration": 0.10,
        "novelty": 0.05,
        "policy_specificity": 0.23,
    },
    Signal.TRADE: {
        "source_reliability": 0.16,
        "intensity": 0.17,
        "market_relevance": 0.24,
        "recency": 0.08,
        "corroboration": 0.08,
        "novelty": 0.07,
        "policy_specificity": 0.12,
        "escalation_velocity": 0.08,
    },
}


HALF_LIFE_BY_SIGNAL = {
    Signal.CONFLICT: 36.0,
    Signal.SANCTIONS: 96.0,
    Signal.TRADE: 120.0,
}


def score_domain(signal: Signal, observations: Iterable[Observation]) -> DomainScore:
    signal_observations = [item for item in observations if item.signal == signal]
    if not signal_observations:
        return _empty_score(signal)

    weighted_scores = []
    confidence_inputs = []
    all_drivers: list[FactorContribution] = []
    evidence: list[str] = []

    for observation in signal_observations:
        factors = _factors(observation)
        drivers = _drivers(signal, factors)
        raw = sum(driver.contribution for driver in drivers)
        score = logistic(raw, midpoint=0.48, steepness=7.2)
        weighted_scores.append(score * _observation_weight(observation))
        confidence_inputs.append(_confidence(observation))
        all_drivers.extend(drivers)
        evidence.append(observation.evidence)

    denominator = sum(_observation_weight(item) for item in signal_observations)
    aggregate_score = precision(sum(weighted_scores) / denominator)
    confidence = precision(sum(confidence_inputs) / len(confidence_inputs))
    lower, upper = confidence_interval(aggregate_score, confidence)

    return DomainScore(
        signal=signal,
        score=aggregate_score,
        confidence=confidence,
        lower_bound=lower,
        upper_bound=upper,
        horizon=_horizon(signal, signal_observations),
        drivers=_top_drivers(all_drivers),
        evidence=evidence[:8],
    )


def _empty_score(signal: Signal) -> DomainScore:
    return DomainScore(
        signal=signal,
        score=0.0,
        confidence=0.0,
        lower_bound=0.0,
        upper_bound=0.0,
        horizon=TimeHorizon.STRATEGIC,
        drivers=[],
        evidence=[],
    )


def _factors(observation: Observation) -> dict[str, float]:
    return {
        "source_reliability": clamp(observation.source_reliability),
        "intensity": clamp(observation.intensity),
        "market_relevance": clamp(observation.market_relevance),
        "recency": recency_decay(observation.recency_hours, HALF_LIFE_BY_SIGNAL[observation.signal]),
        "corroboration": corroboration_boost(observation.corroboration_count),
        "novelty": clamp(observation.novelty),
        "escalation_velocity": clamp(observation.escalation_velocity),
        "policy_specificity": clamp(observation.policy_specificity),
    }


def _drivers(signal: Signal, factors: dict[str, float]) -> list[FactorContribution]:
    weights = DOMAIN_WEIGHTS[signal]
    return [
        FactorContribution(
            name=name,
            value=precision(factors[name]),
            weight=weight,
            contribution=precision(factors[name] * weight),
        )
        for name, weight in weights.items()
    ]


def _observation_weight(observation: Observation) -> float:
    return 0.35 + 0.45 * clamp(observation.source_reliability) + 0.20 * clamp(observation.market_relevance)


def _confidence(observation: Observation) -> float:
    reliability = clamp(observation.source_reliability)
    corroboration = corroboration_boost(observation.corroboration_count)
    evidence_specificity = max(clamp(observation.policy_specificity), clamp(observation.intensity))
    recency = recency_decay(observation.recency_hours, HALF_LIFE_BY_SIGNAL[observation.signal] * 2.0)
    return clamp(
        0.42 * reliability
        + 0.20 * corroboration
        + 0.18 * evidence_specificity
        + 0.12 * recency
        + 0.08 * clamp(observation.market_relevance)
    )


def _horizon(signal: Signal, observations: list[Observation]) -> TimeHorizon:
    newest = min(item.recency_hours for item in observations)
    velocity = max(item.escalation_velocity for item in observations)
    if signal == Signal.CONFLICT and newest <= 12 and velocity >= 0.68:
        return TimeHorizon.INTRADAY
    if newest <= 48:
        return TimeHorizon.SHORT_TERM
    if newest <= 168:
        return TimeHorizon.SWING
    return TimeHorizon.STRATEGIC


def _top_drivers(drivers: list[FactorContribution]) -> list[FactorContribution]:
    by_name: dict[str, FactorContribution] = {}
    for driver in drivers:
        current = by_name.get(driver.name)
        if current is None or driver.contribution > current.contribution:
            by_name[driver.name] = driver
    return sorted(by_name.values(), key=lambda item: item.contribution, reverse=True)[:5]

