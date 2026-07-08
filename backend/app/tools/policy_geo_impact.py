"""Policy & geopolitical impact scoring: tags news items already flagged by
the news layer (policy/geopolitical) and scores their directional impact using
keyword polarity, separate from general market sentiment."""

from __future__ import annotations

from app.tools.sentiment_engine import score_headline

POSITIVE_POLICY = ["rate cut", "stimulus", "subsidy", "incentive", "tax relief", "deal signed", "ceasefire"]
NEGATIVE_POLICY = ["rate hike", "tariff", "sanctions", "ban", "war", "conflict escalates", "tax hike", "strike"]


def _polarity_boost(text: str) -> float:
    low = text.lower()
    boost = 0.0
    for t in POSITIVE_POLICY:
        if t in low:
            boost += 0.2
    for t in NEGATIVE_POLICY:
        if t in low:
            boost -= 0.2
    return max(-0.6, min(0.6, boost))


def analyze(news_items: list[dict]) -> dict:
    relevant = [n for n in news_items if "policy" in n.get("tags", []) or "geopolitical" in n.get("tags", [])]

    if not relevant:
        return {
            "action": "HOLD",
            "confidence": 0.2,
            "evidence": ["No material policy/geopolitical news detected in recent window."],
            "metrics": {"n_relevant": 0},
        }

    scores = []
    evidence = []
    for item in relevant:
        text = f"{item.get('title', '')}. {item.get('summary', '')}"
        s = score_headline(text) + _polarity_boost(text)
        s = max(-1.0, min(1.0, s))
        scores.append(s)
        evidence.append(f"[{s:+.2f}] {item.get('title', '')[:120]}")

    avg = sum(scores) / len(scores)
    if avg > 0.15:
        action = "BUY"
    elif avg < -0.15:
        action = "SELL"
    else:
        action = "HOLD"

    confidence = round(max(0.2, min(0.85, abs(avg) * 1.3 + min(len(relevant) / 6.0, 0.3))), 3)

    return {
        "action": action,
        "confidence": confidence,
        "evidence": evidence[:4],
        "metrics": {"avg_impact": round(avg, 3), "n_relevant": len(relevant)},
    }
