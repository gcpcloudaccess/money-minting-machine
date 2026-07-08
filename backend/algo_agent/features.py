from __future__ import annotations

import math
from dataclasses import dataclass

from .data import PriceBar


@dataclass(frozen=True)
class FeatureRow:
    date: str
    close: float
    features: list[float]
    label: int | None


FEATURE_NAMES = [
    "ret_1",
    "ret_5",
    "ret_10",
    "sma_10_ratio",
    "sma_30_ratio",
    "volatility_20",
    "rsi_14",
    "volume_ratio_20",
    "range_ratio",
    "drawdown_60",
]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    avg = _mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / len(values))


def _safe_ratio(numerator: float, denominator: float) -> float:
    if abs(denominator) < 1e-12:
        return 0.0
    return numerator / denominator


def build_feature_rows(
    bars: list[PriceBar],
    horizon: int = 5,
    min_history: int = 65,
    label_threshold: float = 0.002,
) -> list[FeatureRow]:
    if len(bars) <= min_history + horizon:
        raise ValueError("Not enough bars for feature generation.")

    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    rows: list[FeatureRow] = []

    for index in range(min_history, len(bars)):
        close = closes[index]
        returns = [
            _safe_ratio(closes[position] - closes[position - 1], closes[position - 1])
            for position in range(index - 20, index + 1)
        ]
        ret_1 = returns[-1]
        ret_5 = _safe_ratio(close - closes[index - 5], closes[index - 5])
        ret_10 = _safe_ratio(close - closes[index - 10], closes[index - 10])
        sma_10 = _mean(closes[index - 9 : index + 1])
        sma_30 = _mean(closes[index - 29 : index + 1])
        volatility_20 = _std(returns[-20:]) * math.sqrt(252)

        changes = [closes[pos] - closes[pos - 1] for pos in range(index - 13, index + 1)]
        gains = [max(change, 0.0) for change in changes]
        losses = [abs(min(change, 0.0)) for change in changes]
        rs = _safe_ratio(_mean(gains), _mean(losses))
        rsi_14 = 100.0 - (100.0 / (1.0 + rs)) if rs > 0 else 50.0

        volume_ratio_20 = _safe_ratio(volumes[index], _mean(volumes[index - 19 : index + 1])) - 1.0
        range_ratio = _safe_ratio(bars[index].high - bars[index].low, close)
        high_60 = max(closes[index - 59 : index + 1])
        drawdown_60 = _safe_ratio(close - high_60, high_60)

        label = None
        if index + horizon < len(bars):
            future_return = _safe_ratio(closes[index + horizon] - close, close)
            label = 1 if future_return > label_threshold else 0

        rows.append(
            FeatureRow(
                date=bars[index].date,
                close=close,
                features=[
                    ret_1,
                    ret_5,
                    ret_10,
                    _safe_ratio(close, sma_10) - 1.0,
                    _safe_ratio(close, sma_30) - 1.0,
                    volatility_20,
                    rsi_14 / 100.0,
                    volume_ratio_20,
                    range_ratio,
                    drawdown_60,
                ],
                label=label,
            )
        )

    return rows
