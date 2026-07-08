"""
Macroeconomist agent for an investment app.

The agent turns macro observations into:
- regime labels for growth, inflation, and policy rates
- confidence scores with explainable components
- investment-relevant risks and portfolio tilts
- a JSON-serializable payload suitable for app integration

It intentionally does not fetch live data. Feed it validated observations from
your data layer, such as BEA/FRED GDP, BLS CPI/PCE, and central-bank rates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import json
import math
from typing import Any, Iterable


@dataclass(frozen=True)
class MacroObservation:
    name: str
    value: float
    unit: str
    period: str
    source: str
    as_of: str
    expected_value: float | None = None
    prior_value: float | None = None
    recency_days: int = 30
    source_quality: float = 0.9
    revision_risk: float = 0.2


@dataclass(frozen=True)
class ConfidenceScore:
    score: float
    label: str
    components: dict[str, float]
    rationale: list[str]


@dataclass(frozen=True)
class MacroSignal:
    indicator: str
    regime: str
    value: float
    confidence: ConfidenceScore
    interpretation: str
    portfolio_implication: str


@dataclass(frozen=True)
class MacroAgentResult:
    agent: str
    generated_on: str
    summary: str
    overall_confidence: ConfidenceScore
    signals: list[MacroSignal]
    risks: list[str]
    suggested_tilts: list[str]
    data_quality_notes: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


class MacroeconomistAgent:
    """Rules-based macro agent with transparent confidence scoring."""

    def __init__(self, name: str = "Diverse Financial Agent - Macroeconomist"):
        self.name = name

    def analyze(self, observations: Iterable[MacroObservation]) -> MacroAgentResult:
        obs = {item.name.lower(): item for item in observations}
        required = ["gdp_growth", "inflation", "policy_rate"]
        missing = [name for name in required if name not in obs]
        if missing:
            raise ValueError(f"Missing required observations: {', '.join(missing)}")

        gdp = obs["gdp_growth"]
        inflation = obs["inflation"]
        policy_rate = obs["policy_rate"]

        signals = [
            self._growth_signal(gdp),
            self._inflation_signal(inflation),
            self._rate_signal(policy_rate, inflation),
        ]

        alignment = self._cross_signal_alignment(gdp, inflation, policy_rate)
        overall_components = {
            "indicator_confidence": self._mean(signal.confidence.score for signal in signals),
            "cross_signal_alignment": alignment,
            "data_completeness": min(1.0, len(obs) / 5),
        }
        overall_score = self._clamp(
            0.55 * overall_components["indicator_confidence"]
            + 0.30 * overall_components["cross_signal_alignment"]
            + 0.15 * overall_components["data_completeness"]
        )
        overall_confidence = self._confidence_from_components(
            overall_components,
            rationale=[
                "Overall score blends individual indicator reliability, macro consistency, and data coverage.",
                f"Cross-signal alignment is {alignment:.2f} based on GDP, inflation, and policy-rate consistency.",
            ],
            score_override=overall_score,
        )

        risks = self._risks(gdp, inflation, policy_rate)
        tilts = self._tilts(signals)
        summary = self._summary(signals, overall_score)
        notes = self._data_quality_notes(obs.values())

        return MacroAgentResult(
            agent=self.name,
            generated_on=date.today().isoformat(),
            summary=summary,
            overall_confidence=overall_confidence,
            signals=signals,
            risks=risks,
            suggested_tilts=tilts,
            data_quality_notes=notes,
        )

    def _growth_signal(self, obs: MacroObservation) -> MacroSignal:
        if obs.value >= 3.0:
            regime = "strong_expansion"
            interpretation = "GDP growth is running above trend, supporting earnings cyclicality."
            implication = "Favor quality cyclicals and broad equity exposure, while watching overheating risk."
        elif obs.value >= 1.5:
            regime = "moderate_expansion"
            interpretation = "GDP growth is positive but not excessive, consistent with a balanced expansion."
            implication = "Maintain diversified equity exposure with a quality bias."
        elif obs.value >= 0.0:
            regime = "stall_speed"
            interpretation = "Growth is positive but fragile, increasing sensitivity to shocks."
            implication = "Lean toward defensive equity sectors and higher-quality credit."
        else:
            regime = "contraction"
            interpretation = "Negative GDP growth points to recessionary pressure."
            implication = "Reduce cyclical risk and prefer duration, cash quality, and defensive sectors."

        return MacroSignal(
            indicator="GDP growth",
            regime=regime,
            value=obs.value,
            confidence=self._indicator_confidence(obs, surprise_scale=2.0),
            interpretation=interpretation,
            portfolio_implication=implication,
        )

    def _inflation_signal(self, obs: MacroObservation) -> MacroSignal:
        if obs.value >= 5.0:
            regime = "high_inflation"
            interpretation = "Inflation is far above typical central-bank comfort zones."
            implication = "Prefer pricing-power equities, inflation-linked bonds, and real-asset exposure."
        elif obs.value >= 3.0:
            regime = "sticky_inflation"
            interpretation = "Inflation remains elevated enough to constrain policy easing."
            implication = "Keep duration moderate and emphasize companies with margin resilience."
        elif obs.value >= 1.5:
            regime = "near_target"
            interpretation = "Inflation is near a normal target range."
            implication = "Balanced stock-bond diversification has a better macro backdrop."
        else:
            regime = "disinflationary"
            interpretation = "Low inflation may reflect weaker demand or benign supply conditions."
            implication = "Longer-duration bonds and defensive growth may benefit if rates fall."

        return MacroSignal(
            indicator="Inflation",
            regime=regime,
            value=obs.value,
            confidence=self._indicator_confidence(obs, surprise_scale=1.5),
            interpretation=interpretation,
            portfolio_implication=implication,
        )

    def _rate_signal(self, rate: MacroObservation, inflation: MacroObservation) -> MacroSignal:
        real_rate = rate.value - inflation.value
        if real_rate >= 2.0:
            regime = "restrictive_policy"
            interpretation = "Real policy rates are meaningfully positive, implying tight financial conditions."
            implication = "Favor quality balance sheets, short-to-intermediate duration, and lower leverage."
        elif real_rate >= 0.0:
            regime = "mildly_restrictive"
            interpretation = "Policy is modestly restrictive after inflation adjustment."
            implication = "Use balanced exposure and avoid excessive rate-sensitive concentration."
        else:
            regime = "accommodative_policy"
            interpretation = "Real rates are negative, which can support risk assets but may feed inflation."
            implication = "Risk assets can benefit, but inflation hedges deserve a place in allocation."

        confidence = self._indicator_confidence(rate, surprise_scale=1.0)
        return MacroSignal(
            indicator="Interest rates",
            regime=regime,
            value=rate.value,
            confidence=confidence,
            interpretation=interpretation,
            portfolio_implication=implication,
        )

    def _indicator_confidence(self, obs: MacroObservation, surprise_scale: float) -> ConfidenceScore:
        recency = math.exp(-max(obs.recency_days, 0) / 120)
        revision = 1.0 - self._clamp(obs.revision_risk)
        quality = self._clamp(obs.source_quality)

        if obs.expected_value is None:
            surprise_consistency = 0.75
        else:
            surprise = abs(obs.value - obs.expected_value)
            surprise_consistency = math.exp(-surprise / max(surprise_scale, 0.1))

        if obs.prior_value is None:
            trend_stability = 0.75
        else:
            trend_stability = math.exp(-abs(obs.value - obs.prior_value) / max(surprise_scale * 1.5, 0.1))

        components = {
            "source_quality": quality,
            "recency": self._clamp(recency),
            "revision_stability": self._clamp(revision),
            "surprise_consistency": self._clamp(surprise_consistency),
            "trend_stability": self._clamp(trend_stability),
        }
        return self._confidence_from_components(
            components,
            rationale=[
                f"{obs.name} uses {obs.source} data for {obs.period}.",
                "Confidence rewards fresh, high-quality, low-revision data and penalizes large surprises.",
            ],
        )

    def _confidence_from_components(
        self,
        components: dict[str, float],
        rationale: list[str],
        score_override: float | None = None,
    ) -> ConfidenceScore:
        score = self._clamp(score_override) if score_override is not None else self._mean(components.values())
        return ConfidenceScore(
            score=round(score, 3),
            label=self._confidence_label(score),
            components={key: round(self._clamp(value), 3) for key, value in components.items()},
            rationale=rationale,
        )

    def _cross_signal_alignment(
        self,
        gdp: MacroObservation,
        inflation: MacroObservation,
        policy_rate: MacroObservation,
    ) -> float:
        alignment = 0.5
        if gdp.value >= 1.5 and inflation.value >= 3.0 and policy_rate.value >= inflation.value:
            alignment += 0.3
        if gdp.value < 1.0 and policy_rate.value > inflation.value:
            alignment -= 0.2
        if inflation.value < 2.5 and policy_rate.value > inflation.value + 2.0:
            alignment -= 0.15
        if gdp.value >= 1.5 and 1.5 <= inflation.value <= 3.5:
            alignment += 0.2
        return self._clamp(alignment)

    def _risks(
        self,
        gdp: MacroObservation,
        inflation: MacroObservation,
        policy_rate: MacroObservation,
    ) -> list[str]:
        risks: list[str] = []
        real_rate = policy_rate.value - inflation.value
        if gdp.value < 1.0:
            risks.append("Growth slowdown risk: GDP is close to stall speed.")
        if inflation.value >= 3.0:
            risks.append("Inflation persistence risk: elevated inflation can delay rate cuts.")
        if real_rate >= 2.0:
            risks.append("Policy overtightening risk: real rates are restrictive.")
        if not risks:
            risks.append("No single dominant macro risk, but data revisions and policy communication remain important.")
        return risks

    def _tilts(self, signals: list[MacroSignal]) -> list[str]:
        regimes = {signal.regime for signal in signals}
        tilts: list[str] = []
        if "strong_expansion" in regimes or "moderate_expansion" in regimes:
            tilts.append("Maintain diversified equity exposure with quality and cash-flow discipline.")
        if "high_inflation" in regimes or "sticky_inflation" in regimes:
            tilts.append("Include inflation-aware exposure such as pricing-power equities or TIPS.")
        if "restrictive_policy" in regimes:
            tilts.append("Avoid overexposure to highly levered borrowers and speculative duration.")
        if "contraction" in regimes or "stall_speed" in regimes:
            tilts.append("Increase defensive sectors, high-quality bonds, and liquidity buffers.")
        return tilts or ["Use a balanced allocation while awaiting a clearer macro signal."]

    def _summary(self, signals: list[MacroSignal], confidence: float) -> str:
        regimes = ", ".join(signal.regime for signal in signals)
        return (
            f"Macro regime mix: {regimes}. "
            f"Overall confidence is {self._confidence_label(confidence)} ({confidence:.3f})."
        )

    def _data_quality_notes(self, observations: Iterable[MacroObservation]) -> list[str]:
        notes: list[str] = []
        for obs in observations:
            if obs.recency_days > 90:
                notes.append(f"{obs.name} is older than 90 days; refresh before production use.")
            if obs.revision_risk >= 0.5:
                notes.append(f"{obs.name} has high revision risk; lower conviction until confirmed.")
            if obs.source_quality < 0.75:
                notes.append(f"{obs.name} source quality is below preferred institutional threshold.")
        return notes

    @staticmethod
    def _confidence_label(score: float) -> str:
        if score >= 0.80:
            return "high"
        if score >= 0.60:
            return "medium"
        return "low"

    @staticmethod
    def _mean(values: Iterable[float]) -> float:
        values = list(values)
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, value))


def _demo() -> None:
    agent = MacroeconomistAgent()
    result = agent.analyze(
        [
            MacroObservation(
                name="gdp_growth",
                value=2.4,
                unit="annualized_percent",
                period="latest_quarter",
                source="BEA/FRED",
                as_of=date.today().isoformat(),
                expected_value=2.1,
                prior_value=1.8,
                recency_days=25,
                source_quality=0.95,
                revision_risk=0.35,
            ),
            MacroObservation(
                name="inflation",
                value=3.1,
                unit="year_over_year_percent",
                period="latest_month",
                source="BLS/FRED",
                as_of=date.today().isoformat(),
                expected_value=3.0,
                prior_value=3.3,
                recency_days=14,
                source_quality=0.95,
                revision_risk=0.15,
            ),
            MacroObservation(
                name="policy_rate",
                value=4.5,
                unit="percent",
                period="current",
                source="Federal Reserve",
                as_of=date.today().isoformat(),
                expected_value=4.5,
                prior_value=4.5,
                recency_days=7,
                source_quality=0.98,
                revision_risk=0.05,
            ),
        ]
    )
    print(result.to_json())


if __name__ == "__main__":
    _demo()
