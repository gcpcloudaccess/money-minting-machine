"""Geopolitical Analyst: uses the team-contributed geopolitical_analyst engine
(vendored, unmodified, backend/geopolitical_analyst/ - calibrated scoring
across conflict/sanctions/trade domains with recency decay, corroboration
boosts, and confidence intervals).

Unlike the other integrations, this one needs an LLM extraction step first:
the engine's input is structured `Observation` objects (region, countries,
signal type, intensity, market relevance, source reliability - numbers that
don't exist in a raw headline), not free text. So this agent makes one LLM
call to extract Observations from geopolitical-tagged headlines as JSON,
then runs the engine's math deterministically, then makes a second LLM call
to narrate the result (same pattern as every other agent). Extraction
failures (bad JSON, no LLM key, no genuinely geopolitical headlines) degrade
to an empty observation list rather than raising - handled the same way as
"no relevant news" everywhere else in this codebase."""

from __future__ import annotations

import json
import re

from app.agents.base import AgentVote, AnalysisContext, BaseAgent
from app.llm.client import get_llm_client
from geopolitical_analyst import Observation, Recommendation, Signal
from geopolitical_analyst import GeopoliticalAnalyst as _GeoEngine

_ENGINE = _GeoEngine()
_REC_ACTION = {
    Recommendation.IGNORE: "HOLD",
    Recommendation.MONITOR: "HOLD",
    Recommendation.HEDGE: "SELL",
    Recommendation.REDUCE_EXPOSURE: "SELL",
    Recommendation.EVENT_DRIVEN_OPPORTUNITY: "WAIT",
}
_VALID_SIGNALS = {s.value for s in Signal}


def _clamp01(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def _extract_observations(symbol: str, news_items: list[dict], llm) -> list[Observation]:
    if not news_items:
        return []

    headlines = "\n".join(f"- {n.get('title', '')}" for n in news_items[:8])
    raw = llm.chat(
        system=(
            'Extract geopolitical risk observations (conflict, sanctions, or trade-related) from these headlines '
            'that could affect an Indian equity. Return ONLY a JSON array (no prose, no markdown fences), each '
            'item: {"region": str, "countries": [ISO3 codes], "signal": "conflict"|"sanctions"|"trade", '
            '"intensity": 0-1, "market_relevance": 0-1 (relevance to Indian equities specifically), '
            '"source_reliability": 0-1, "recency_hours": number, "evidence": short quote}. '
            "If no headline is genuinely geopolitical (conflict/sanctions/trade), return []."
        ),
        user=f"Symbol: {symbol}\nHeadlines:\n{headlines}",
        max_tokens=600,
        fallback="[]",
    )

    try:
        cleaned = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        items = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return []

    observations = []
    for item in items if isinstance(items, list) else []:
        try:
            signal = str(item.get("signal", "")).lower()
            if signal not in _VALID_SIGNALS:
                continue
            observations.append(
                Observation(
                    region=str(item.get("region", "Unknown")),
                    countries=[str(c) for c in item.get("countries", [])][:5],
                    signal=Signal(signal),
                    source_reliability=_clamp01(item.get("source_reliability", 0.6)),
                    intensity=_clamp01(item.get("intensity", 0.5)),
                    market_relevance=_clamp01(item.get("market_relevance", 0.4)),
                    recency_hours=max(0.0, float(item.get("recency_hours", 12) or 12)),
                    evidence=str(item.get("evidence", ""))[:200],
                )
            )
        except (TypeError, ValueError):
            continue
    return observations


class GeopoliticalAnalyst(BaseAgent):
    name = "Geopolitical Analyst"
    agent_type = "analyst"
    expertise = "geopolitical"

    def vote(self, ctx: AnalysisContext) -> AgentVote:
        combined_news = ctx.symbol_news + ctx.market_news
        geo_items = [n for n in combined_news if "geopolitical" in n.get("tags", [])]

        llm = get_llm_client()
        observations = _extract_observations(ctx.symbol, geo_items, llm)

        if not observations:
            reasoning = f"No material conflict, sanctions, or trade-policy signals detected for {ctx.symbol} this tick."
            return AgentVote(
                agent_name=self.name, agent_type=self.agent_type, action="HOLD", confidence=0.15,
                reasoning=reasoning, evidence=[reasoning], metrics={"n_observations": 0},
            )

        assessment = _ENGINE.assess(observations)
        action = _REC_ACTION.get(assessment.recommendation, "HOLD")
        confidence = round(max(0.15, min(0.9, assessment.overall_confidence * (0.3 + 0.7 * assessment.overall_score))), 3)

        evidence = [assessment.summary]
        evidence.extend(f"[{obs.signal.value}] {obs.region}: {obs.evidence}" for obs in observations[:4])

        metrics = {
            "overall_score": assessment.overall_score,
            "overall_confidence": assessment.overall_confidence,
            "recommendation": assessment.recommendation.value,
            "affected_countries": assessment.affected_countries,
            "n_observations": len(observations),
        }

        reasoning = llm.chat(
            system=(
                "You are a geopolitical risk analyst on a trading committee. Summarize conflict/sanctions/trade "
                "related impact on this stock in 2-3 crisp sentences."
            ),
            user=f"Symbol {ctx.symbol}. Signal: {action} (confidence {confidence}). Evidence: {' '.join(evidence)}",
            fallback=f"Geopolitical read for {ctx.symbol}: {action}. {assessment.summary}",
        )

        return AgentVote(
            agent_name=self.name, agent_type=self.agent_type, action=action, confidence=confidence,
            reasoning=reasoning, evidence=evidence, metrics=metrics,
        )
