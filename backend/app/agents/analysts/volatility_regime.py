"""Volatility Regime Analyst: is options premium cheap or rich right now
(implied vol vs realized vol, vol term structure), independent of direction.
Feeds the Strategy Architect's choice between buying premium outright and
selling a spread - see app/tools/volatility_regime.py and
app/tools/strategy_builder.py.

Its "action" field is a premium-cost signal (BUY = buy premium / cheap, SELL
= sell premium / rich), not a directional market call, so it's given lower
expertise_relevance in the positional consensus table than genuinely
directional agents - it should nudge structure choice, not the BUY/SELL
verdict itself. See app/consensus/trust_weighted_consensus.py's
POSITIONAL_EXPERTISE_RELEVANCE."""

from __future__ import annotations

from app.agents.base import AgentVote, AnalysisContext, BaseAgent, prior_stage_summary
from app.llm.client import get_llm_client
from app.tools import volatility_regime


class VolatilityRegimeAnalyst(BaseAgent):
    name = "Volatility Regime Analyst"
    agent_type = "analyst"
    expertise = "volatility_regime"

    def vote(self, ctx: AnalysisContext) -> AgentVote:
        signal = volatility_regime.analyze(ctx.daily_bars, ctx.option_chain)

        llm = get_llm_client()
        evidence_txt = " ".join(signal["evidence"])
        context_txt = prior_stage_summary(ctx)
        reasoning = llm.chat(
            system=(
                "You are the Volatility Regime Analyst on a trading committee. Summarize in 2-3 crisp sentences "
                "whether options premium looks cheap or rich right now (implied vs realized volatility, term "
                "structure) and what that implies for how a positional options trade should be structured - do not "
                "make a directional call, that's other analysts' job."
            ),
            user=f"Symbol {ctx.symbol}. Signal: {signal['action']} (confidence {signal['confidence']}). Evidence: {evidence_txt}\n\n{context_txt}",
            fallback=f"Volatility regime read for {ctx.symbol}: {signal['action']}. {evidence_txt}",
        )

        return AgentVote(
            agent_name=self.name, agent_type=self.agent_type, action=signal["action"], confidence=signal["confidence"],
            reasoning=reasoning, evidence=signal["evidence"], metrics=signal["metrics"],
        )
