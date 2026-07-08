"""Custom sentiment scoring: VADER base score blended with a finance-specific
keyword weighting layer (VADER alone misses domain terms like "beats estimates"
or "guidance cut"). Optionally refined by the LLM client for a headline digest,
but the numeric score never depends on the LLM being available."""

from __future__ import annotations

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer = SentimentIntensityAnalyzer()

POSITIVE_TERMS = {
    "beats estimates": 0.35, "beat estimates": 0.35, "record profit": 0.3, "upgrade": 0.25,
    "strong guidance": 0.3, "buyback": 0.2, "expansion": 0.15, "outperform": 0.25,
    "raises guidance": 0.3, "wins order": 0.2, "order win": 0.2, "surge": 0.15,
}
NEGATIVE_TERMS = {
    "misses estimates": -0.35, "miss estimates": -0.35, "downgrade": -0.25, "guidance cut": -0.35,
    "probe": -0.3, "fraud": -0.4, "resign": -0.2, "layoffs": -0.2, "default": -0.35,
    "lawsuit": -0.2, "regulatory action": -0.25, "profit warning": -0.35, "slump": -0.2,
}


def _keyword_adjustment(text: str) -> float:
    low = text.lower()
    adj = 0.0
    for term, weight in POSITIVE_TERMS.items():
        if term in low:
            adj += weight
    for term, weight in NEGATIVE_TERMS.items():
        if term in low:
            adj += weight
    return max(-1.0, min(1.0, adj))


def score_headline(text: str) -> float:
    base = _analyzer.polarity_scores(text)["compound"]
    adj = _keyword_adjustment(text)
    return max(-1.0, min(1.0, 0.6 * base + 0.4 * adj))


def analyze(news_items: list[dict]) -> dict:
    if not news_items:
        return {"action": "WAIT", "confidence": 0.15, "evidence": ["No recent news found."], "metrics": {"n_items": 0}}

    scores = []
    evidence = []
    for item in news_items:
        text = f"{item.get('title', '')}. {item.get('summary', '')}"
        s = score_headline(text)
        scores.append(s)
        if abs(s) >= 0.3:
            evidence.append(f"[{s:+.2f}] {item.get('title', '')[:120]}")

    avg = sum(scores) / len(scores)
    agreement = 1.0 - (max(scores) - min(scores)) / 2.0 if len(scores) > 1 else 0.5
    agreement = max(0.0, min(1.0, agreement))

    if avg > 0.15:
        action = "BUY"
    elif avg < -0.15:
        action = "SELL"
    else:
        action = "HOLD"

    volume_factor = min(len(news_items) / 8.0, 1.0)
    confidence = round(max(0.15, min(0.95, abs(avg) * 1.5 * agreement * 0.6 + volume_factor * 0.4)), 3)

    if not evidence:
        evidence = [f"{len(news_items)} recent headlines, average sentiment {avg:+.2f} (mixed/neutral)."]

    return {
        "action": action,
        "confidence": confidence,
        "evidence": evidence[:5],
        "metrics": {"avg_sentiment": round(avg, 3), "agreement": round(agreement, 3), "n_items": len(news_items)},
    }
