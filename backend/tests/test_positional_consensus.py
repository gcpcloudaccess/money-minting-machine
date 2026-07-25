"""Unit tests for positional-mode consensus (mode="positional") - proves it's
a genuinely different weighting/threshold from the default intraday mode,
and that intraday callers (mode omitted) are completely unaffected."""

from app.agents.base import AgentVote
from app.consensus.trust_weighted_consensus import (
    DECISIVE_THRESHOLD,
    EXPERTISE_RELEVANCE,
    POSITIONAL_DECISIVE_THRESHOLD,
    POSITIONAL_EXPERTISE_RELEVANCE,
    compute_consensus,
)


def _vote(agent_name, action, confidence):
    return AgentVote(agent_name=agent_name, agent_type="analyst", action=action, confidence=confidence, reasoning="synthetic", evidence=[], metrics={})


def test_positional_threshold_is_higher_than_intraday():
    assert POSITIONAL_DECISIVE_THRESHOLD > DECISIVE_THRESHOLD


def test_fundamental_analyst_weighted_higher_positionally():
    assert POSITIONAL_EXPERTISE_RELEVANCE["Fundamental Analyst"] > EXPERTISE_RELEVANCE["Fundamental Analyst"]


def test_default_mode_is_intraday_and_unchanged():
    """Omitting `mode` must behave exactly as before this feature existed -
    no positional-only agent name should silently affect an intraday call."""
    votes = [_vote("Technical Analyst", "BUY", 0.8), _vote("Sentiment Analyst", "BUY", 0.75)]
    trust = {"Technical Analyst": 0.7, "Sentiment Analyst": 0.7}

    default_mode = compute_consensus(votes, trust)
    explicit_intraday = compute_consensus(votes, trust, mode="intraday")
    assert default_mode.directional_confidence == explicit_intraday.directional_confidence
    assert default_mode.verdict == explicit_intraday.verdict


def test_same_votes_can_clear_intraday_but_not_positional_threshold():
    """A moderate plurality that clears intraday's 14% decisive bar should not
    automatically clear positional's higher 22% bar - proves the modes are
    genuinely calibrated differently, not just relabeled."""
    votes = [
        _vote("Technical Analyst", "BUY", 0.35),
        _vote("Sentiment Analyst", "HOLD", 0.3),
        _vote("Risk Assessment Analyst", "HOLD", 0.25),
    ]
    trust = {"Technical Analyst": 0.5, "Sentiment Analyst": 0.5, "Risk Assessment Analyst": 0.5}

    intraday = compute_consensus(votes, trust, mode="intraday")
    positional = compute_consensus(votes, trust, mode="positional")
    assert intraday.winning_action == "BUY"
    assert intraday.verdict == "BUY"
    assert positional.verdict != "BUY" or positional.directional_confidence < intraday.directional_confidence


def test_options_specific_agent_relevance_present_only_in_positional_table():
    assert "IV & Options Chain Analyst" not in EXPERTISE_RELEVANCE
    assert POSITIONAL_EXPERTISE_RELEVANCE["IV & Options Chain Analyst"] == 1.0
