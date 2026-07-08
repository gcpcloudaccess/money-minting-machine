"""Sentiment Analyst: uses the team-contributed expert sentiment engine
(vendored, unmodified, backend/sentiment_analyst.py - lexicon-based polarity,
confidence, emotion, credibility, and risk scoring with negation/intensifier
handling) in place of our simpler VADER+keyword engine. Unlike the risk and
technical integrations, this one operates on the exact same input (raw
headline text) at the exact same timeframe as our own analyst, so it's a
clean replacement rather than a blend."""

from __future__ import annotations

from app.agents.base import AgentVote, AnalysisContext, BaseAgent
from app.llm.client import get_llm_client
from sentiment_analyst import ExpertSentimentAnalyst

_ENGINE = ExpertSentimentAnalyst()
_BIAS_TO_ACTION = {"bullish": "BUY", "bearish": "SELL", "neutral": "HOLD", "watch": "WAIT"}


def _headline_texts(news_items: list[dict]) -> list[str]:
    texts = []
    for n in news_items:
        text = f"{n.get('title', '')}. {n.get('summary', '')}".strip()
        if text and text != ".":
            texts.append(text)
    return texts


class SentimentAnalyst(BaseAgent):
    name = "Sentiment Analyst"
    agent_type = "analyst"
    expertise = "sentiment"

    def vote(self, ctx: AnalysisContext) -> AgentVote:
        texts = _headline_texts(ctx.symbol_news)
        if not texts:
            return AgentVote(
                agent_name=self.name, agent_type=self.agent_type, action="WAIT", confidence=0.15,
                reasoning=f"No recent news found for {ctx.symbol}.", evidence=["No recent news found."],
                metrics={"n_items": 0},
            )

        report = _ENGINE.analyze(texts, source="news", mode="balanced")
        signal = report.trading_signal
        agg = report.aggregate

        action = _BIAS_TO_ACTION.get(signal.bias, "HOLD")
        confidence = round(max(0.15, min(0.95, signal.conviction / 100.0)), 3)

        top_items = sorted(report.items, key=lambda i: abs(i.polarity), reverse=True)[:5]
        evidence = [f"[{item.label} {item.polarity:+.0f}] {item.text[:120]}" for item in top_items]
        evidence.append(
            f"Aggregate: {agg.label} polarity {agg.polarity:+.1f}, confidence {agg.confidence:.0f}%, "
            f"credibility {agg.credibility_score:.0f}%, risk {agg.risk_score:.0f}%, dominant emotion {agg.top_emotion}."
        )

        metrics = {
            "polarity": agg.polarity,
            "confidence_pct": agg.confidence,
            "credibility_score": agg.credibility_score,
            "risk_score": agg.risk_score,
            "top_emotion": agg.top_emotion,
            "n_items": len(texts),
            "positive_count": agg.positive_count,
            "negative_count": agg.negative_count,
            "conviction": signal.conviction,
        }

        llm = get_llm_client()
        evidence_txt = " ".join(evidence)
        reasoning = llm.chat(
            system=(
                "You are the Sentiment Analyst on a trading committee, using a lexicon-based engine with emotion, "
                "credibility, and risk scoring (not just raw polarity). Summarize crowd mood in 2-3 crisp sentences, "
                "noting the credibility/risk qualifiers if they temper the raw sentiment."
            ),
            user=f"Symbol {ctx.symbol}. Signal: {action} (confidence {confidence}). Evidence: {evidence_txt}",
            fallback=f"Sentiment read for {ctx.symbol}: {action}. {evidence_txt}",
        )

        return AgentVote(
            agent_name=self.name, agent_type=self.agent_type, action=action, confidence=confidence,
            reasoning=reasoning, evidence=evidence, metrics=metrics,
        )
