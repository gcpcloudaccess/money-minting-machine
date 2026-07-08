"""Typed data structures for geopolitical risk assessment."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Signal(str, Enum):
    CONFLICT = "conflict"
    SANCTIONS = "sanctions"
    TRADE = "trade"


class TimeHorizon(str, Enum):
    INTRADAY = "intraday"
    SHORT_TERM = "short_term"
    SWING = "swing"
    STRATEGIC = "strategic"


class Recommendation(str, Enum):
    IGNORE = "ignore"
    MONITOR = "monitor"
    HEDGE = "hedge"
    REDUCE_EXPOSURE = "reduce_exposure"
    EVENT_DRIVEN_OPPORTUNITY = "event_driven_opportunity"


@dataclass(frozen=True)
class Observation:
    region: str
    countries: list[str]
    signal: Signal
    source_reliability: float
    intensity: float
    market_relevance: float
    recency_hours: float
    evidence: str
    asset_classes: list[str] = field(default_factory=list)
    corroboration_count: int = 1
    novelty: float = 0.5
    escalation_velocity: float = 0.5
    policy_specificity: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FactorContribution:
    name: str
    value: float
    weight: float
    contribution: float


@dataclass(frozen=True)
class DomainScore:
    signal: Signal
    score: float
    confidence: float
    lower_bound: float
    upper_bound: float
    horizon: TimeHorizon
    drivers: list[FactorContribution]
    evidence: list[str]


@dataclass(frozen=True)
class Assessment:
    overall_score: float
    overall_confidence: float
    recommendation: Recommendation
    domain_scores: dict[Signal, DomainScore]
    affected_regions: list[str]
    affected_countries: list[str]
    affected_asset_classes: list[str]
    summary: str

