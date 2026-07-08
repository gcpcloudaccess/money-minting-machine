"""Tests for the vendored team sentiment_analyst engine and its integration
into our SentimentAnalyst - no network, no LLM key required."""

from app.agents.analysts.sentiment import SentimentAnalyst
from app.agents.base import AnalysisContext
from sentiment_analyst import ExpertSentimentAnalyst


def test_vendored_engine_runs_standalone():
    report = ExpertSentimentAnalyst().analyze(
        ["Shares surged after record profit and stronger guidance."], source="news"
    )
    assert report.aggregate.label == "positive"
    assert report.trading_signal.bias in ("bullish", "bearish", "neutral", "watch")


def test_sentiment_analyst_bullish_news():
    ctx = AnalysisContext(
        symbol="TCS.NS",
        bars=None,
        fundamentals={},
        symbol_news=[
            {"title": "TCS beats estimates with record profit and raised guidance", "summary": "Strong quarter."},
            {"title": "Analysts upgrade TCS on resilient growth outlook", "summary": "Confident tone."},
        ],
        market_news=[],
    )
    vote = SentimentAnalyst().vote(ctx)
    assert vote.agent_name == "Sentiment Analyst"
    assert vote.action == "BUY"
    assert vote.metrics["n_items"] == 2
    assert vote.metrics["polarity"] > 0


def test_sentiment_analyst_bearish_news():
    ctx = AnalysisContext(
        symbol="XYZ.NS",
        bars=None,
        fundamentals={},
        symbol_news=[
            {"title": "XYZ crashes after fraud investigation and bankruptcy fears", "summary": "Selloff continues."},
            {"title": "Analysts downgrade XYZ amid layoffs and weak margins", "summary": "Disappointing outlook."},
        ],
        market_news=[],
    )
    vote = SentimentAnalyst().vote(ctx)
    assert vote.action == "SELL"
    assert vote.metrics["polarity"] < 0
    assert vote.metrics["risk_score"] > 0


def test_sentiment_analyst_no_news():
    ctx = AnalysisContext(symbol="ABC.NS", bars=None, fundamentals={}, symbol_news=[], market_news=[])
    vote = SentimentAnalyst().vote(ctx)
    assert vote.action == "WAIT"
    assert vote.metrics["n_items"] == 0
