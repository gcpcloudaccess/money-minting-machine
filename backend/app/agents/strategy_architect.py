"""Strategy Architect: NOT a voting analyst - a translator that runs once,
after the consensus verdict is final, turning "BUY, 62% directional
confidence" into an actual options structure (strike, expiry, spread vs
naked) using the Volatility Regime Analyst's read. See app/tools/
strategy_builder.py for the structure-selection math and
docs/POSITIONAL_OPTIONS_ENHANCEMENT_PLAN.md for why this is a separate stage
rather than another committee vote: it has nothing to add to WHETHER to trade
(that's the consensus's job) and everything to add to HOW to express it."""

from __future__ import annotations

from app.agents.base import AgentVote
from app.data.options_data import OptionChainSnapshot
from app.tools.strategy_builder import StrategyPick, build_strategy


def _iv_regime_from_votes(analyst_votes: list[AgentVote]) -> str:
    vol_vote = next((v for v in analyst_votes if v.agent_name == "Volatility Regime Analyst"), None)
    if vol_vote is None:
        return "unknown"
    return vol_vote.metrics.get("regime", "unknown")


def build_strategy_for_verdict(
    winning_action: str,
    directional_confidence: float,
    analyst_votes: list[AgentVote],
    option_chain: OptionChainSnapshot | None,
) -> StrategyPick | None:
    """winning_action/directional_confidence come straight from
    ConsensusResult (app/consensus/trust_weighted_consensus.py). Returns None
    for HOLD/WAIT verdicts (nothing to structure) or when there's no options
    chain to build real strikes/premiums from."""
    if winning_action not in ("BUY", "SELL"):
        return None
    iv_regime = _iv_regime_from_votes(analyst_votes)
    return build_strategy(winning_action, directional_confidence, iv_regime, option_chain)
