"""Calibration utilities for bounded confidence scores."""

from __future__ import annotations

import math


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def logistic(value: float, midpoint: float = 0.5, steepness: float = 8.0) -> float:
    return 1.0 / (1.0 + math.exp(-steepness * (value - midpoint)))


def recency_decay(hours: float, half_life_hours: float) -> float:
    if hours <= 0:
        return 1.0
    return 0.5 ** (hours / half_life_hours)


def corroboration_boost(count: int) -> float:
    if count <= 1:
        return 0.0
    return clamp(math.log1p(count - 1) / math.log(8), 0.0, 1.0)


def confidence_interval(score: float, confidence: float) -> tuple[float, float]:
    width = (1.0 - confidence) * 0.32 + 0.025
    return round(clamp(score - width), 4), round(clamp(score + width), 4)


def precision(value: float) -> float:
    return round(clamp(value), 4)

