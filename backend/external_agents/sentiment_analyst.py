"""
Expert sentiment analyst for news, social media, and market commentary.

This module is dependency-free and designed to be embedded in trading,
monitoring, or research apps. It produces high-resolution polarity,
confidence, intensity, emotion, risk, and evidence scores.

Important: sentiment is only one input to a trading decision. Do not use this
module as the sole basis for placing trades.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
import re
from typing import Dict, Iterable, List, Literal, Optional, Sequence


SourceType = Literal["news", "social", "markets", "general"]
Mode = Literal["balanced", "strict", "sensitive"]
SentimentLabel = Literal["positive", "negative", "neutral"]
TradingBias = Literal["bullish", "bearish", "neutral", "watch"]


POSITIVE_LEXICON: Dict[str, float] = {
    "accelerate": 2.0,
    "accelerated": 2.0,
    "approval": 1.7,
    "approved": 1.8,
    "amazing": 2.6,
    "beat": 2.1,
    "beats": 2.1,
    "best": 2.4,
    "breakthrough": 2.6,
    "bullish": 2.8,
    "buyback": 2.1,
    "confident": 1.8,
    "expand": 1.7,
    "expanded": 1.7,
    "excellent": 2.8,
    "gain": 2.1,
    "gains": 2.1,
    "great": 2.3,
    "growth": 2.2,
    "happy": 2.1,
    "improve": 1.8,
    "improved": 1.8,
    "improving": 1.7,
    "love": 2.7,
    "margin": 1.0,
    "outperform": 2.4,
    "profit": 2.2,
    "profitable": 2.3,
    "promising": 1.9,
    "raise": 1.8,
    "raised": 1.9,
    "record": 1.6,
    "rebound": 2.1,
    "recovered": 2.0,
    "recovery": 2.0,
    "relief": 1.6,
    "resilient": 1.9,
    "secure": 1.6,
    "strong": 1.8,
    "stronger": 1.9,
    "success": 2.0,
    "successful": 2.2,
    "support": 1.5,
    "surge": 2.5,
    "surged": 2.5,
    "upgrade": 2.1,
    "upgraded": 2.1,
    "win": 2.0,
    "wins": 2.0,
}


NEGATIVE_LEXICON: Dict[str, float] = {
    "angry": -2.3,
    "awful": -2.6,
    "backlash": -2.3,
    "bankrupt": -3.0,
    "bankruptcy": -3.0,
    "bearish": -2.8,
    "boycott": -2.3,
    "concern": -1.6,
    "concerns": -1.6,
    "crash": -2.6,
    "crashed": -2.6,
    "crashes": -2.6,
    "crashing": -2.6,
    "crisis": -2.8,
    "cut": -1.7,
    "cuts": -1.7,
    "decline": -2.0,
    "declined": -2.0,
    "disappointing": -2.1,
    "disappointed": -2.1,
    "downgrade": -2.2,
    "downgraded": -2.2,
    "drop": -2.0,
    "dropped": -2.1,
    "fail": -2.4,
    "failed": -2.4,
    "failure": -2.5,
    "fall": -1.8,
    "falls": -1.8,
    "fear": -2.2,
    "fears": -2.2,
    "fell": -2.1,
    "fraud": -3.0,
    "hate": -2.8,
    "investigation": -1.9,
    "lawsuit": -2.4,
    "layoff": -2.2,
    "layoffs": -2.4,
    "loss": -2.3,
    "losses": -2.3,
    "miss": -2.0,
    "misses": -2.0,
    "probe": -1.7,
    "recall": -2.2,
    "risk": -1.8,
    "risks": -1.8,
    "selloff": -2.5,
    "shortfall": -2.0,
    "slump": -2.3,
    "terrible": -2.7,
    "threat": -2.4,
    "underperform": -2.4,
    "unsafe": -2.4,
    "weak": -1.8,
    "weaker": -1.9,
    "worst": -2.9,
}


EMOTION_LEXICON: Dict[str, Sequence[str]] = {
    "anger": ("angry", "rage", "furious", "hate", "outrage", "backlash", "slam", "slammed"),
    "fear": ("fear", "worried", "worry", "risk", "threat", "crisis", "unsafe", "panic"),
    "joy": ("love", "happy", "great", "excellent", "amazing", "win", "success", "relief"),
    "trust": ("secure", "safe", "approved", "support", "confident", "resilient", "credible"),
}


NEGATORS = {
    "not",
    "never",
    "no",
    "without",
    "hardly",
    "barely",
    "rarely",
    "isnt",
    "isn't",
    "wasnt",
    "wasn't",
    "dont",
    "don't",
    "doesnt",
    "doesn't",
}

INTENSIFIERS = {
    "very": 1.25,
    "extremely": 1.45,
    "highly": 1.30,
    "deeply": 1.30,
    "massively": 1.45,
    "slightly": 0.72,
    "somewhat": 0.78,
    "partly": 0.72,
}

UNCERTAINTY_TERMS = {
    "allegedly",
    "appears",
    "could",
    "may",
    "might",
    "possible",
    "reportedly",
    "rumor",
    "rumour",
    "seems",
    "unconfirmed",
}

RISK_TERMS = {
    "bankruptcy",
    "boycott",
    "crisis",
    "fraud",
    "investigation",
    "lawsuit",
    "layoff",
    "layoffs",
    "probe",
    "recall",
    "risk",
    "shortfall",
    "threat",
    "unconfirmed",
    "unsafe",
}

SOCIAL_MARKERS = {
    "imo",
    "imho",
    "lol",
    "lmao",
    "smh",
    "wtf",
    "wow",
    "moon",
}

SOURCE_FACTORS: Dict[SourceType, float] = {
    "news": 0.92,
    "social": 1.12,
    "markets": 1.04,
    "general": 1.0,
}

MODE_FACTORS: Dict[Mode, float] = {
    "balanced": 1.0,
    "strict": 0.86,
    "sensitive": 1.12,
}


@dataclass(frozen=True)
class EvidenceTerm:
    term: str
    score: float
    modifier: str
    position: int


@dataclass(frozen=True)
class ItemSentiment:
    text: str
    source: SourceType
    label: SentimentLabel
    polarity: float
    confidence: float
    intensity: float
    raw_score: float
    emotion: Dict[str, int]
    evidence: List[EvidenceTerm]
    risk_terms: List[str]
    uncertainty_terms: List[str]
    social_markers: List[str]
    token_count: int


@dataclass(frozen=True)
class AggregateSentiment:
    label: SentimentLabel
    polarity: float
    confidence: float
    intensity: float
    positive_count: int
    negative_count: int
    neutral_count: int
    top_emotion: str
    risk_score: float
    credibility_score: float
    evidence: List[EvidenceTerm]


@dataclass(frozen=True)
class TradingSignal:
    bias: TradingBias
    conviction: float
    sentiment_edge: float
    caution: str
    reasons: List[str]


@dataclass(frozen=True)
class SentimentReport:
    aggregate: AggregateSentiment
    items: List[ItemSentiment]
    trading_signal: Optional[TradingSignal]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


class ExpertSentimentAnalyst:
    """Rule-based, explainable sentiment scorer for trading workflows."""

    def __init__(
        self,
        *,
        positive_lexicon: Optional[Dict[str, float]] = None,
        negative_lexicon: Optional[Dict[str, float]] = None,
    ) -> None:
        self.positive_lexicon = dict(POSITIVE_LEXICON)
        self.negative_lexicon = dict(NEGATIVE_LEXICON)
        if positive_lexicon:
            self.positive_lexicon.update(positive_lexicon)
        if negative_lexicon:
            self.negative_lexicon.update(negative_lexicon)

    def analyze(
        self,
        texts: str | Iterable[str],
        *,
        source: SourceType = "general",
        mode: Mode = "balanced",
        include_trading_signal: bool = True,
    ) -> SentimentReport:
        """Analyze one text blob or an iterable of individual items."""
        items = self._coerce_items(texts)
        scored = [self.analyze_item(item, source=source, mode=mode) for item in items]
        aggregate = self.aggregate(scored)
        signal = self.trading_signal(aggregate, scored) if include_trading_signal else None
        return SentimentReport(aggregate=aggregate, items=scored, trading_signal=signal)

    def analyze_item(
        self,
        text: str,
        *,
        source: SourceType = "general",
        mode: Mode = "balanced",
    ) -> ItemSentiment:
        tokens = tokenize(text)
        evidence: List[EvidenceTerm] = []
        emotion_hits = {name: 0 for name in EMOTION_LEXICON}
        raw_score = 0.0
        magnitude = 0.0

        risk_terms: List[str] = []
        uncertainty_terms: List[str] = []
        social_markers: List[str] = []

        for index, token in enumerate(tokens):
            if token in RISK_TERMS:
                risk_terms.append(token)
            if token in UNCERTAINTY_TERMS:
                uncertainty_terms.append(token)
            if token in SOCIAL_MARKERS:
                social_markers.append(token)

            for emotion, words in EMOTION_LEXICON.items():
                if token in words:
                    emotion_hits[emotion] += 1

            base_score = self.positive_lexicon.get(token, self.negative_lexicon.get(token, 0.0))
            if not base_score:
                continue

            previous = tokens[max(0, index - 3) : index]
            negated = any(word in NEGATORS for word in previous)
            multiplier = 1.0
            for word in previous:
                multiplier *= INTENSIFIERS.get(word, 1.0)

            adjusted = base_score * multiplier
            modifier = "direct"
            if token == "support" and any(word in {"bad", "poor", "weak", "awful"} for word in previous):
                adjusted = -1.2 * multiplier
                modifier = "contextual"
            elif token == "margin" and any(word in {"weak", "weaker", "declining", "falling"} for word in previous):
                adjusted = -1.4 * multiplier
                modifier = "contextual"
            if negated:
                adjusted *= -0.84
                modifier = "negated"
            elif multiplier != 1.0:
                modifier = "weighted"

            raw_score += adjusted
            magnitude += abs(adjusted)
            evidence.append(
                EvidenceTerm(
                    term=token,
                    score=round(adjusted, 4),
                    modifier=modifier,
                    position=index,
                )
            )

        normalized = math.tanh((raw_score * SOURCE_FACTORS[source] * MODE_FACTORS[mode]) / 5.0)
        polarity = round(normalized * 100.0, 2)
        label = sentiment_label(polarity)

        evidence_density = min(1.0, len(evidence) / max(3.0, len(tokens) / 12.0))
        agreement = abs(raw_score) / magnitude if magnitude else 0.0
        ambiguity_penalty = min(0.34, len(uncertainty_terms) * 0.055 + (0.08 if label == "neutral" else 0.0))
        confidence = 42.0 + evidence_density * 35.0 + agreement * 28.0 - ambiguity_penalty * 100.0
        if mode == "strict":
            confidence *= 0.92
        confidence = round(clamp(confidence, 7.0, 99.7), 2)

        intensity = round(
            clamp(abs(normalized) * 72.0 + magnitude * 3.2 + len(social_markers) * 4.0, 0.0, 100.0),
            2,
        )

        emotion_total = sum(emotion_hits.values()) or 1
        emotion = {name: round(count / emotion_total * 100) for name, count in emotion_hits.items()}

        return ItemSentiment(
            text=text,
            source=source,
            label=label,
            polarity=polarity,
            confidence=confidence,
            intensity=intensity,
            raw_score=round(raw_score, 4),
            emotion=emotion,
            evidence=sorted(evidence, key=lambda item: abs(item.score), reverse=True),
            risk_terms=risk_terms,
            uncertainty_terms=uncertainty_terms,
            social_markers=social_markers,
            token_count=len(tokens),
        )

    def aggregate(self, items: Sequence[ItemSentiment]) -> AggregateSentiment:
        if not items:
            raise ValueError("At least one text item is required.")

        total_weight = 0.0
        weighted_polarity = 0.0
        weighted_confidence = 0.0
        weighted_intensity = 0.0
        emotion_totals = {name: 0.0 for name in EMOTION_LEXICON}
        all_evidence: List[EvidenceTerm] = []
        risk_hits = 0
        uncertainty_hits = 0

        for item in items:
            weight = max(0.1, item.confidence / 100.0) * max(0.35, item.intensity / 100.0)
            total_weight += weight
            weighted_polarity += item.polarity * weight
            weighted_confidence += item.confidence * weight
            weighted_intensity += item.intensity * weight
            risk_hits += len(item.risk_terms)
            uncertainty_hits += len(item.uncertainty_terms)
            all_evidence.extend(item.evidence[:8])
            for emotion, value in item.emotion.items():
                emotion_totals[emotion] += value * weight

        polarity = round(weighted_polarity / total_weight, 2)
        confidence = round(weighted_confidence / total_weight, 2)
        intensity = round(weighted_intensity / total_weight, 2)
        risk_score = round(clamp((risk_hits * 11.0 + uncertainty_hits * 5.0) / max(1, len(items)), 0.0, 100.0), 2)
        credibility_score = round(clamp(confidence - risk_score * 0.35 - uncertainty_hits * 1.5, 1.0, 99.0), 2)

        return AggregateSentiment(
            label=sentiment_label(polarity),
            polarity=polarity,
            confidence=confidence,
            intensity=intensity,
            positive_count=sum(1 for item in items if item.label == "positive"),
            negative_count=sum(1 for item in items if item.label == "negative"),
            neutral_count=sum(1 for item in items if item.label == "neutral"),
            top_emotion=max(emotion_totals.items(), key=lambda pair: pair[1])[0],
            risk_score=risk_score,
            credibility_score=credibility_score,
            evidence=sorted(all_evidence, key=lambda item: abs(item.score), reverse=True)[:20],
        )

    def trading_signal(
        self,
        aggregate: AggregateSentiment,
        items: Sequence[ItemSentiment],
    ) -> TradingSignal:
        """Convert sentiment into a conservative trading bias, not an order."""
        edge = aggregate.polarity * (aggregate.confidence / 100.0) * (aggregate.credibility_score / 100.0)
        disagreement = min(aggregate.positive_count, aggregate.negative_count) / max(1, len(items))
        risk_drag = aggregate.risk_score * 0.18 + disagreement * 18.0
        conviction = round(clamp(abs(edge) - risk_drag, 0.0, 100.0), 2)

        if aggregate.credibility_score < 45 or aggregate.confidence < 45:
            bias: TradingBias = "watch"
        elif edge >= 18 and conviction >= 12:
            bias = "bullish"
        elif edge <= -18 and conviction >= 12:
            bias = "bearish"
        elif abs(edge) < 8:
            bias = "neutral"
        else:
            bias = "watch"

        reasons = [
            f"aggregate sentiment is {aggregate.label} at {aggregate.polarity}",
            f"confidence {aggregate.confidence}%, credibility {aggregate.credibility_score}%",
            f"risk score {aggregate.risk_score}%",
        ]
        if disagreement:
            reasons.append(f"mixed corpus disagreement {round(disagreement * 100, 1)}%")
        if aggregate.top_emotion in {"fear", "anger"}:
            reasons.append(f"dominant emotion is {aggregate.top_emotion}")

        caution = (
            "Use as a sentiment input only; confirm with price action, volume, liquidity, "
            "position sizing, and risk controls before trading."
        )

        return TradingSignal(
            bias=bias,
            conviction=conviction,
            sentiment_edge=round(edge, 2),
            caution=caution,
            reasons=reasons,
        )

    @staticmethod
    def _coerce_items(texts: str | Iterable[str]) -> List[str]:
        if isinstance(texts, str):
            parts = re.split(r"\n\s*\n|(?<=[.!?])\s+(?=[A-Z0-9\"'])", texts)
        else:
            parts = list(texts)
        items = [part.strip() for part in parts if part and part.strip()]
        if not items:
            raise ValueError("No text supplied for sentiment analysis.")
        return items


def tokenize(text: str) -> List[str]:
    return [token.strip("'").lower() for token in re.findall(r"[A-Za-z']+|[$#][A-Za-z0-9_]+", text)]


def sentiment_label(polarity: float) -> SentimentLabel:
    if polarity > 8.0:
        return "positive"
    if polarity < -8.0:
        return "negative"
    return "neutral"


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def analyze_sentiment(
    texts: str | Iterable[str],
    *,
    source: SourceType = "general",
    mode: Mode = "balanced",
    include_trading_signal: bool = True,
) -> SentimentReport:
    """Convenience function for quick integration."""
    return ExpertSentimentAnalyst().analyze(
        texts,
        source=source,
        mode=mode,
        include_trading_signal=include_trading_signal,
    )


if __name__ == "__main__":
    sample = [
        "Shares surged after the company reported record profit and stronger guidance.",
        "Users are angry about crashes, weak support, and a disappointing update.",
        "Analysts reportedly remain cautious because the investigation is ongoing.",
    ]
    report = analyze_sentiment(sample, source="markets", mode="balanced")
    print(report.to_json())
