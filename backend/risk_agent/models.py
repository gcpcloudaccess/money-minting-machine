"""Typed models used by the risk assessment agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


Recommendation = Literal["BUY", "HOLD", "SELL"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "EXTREME"]


@dataclass(frozen=True)
class OHLCVBar:
    """Single OHLCV market data bar."""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class PortfolioPosition:
    """Portfolio position metadata used for exposure and concentration risk."""

    symbol: str
    weight: float
    sector: str | None = None


@dataclass(frozen=True)
class RiskAssessmentInput:
    """Input bundle for a risk assessment run."""

    symbol: str
    price_data: list[OHLCVBar]
    benchmark_data: list[OHLCVBar]
    portfolio: list[PortfolioPosition] = field(default_factory=list)
    fundamentals: dict[str, Any] = field(default_factory=dict)
    news_sentiment: dict[str, float] = field(default_factory=dict)
    macro_indicators: dict[str, float] = field(default_factory=dict)
    risk_free_rate: float = 0.04


@dataclass(frozen=True)
class DirectionalConfidence:
    """Directional confidence scores that sum to one."""

    buy: float
    hold: float
    sell: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class RiskMetrics:
    """Core market and portfolio risk metrics."""

    volatility: float
    beta: float
    max_drawdown: float
    var_95: float
    cvar_95: float
    sharpe_ratio: float
    sortino_ratio: float
    downside_deviation: float
    liquidity_risk: float
    concentration_risk: float
    correlation_risk: float
    sector_exposure_risk: float
    risk_adjusted_return: float
    market_regime_risk: float
    sentiment_risk: float
    macro_risk: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class CriticReport:
    """Risk critic commentary for debate and consensus layers."""

    top_risks: list[str]
    hidden_risks: list[str]
    mitigations: list[str]
    disagreement_signals: list[str]
    rejection_conditions: list[str]
    critic_notes: list[str]

    def to_dict(self) -> dict[str, list[str]]:
        return asdict(self)


@dataclass(frozen=True)
class RiskAssessmentResult:
    """JSON-compatible final output from the agent."""

    agent: str
    symbol: str
    recommendation: Recommendation
    directional_confidence: DirectionalConfidence
    risk_score: int
    risk_level: RiskLevel
    metrics: RiskMetrics
    score_explanations: dict[str, str]
    top_risks: list[str]
    hidden_risks: list[str]
    mitigations: list[str]
    critic_notes: list[str]
    disagreement_signals: list[str]
    rejection_conditions: list[str]
    memory_comparison: dict[str, Any]
    reliability_score: float | None
    consensus_payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


@dataclass(frozen=True)
class HistoricalDecision:
    """Stored decision with optional realized outcome for reliability scoring."""

    symbol: str
    date: str
    recommendation: Recommendation
    risk_score: int
    metrics: dict[str, float]
    realized_return: float | None = None
