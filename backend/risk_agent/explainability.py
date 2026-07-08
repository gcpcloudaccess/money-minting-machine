"""Critic-style explanations for investment committee debate."""

from __future__ import annotations

from risk_agent.models import CriticReport, RiskMetrics


def build_critic_report(metrics: RiskMetrics, risk_score: int) -> CriticReport:
    top_risks: list[str] = []
    hidden_risks: list[str] = []
    mitigations: list[str] = []
    disagreement_signals: list[str] = []
    rejection_conditions: list[str] = []

    if metrics.volatility > 0.30:
        top_risks.append("High annualized volatility may cause unstable position sizing and stop-loss churn.")
        mitigations.append("Reduce position size or stage entries until realized volatility compresses.")
    if abs(metrics.beta) > 1.25:
        top_risks.append("Elevated beta makes the trade sensitive to broad market selloffs.")
        mitigations.append("Pair with index hedge or lower portfolio market exposure.")
    if metrics.max_drawdown < -0.20:
        top_risks.append("Historical drawdown exceeds normal risk budget tolerance.")
        rejection_conditions.append("Reject or defer if current price action breaks below the previous drawdown support zone.")
    if metrics.cvar_95 < -0.05:
        top_risks.append("Expected tail loss is severe under the worst five percent of sessions.")
        hidden_risks.append("Tail loss can expand quickly during gap-down opens when liquidity disappears.")
    if metrics.sharpe_ratio < 0.5:
        top_risks.append("Risk-adjusted return is weak relative to volatility consumed.")
        disagreement_signals.append("A profit-focused agent may like upside, but risk-adjusted evidence is not confirming.")
    if metrics.sortino_ratio < 0.5:
        hidden_risks.append("Downside deviation is high, so positive average return may be masking loss clustering.")
    if metrics.liquidity_risk > 0.6:
        top_risks.append("Liquidity risk is high, increasing slippage and execution uncertainty.")
        mitigations.append("Use limit orders and avoid full-size orders near market open or close.")
    if metrics.concentration_risk > 0.35:
        top_risks.append("Portfolio concentration risk is elevated.")
        mitigations.append("Cap single-name exposure and rebalance correlated holdings.")
    if metrics.sector_exposure_risk > 0.45:
        hidden_risks.append("Sector exposure is crowded, so idiosyncratic risk may actually be thematic risk.")
    if metrics.market_regime_risk > 0.55:
        disagreement_signals.append("Market regime stress can override stock-specific bullish signals.")
        rejection_conditions.append("Reject fresh long exposure if benchmark trend and volatility remain stressed.")
    if metrics.sentiment_risk > 0.55:
        hidden_risks.append("Negative news or social sentiment may create headline gap risk.")
    if metrics.macro_risk > 0.55:
        hidden_risks.append("Macro stress is elevated and may pressure valuation multiples.")

    if risk_score >= 75:
        rejection_conditions.append("Reject new BUY recommendation unless another agent provides strong, recent, cross-verified evidence.")
    elif risk_score >= 45:
        mitigations.append("Prefer HOLD, smaller allocation, or hedged exposure until risk improves.")
    else:
        mitigations.append("Risk profile is acceptable, but maintain stop-loss and periodic reassessment.")

    if not top_risks:
        top_risks.append("No dominant risk factor breached high-risk thresholds.")
    if not hidden_risks:
        hidden_risks.append("No major hidden risk detected from supplied data.")
    if not disagreement_signals:
        disagreement_signals.append("Risk evidence is broadly aligned with the directional score.")
    if not rejection_conditions:
        rejection_conditions.append("Reject only if fresh data shows a volatility, liquidity, or drawdown shock.")

    critic_notes = [
        "Risk critic prioritizes downside control over raw upside.",
        "Consensus engine should down-weight bullish agents when tail loss, drawdown, or liquidity risk is elevated.",
    ]

    return CriticReport(
        top_risks=top_risks,
        hidden_risks=hidden_risks,
        mitigations=mitigations,
        disagreement_signals=disagreement_signals,
        rejection_conditions=rejection_conditions,
        critic_notes=critic_notes,
    )
