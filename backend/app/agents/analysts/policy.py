"""Government Policy Analyst: deterministic keyword+sentiment scoring (see
app/tools/policy_geo_impact.py) drives the action/confidence, same as before.
The LLM reasoning pass is upgraded to explicitly walk five policy-impact
dimensions - a taxonomy borrowed from a teammate's Government Policy Analyst
prototype (github.com/Mayurirai2020/Government_policy_analyst). That repo's
actual agents turned out to be non-functional scaffolding (its LLM client
unconditionally returns a hardcoded mock string, and its "specialist agents"
return near-static template text averaged by a naive consensus) - there was
no real logic to port. The taxonomy itself was the only reusable part, so
that's what's integrated here, applied to our own working LLM client."""

from app.agents.base import AgentVote, AnalysisContext, BaseAgent
from app.llm.client import get_llm_client
from app.tools import policy_geo_impact

POLICY_DIMENSIONS = [
    "Legal/Regulatory - statutory authority, compliance burden, rule changes",
    "Fiscal/Budgetary - taxation, subsidies, government spending exposure",
    "Implementation - feasibility and timeline of the policy actually taking effect",
    "Stakeholder Impact - who benefits or is burdened (consumers, competitors, sector peers)",
    "Geopolitical/Trade - tariffs, sanctions, treaties, cross-border exposure",
]


class PolicyAnalyst(BaseAgent):
    name = "Government Policy Analyst"
    agent_type = "analyst"
    expertise = "policy"

    def vote(self, ctx: AnalysisContext) -> AgentVote:
        combined_news = ctx.symbol_news + ctx.market_news
        policy_items = [n for n in combined_news if "policy" in n.get("tags", [])]
        signal = policy_geo_impact.analyze(policy_items)

        llm = get_llm_client()
        evidence_txt = " ".join(signal["evidence"])
        dimensions_txt = "\n".join(f"- {d}" for d in POLICY_DIMENSIONS)
        reasoning = llm.chat(
            system=(
                "You are a government/regulatory policy analyst on a trading committee (RBI, SEBI, budget, "
                "taxation, trade policy). Given the headline evidence, briefly consider which of these five "
                "dimensions are actually in play, then write a 2-3 sentence synthesis - only mention dimensions "
                f"with real evidence, don't force all five:\n{dimensions_txt}"
            ),
            user=f"Symbol {ctx.symbol}. Signal: {signal['action']} (confidence {signal['confidence']}). Evidence: {evidence_txt}",
            fallback=f"Policy read for {ctx.symbol}: {signal['action']}. {evidence_txt or 'No material policy headlines this tick.'}",
        )

        return AgentVote(
            agent_name=self.name,
            agent_type=self.agent_type,
            action=signal["action"],
            confidence=signal["confidence"],
            reasoning=reasoning,
            evidence=signal["evidence"] or ["No policy/regulatory headlines detected this tick."],
            metrics=signal["metrics"],
        )
