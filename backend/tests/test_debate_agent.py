"""Unit tests for the Debate Agent's contest-ratio math - independent of the
LLM (no API key needed; LLMClient falls back to templated text when unset)."""

from app.agents.base import AgentVote, AnalysisContext
from app.agents.debate_agent import DebateAgent


def _vote(agent_name, action, confidence, evidence=None):
    return AgentVote(agent_name=agent_name, agent_type="analyst", action=action, confidence=confidence, reasoning="synthetic", evidence=evidence or [], metrics={})


def _ctx(symbol="TEST.NS"):
    return AnalysisContext(symbol=symbol, bars=None, fundamentals={}, symbol_news=[], market_news=[])


def test_lopsided_agreement_yields_high_confidence():
    votes = [
        _vote("Technical Analyst", "BUY", 0.8),
        _vote("Fundamental Analyst", "BUY", 0.7),
        _vote("Sentiment Analyst", "BUY", 0.6),
    ]
    result = DebateAgent().vote(_ctx(), votes)
    assert result.action == "BUY"
    assert result.confidence > 0.7  # no real dissent -> high synthesis confidence


def test_evenly_split_room_yields_low_confidence():
    votes = [
        _vote("Technical Analyst", "BUY", 0.6, ["Momentum favors upside"]),
        _vote("Risk Assessment Analyst", "SELL", 0.6, ["Volatility regime is elevated"]),
    ]
    result = DebateAgent().vote(_ctx(), votes)
    assert result.confidence < 0.4  # evenly contested -> low synthesis confidence
    assert "Technical Analyst" in result.evidence[0]
    assert "Risk Assessment Analyst" in result.evidence[0]


def test_debate_vote_participates_in_consensus_with_expected_relevance():
    from app.consensus.trust_weighted_consensus import EXPERTISE_RELEVANCE

    assert "Debate Agent" in EXPERTISE_RELEVANCE
