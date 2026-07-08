from app.agents.base import AgentVote, AnalysisContext, BaseAgent
from app.llm.client import get_llm_client
from app.tools import policy_geo_impact


class GeopoliticalAnalyst(BaseAgent):
    name = "Geopolitical Analyst"
    agent_type = "analyst"
    expertise = "geopolitical"

    def vote(self, ctx: AnalysisContext) -> AgentVote:
        combined_news = ctx.symbol_news + ctx.market_news
        geo_items = [n for n in combined_news if "geopolitical" in n.get("tags", [])]
        signal = policy_geo_impact.analyze(geo_items)

        llm = get_llm_client()
        evidence_txt = " ".join(signal["evidence"])
        reasoning = llm.chat(
            system="You are a geopolitical risk analyst on a trading committee. Summarize conflict/sanctions/trade "
            "related impact on this stock in 2-3 crisp sentences.",
            user=f"Symbol {ctx.symbol}. Signal: {signal['action']} (confidence {signal['confidence']}). Evidence: {evidence_txt}",
            fallback=f"Geopolitical read for {ctx.symbol}: {signal['action']}. {evidence_txt or 'No material geopolitical headlines this tick.'}",
        )

        return AgentVote(
            agent_name=self.name,
            agent_type=self.agent_type,
            action=signal["action"],
            confidence=signal["confidence"],
            reasoning=reasoning,
            evidence=signal["evidence"] or ["No geopolitical headlines detected this tick."],
            metrics=signal["metrics"],
        )
