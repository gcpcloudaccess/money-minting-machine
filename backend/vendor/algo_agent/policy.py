from __future__ import annotations

from dataclasses import dataclass

from .data import PriceBar
from .model import ModelMetrics


@dataclass(frozen=True)
class TradePolicy:
    capital: float = 100_000.0
    account_risk_pct: float = 0.5
    max_position_pct: float = 8.0
    min_accuracy_edge: float = 0.03
    min_validation_samples: int = 40
    min_avg_dollar_volume: float = 2_000_000.0
    max_annualized_volatility: float = 0.65
    max_spread_bps: float = 25.0


@dataclass(frozen=True)
class PolicyCheck:
    status: str
    passed: bool
    reasons: list[str]


def evaluate_policy(
    bars: list[PriceBar],
    action: str,
    metrics: ModelMetrics,
    annualized_volatility: float,
    policy: TradePolicy,
) -> PolicyCheck:
    reasons: list[str] = []
    passed = True

    if action == "HOLD":
        passed = False
        reasons.append("No directional trade is proposed.")

    edge = metrics.accuracy - metrics.baseline_accuracy
    if metrics.samples < policy.min_validation_samples:
        passed = False
        reasons.append(
            f"Validation sample is too small: {metrics.samples} < {policy.min_validation_samples}."
        )
    if edge < policy.min_accuracy_edge:
        passed = False
        reasons.append(
            f"Model validation edge is too low: {edge:.2%} < {policy.min_accuracy_edge:.2%}."
        )

    avg_dollar_volume = _average_dollar_volume(bars)
    if avg_dollar_volume < policy.min_avg_dollar_volume:
        passed = False
        reasons.append(
            f"Average dollar volume is too low: {avg_dollar_volume:,.0f} < {policy.min_avg_dollar_volume:,.0f}."
        )

    if annualized_volatility > policy.max_annualized_volatility:
        passed = False
        reasons.append(
            f"Annualized volatility is too high: {annualized_volatility:.2%} > {policy.max_annualized_volatility:.2%}."
        )

    spread_bps = _proxy_spread_bps(bars)
    if spread_bps > policy.max_spread_bps:
        passed = False
        reasons.append(f"Proxy spread is too wide: {spread_bps:.1f} bps > {policy.max_spread_bps:.1f} bps.")

    if passed:
        reasons.append("All configured real-money review gates passed.")

    return PolicyCheck(
        status="APPROVED_FOR_REVIEW" if passed else "REJECTED_BY_POLICY",
        passed=passed,
        reasons=reasons,
    )


def _average_dollar_volume(bars: list[PriceBar], lookback: int = 20) -> float:
    sample = bars[-lookback:]
    return sum(bar.close * bar.volume for bar in sample) / len(sample)


def _proxy_spread_bps(bars: list[PriceBar], lookback: int = 10) -> float:
    sample = bars[-lookback:]
    values = []
    for bar in sample:
        midpoint = (bar.high + bar.low) / 2.0
        if midpoint > 0:
            values.append((bar.high - bar.low) / midpoint * 10_000.0)
    return sum(values) / len(values) if values else 10_000.0
