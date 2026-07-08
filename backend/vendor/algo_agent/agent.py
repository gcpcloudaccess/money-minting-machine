from __future__ import annotations

from dataclasses import asdict, dataclass

from .data import PriceBar
from .features import FEATURE_NAMES, build_feature_rows
from .model import ModelMetrics, train_model
from .policy import PolicyCheck, TradePolicy, evaluate_policy
from .risk import annualized_volatility, build_risk_plan, confidence_from_probability


@dataclass(frozen=True)
class Recommendation:
    symbol: str
    action: str
    confidence: float
    model_probability_up: float
    entry: float
    stop_loss: float
    take_profit: float
    position_size_pct: float
    shares: int
    notional: float
    capital_at_risk: float
    risk_reward: float
    latest_date: str
    review_status: str
    policy_check: PolicyCheck
    model_metrics: ModelMetrics
    top_features: list[dict[str, float | str]]
    rationale: list[str]
    disclaimer: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["model_metrics"] = asdict(self.model_metrics)
        return data


def recommend(
    bars: list[PriceBar],
    symbol: str,
    horizon: int = 5,
    buy_threshold: float = 0.58,
    sell_threshold: float = 0.42,
    policy: TradePolicy | None = None,
) -> Recommendation:
    policy = policy or TradePolicy()
    rows = build_feature_rows(bars, horizon=horizon)
    labeled = [row for row in rows if row.label is not None]
    x_rows = [row.features for row in labeled]
    y = [int(row.label) for row in labeled]
    trained = train_model(x_rows, y)

    latest = rows[-1]
    probability = trained.predict_probability(latest.features)
    closes = [bar.close for bar in bars]
    sma_10 = sum(closes[-10:]) / 10.0
    sma_30 = sum(closes[-30:]) / 30.0
    volatility = annualized_volatility(closes)

    trend_positive = sma_10 > sma_30 and latest.close > sma_30
    trend_negative = sma_10 < sma_30 and latest.close < sma_30

    if probability >= buy_threshold and trend_positive:
        action = "BUY"
    elif probability <= sell_threshold and trend_negative:
        action = "SELL"
    else:
        action = "HOLD"

    risk = build_risk_plan(
        bars,
        action,
        capital=policy.capital,
        account_risk_pct=policy.account_risk_pct,
        max_position_pct=policy.max_position_pct,
    )
    policy_check = evaluate_policy(bars, action, trained.metrics, volatility, policy)
    rationale = _build_rationale(probability, action, trend_positive, trend_negative, volatility)
    top_features = _top_feature_contributions(
        FEATURE_NAMES,
        latest.features,
        trained.scaler.transform_one(latest.features),
        trained.classifier.weights,
    )

    return Recommendation(
        symbol=symbol.upper(),
        action=action,
        confidence=confidence_from_probability(probability),
        model_probability_up=round(probability, 4),
        entry=round(latest.close, 2),
        stop_loss=risk.stop_loss,
        take_profit=risk.take_profit,
        position_size_pct=risk.position_size_pct,
        shares=risk.shares,
        notional=risk.notional,
        capital_at_risk=risk.capital_at_risk,
        risk_reward=risk.risk_reward,
        latest_date=latest.date,
        review_status=policy_check.status,
        policy_check=policy_check,
        model_metrics=trained.metrics,
        top_features=top_features,
        rationale=rationale,
        disclaimer="Research output only. Not financial advice or an execution instruction.",
    )


def _build_rationale(
    probability: float,
    action: str,
    trend_positive: bool,
    trend_negative: bool,
    volatility: float,
) -> list[str]:
    reasons: list[str] = []
    if action == "BUY":
        reasons.append("Model probability is above the buy threshold.")
        reasons.append("Short trend is above long trend.")
    elif action == "SELL":
        reasons.append("Model probability is below the sell threshold.")
        reasons.append("Short trend is below long trend.")
    else:
        reasons.append("Model and trend confirmation are mixed, so the agent avoids a directional call.")

    if volatility > 0.45:
        reasons.append("Recent volatility is elevated; reduce size or wait for cleaner conditions.")
    elif volatility < 0.18:
        reasons.append("Recent volatility is controlled relative to the default risk budget.")
    else:
        reasons.append("Recent volatility is moderate.")

    reasons.append(f"Raw probability of an up move over the forecast horizon is {probability:.2%}.")
    return reasons


def _top_feature_contributions(
    names: list[str],
    raw_features: list[float],
    scaled_features: list[float],
    weights: list[float],
    limit: int = 5,
) -> list[dict[str, float | str]]:
    contributions = [
        {
            "feature": name,
            "value": round(raw, 6),
            "contribution": round(scaled * weight, 6),
        }
        for name, raw, scaled, weight in zip(names, raw_features, scaled_features, weights)
    ]
    contributions.sort(key=lambda item: abs(float(item["contribution"])), reverse=True)
    return contributions[:limit]
