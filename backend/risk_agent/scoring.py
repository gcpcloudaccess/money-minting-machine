"""Risk scoring and directional confidence logic."""

from __future__ import annotations

from risk_agent.models import DirectionalConfidence, Recommendation, RiskLevel, RiskMetrics


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def risk_level(score: int) -> RiskLevel:
    if score >= 85:
        return "EXTREME"
    if score >= 65:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


def score_metrics(metrics: RiskMetrics) -> tuple[int, dict[str, str]]:
    """Convert raw metrics into a 0..100 severity score.

    The model is transparent by design: each major risk family contributes a
    bounded number of points, making it usable in forensic investment logs.
    """

    components: dict[str, float] = {}
    components["volatility"] = clamp((metrics.volatility - 0.12) / 0.38, 0.0, 1.0) * 16
    components["beta"] = clamp((abs(metrics.beta) - 0.8) / 1.0, 0.0, 1.0) * 11
    components["drawdown"] = clamp(abs(metrics.max_drawdown) / 0.35, 0.0, 1.0) * 15
    components["tail_loss"] = clamp(abs(metrics.cvar_95) / 0.08, 0.0, 1.0) * 12
    components["sharpe"] = clamp((1.2 - metrics.sharpe_ratio) / 2.2, 0.0, 1.0) * 11
    components["sortino"] = clamp((1.2 - metrics.sortino_ratio) / 2.2, 0.0, 1.0) * 7
    components["liquidity"] = metrics.liquidity_risk * 7
    components["concentration"] = metrics.concentration_risk * 6
    components["correlation"] = metrics.correlation_risk * 4
    components["sector"] = metrics.sector_exposure_risk * 4
    components["regime"] = metrics.market_regime_risk * 4
    components["sentiment"] = metrics.sentiment_risk * 2
    components["macro"] = metrics.macro_risk * 1

    score = int(round(clamp(sum(components.values()), 0.0, 100.0)))
    explanations = {
        "volatility": f"Annualized volatility contributes {components['volatility']:.1f} risk points.",
        "beta": f"Beta contributes {components['beta']:.1f} risk points based on market sensitivity.",
        "drawdown": f"Maximum drawdown contributes {components['drawdown']:.1f} risk points.",
        "tail_loss": f"CVaR contributes {components['tail_loss']:.1f} risk points from left-tail losses.",
        "risk_adjusted_return": (
            f"Sharpe and Sortino together contribute "
            f"{components['sharpe'] + components['sortino']:.1f} risk points."
        ),
        "portfolio_structure": (
            f"Liquidity, concentration, correlation, and sector exposure contribute "
            f"{components['liquidity'] + components['concentration'] + components['correlation'] + components['sector']:.1f} risk points."
        ),
        "external_context": (
            f"Market regime, sentiment, and macro inputs contribute "
            f"{components['regime'] + components['sentiment'] + components['macro']:.1f} risk points."
        ),
    }
    return score, explanations


def directional_confidence(score: int, metrics: RiskMetrics) -> DirectionalConfidence:
    """Create BUY/HOLD/SELL confidence from risk severity and return quality."""

    return_quality = clamp((metrics.sharpe_ratio + metrics.sortino_ratio) / 4.0, -0.25, 0.75)
    if score > 75:
        buy = 0.08 + max(0.0, return_quality) * 0.10
        hold = 0.24 + max(0.0, return_quality) * 0.12
        sell = 1.0 - buy - hold
    elif score >= 45:
        sell = 0.18 + clamp((score - 45) / 30, 0.0, 1.0) * 0.20
        buy = 0.18 + max(0.0, return_quality) * 0.22
        hold = 1.0 - buy - sell
    else:
        sell = 0.08 + clamp(score / 45, 0.0, 1.0) * 0.13
        hold = 0.28 + clamp(score / 45, 0.0, 1.0) * 0.18
        buy = 1.0 - hold - sell
        if metrics.sharpe_ratio < 0.4:
            shift = min(0.15, buy * 0.35)
            buy -= shift
            hold += shift

    total = buy + hold + sell
    buy = round(buy / total, 4)
    hold = round(hold / total, 4)
    sell = round(1.0 - buy - hold, 4)
    return DirectionalConfidence(buy=buy, hold=hold, sell=sell)


def recommendation_from_confidence(confidence: DirectionalConfidence) -> Recommendation:
    values = {"BUY": confidence.buy, "HOLD": confidence.hold, "SELL": confidence.sell}
    return max(values, key=values.get)  # type: ignore[return-value]


def consensus_payload(score: int, confidence: DirectionalConfidence, level: RiskLevel) -> dict[str, object]:
    if score >= 75:
        stance = "risk_reject_or_reduce"
    elif score >= 45:
        stance = "risk_caution"
    else:
        stance = "risk_supportive"
    evidence_strength = "high" if max(confidence.to_dict().values()) >= 0.70 else "medium"
    return {
        "stance": stance,
        "confidence": round(max(confidence.to_dict().values()), 4),
        "evidence_strength": evidence_strength,
        "risk_level": level,
        "directional_weighting": confidence.to_dict(),
    }
