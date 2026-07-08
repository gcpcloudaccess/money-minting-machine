from __future__ import annotations

import math
from dataclasses import dataclass

from .data import PriceBar


@dataclass(frozen=True)
class RiskPlan:
    stop_loss: float
    take_profit: float
    position_size_pct: float
    shares: int
    notional: float
    capital_at_risk: float
    risk_reward: float
    atr: float


def average_true_range(bars: list[PriceBar], period: int = 14) -> float:
    if len(bars) < period + 1:
        raise ValueError("Not enough bars to calculate ATR.")
    ranges: list[float] = []
    for index in range(len(bars) - period, len(bars)):
        current = bars[index]
        previous_close = bars[index - 1].close
        ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous_close),
                abs(current.low - previous_close),
            )
        )
    return sum(ranges) / len(ranges)


def build_risk_plan(
    bars: list[PriceBar],
    action: str,
    capital: float = 100_000.0,
    account_risk_pct: float = 1.0,
    max_position_pct: float = 12.0,
) -> RiskPlan:
    entry = bars[-1].close
    atr = average_true_range(bars)
    stop_distance = max(1.8 * atr, entry * 0.015)
    target_distance = 2.4 * stop_distance

    if action == "SELL":
        stop_loss = entry + stop_distance
        take_profit = entry - target_distance
    else:
        stop_loss = entry - stop_distance
        take_profit = entry + target_distance

    per_share_risk_pct = abs(entry - stop_loss) / entry * 100.0
    position_size_pct = min(max_position_pct, account_risk_pct / per_share_risk_pct * 100.0)
    if action == "HOLD":
        position_size_pct = 0.0
    notional = capital * position_size_pct / 100.0
    shares = int(notional // entry) if entry > 0 and action != "HOLD" else 0
    notional = shares * entry
    capital_at_risk = shares * abs(entry - stop_loss)

    return RiskPlan(
        stop_loss=round(stop_loss, 2),
        take_profit=round(take_profit, 2),
        position_size_pct=round(max(0.0, position_size_pct), 2),
        shares=shares,
        notional=round(notional, 2),
        capital_at_risk=round(capital_at_risk, 2),
        risk_reward=round(abs(take_profit - entry) / abs(entry - stop_loss), 2),
        atr=round(atr, 4),
    )


def confidence_from_probability(probability: float) -> float:
    return round(0.5 + abs(probability - 0.5), 4)


def annualized_volatility(closes: list[float], lookback: int = 20) -> float:
    if len(closes) <= lookback:
        return 0.0
    returns = []
    for index in range(len(closes) - lookback, len(closes)):
        returns.append((closes[index] - closes[index - 1]) / closes[index - 1])
    avg = sum(returns) / len(returns)
    variance = sum((value - avg) ** 2 for value in returns) / len(returns)
    return math.sqrt(variance) * math.sqrt(252)
