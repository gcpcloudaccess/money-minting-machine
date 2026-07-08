from __future__ import annotations

import math


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def stdev(values: list[float]) -> float:
    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / len(values))


def safe_ratio(numerator: float, denominator: float) -> float:
    return 0.0 if abs(denominator) < 1e-12 else numerator / denominator


def ema_series(values: list[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("EMA period must be positive.")
    if not values:
        return []

    alpha = 2.0 / (period + 1.0)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * alpha + result[-1] * (1.0 - alpha))
    return result


def rsi_series(closes: list[float], period: int = 14) -> list[float | None]:
    if len(closes) <= period:
        return [None] * len(closes)

    values: list[float | None] = [None] * period
    changes = [closes[index] - closes[index - 1] for index in range(1, period + 1)]
    avg_gain = mean([max(change, 0.0) for change in changes])
    avg_loss = mean([abs(min(change, 0.0)) for change in changes])
    values.append(_rsi_from_averages(avg_gain, avg_loss))

    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        gain = max(change, 0.0)
        loss = abs(min(change, 0.0))
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
        values.append(_rsi_from_averages(avg_gain, avg_loss))

    return values


def macd_series(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[float], list[float], list[float]]:
    fast_ema = ema_series(closes, fast)
    slow_ema = ema_series(closes, slow)
    macd = [fast_value - slow_value for fast_value, slow_value in zip(fast_ema, slow_ema)]
    signal_line = ema_series(macd, signal)
    histogram = [macd_value - signal_value for macd_value, signal_value in zip(macd, signal_line)]
    return macd, signal_line, histogram


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0 and avg_gain == 0:
        return 50.0
    if avg_loss == 0:
        return 100.0
    relative_strength = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))
