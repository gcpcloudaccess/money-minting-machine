from app.agents.base import AgentVote, AnalysisContext, BaseAgent, blend_signals
from app.llm.client import get_llm_client
from app.tools import fundamental_scoring, sector_intelligence


class FundamentalAnalyst(BaseAgent):
    name = "Fundamental Analyst"
    agent_type = "analyst"
    expertise = "fundamental"

    def vote(self, ctx: AnalysisContext) -> AgentVote:
        fund = fundamental_scoring.analyze(ctx.fundamentals)
        sector = sector_intelligence.analyze(ctx.symbol, ctx.bars, ctx.peer_bars)
        combined = blend_signals([fund, sector], [0.7, 0.3])

        llm = get_llm_client()
        evidence_txt = " ".join(combined["evidence"])
        reasoning = llm.chat(
            system="You are a fundamental analyst on a trading committee. Summarize the valuation/quality case in 2-3 crisp sentences.",
            user=f"Symbol {ctx.symbol}. Signal: {combined['action']} (confidence {combined['confidence']}). Evidence: {evidence_txt}",
            fallback=f"Fundamental read for {ctx.symbol}: {combined['action']}. {evidence_txt}",
        )

        return AgentVote(
            agent_name=self.name,
            agent_type=self.agent_type,
            action=combined["action"],
            confidence=combined["confidence"],
            reasoning=reasoning,
            evidence=combined["evidence"],
            metrics=combined["metrics"],
        )
