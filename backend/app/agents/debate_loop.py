from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.agents.analysts import ALL_ANALYSTS
from app.agents.base import AgentVote, AnalysisContext
from app.agents.critics import ALL_CRITICS
from app.agents.debate_agent import DebateAgent
from app.config import get_settings


def run_debate(ctx: AnalysisContext) -> tuple[list[AgentVote], AgentVote, list[AgentVote]]:
    """Runs all analyst agents in parallel (each one independently gathers its
    own evidence and makes its own LLM call - there's no ordering dependency
    among them), then the Debate Agent synthesizes the strongest contradicting
    views, then all 4 critics in parallel over analysts + the debate synthesis.

    Concurrency is capped at `settings.max_parallel_agents` rather than left
    unbounded: firing all 8+ agents' LLM calls at once tends to trip API rate
    limits, and the SDK's automatic retry-with-backoff on 429s can end up
    *slower* than sequential execution - a bounded pool still gets most of the
    parallelism benefit without falling into that trap.

    Returns (analyst_votes, debate_vote, critic_votes).
    """
    max_workers = max(1, get_settings().max_parallel_agents)

    with ThreadPoolExecutor(max_workers=min(max_workers, len(ALL_ANALYSTS))) as pool:
        analyst_votes = list(pool.map(lambda cls: cls().vote(ctx), ALL_ANALYSTS))

    debate_vote = DebateAgent().vote(ctx, analyst_votes)

    with ThreadPoolExecutor(max_workers=min(max_workers, len(ALL_CRITICS))) as pool:
        critic_votes = list(pool.map(lambda cls: cls().vote(ctx, analyst_votes + [debate_vote]), ALL_CRITICS))

    return analyst_votes, debate_vote, critic_votes
