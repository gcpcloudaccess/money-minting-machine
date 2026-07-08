from app.agents.base import AgentVote, AnalysisContext, BaseAgent
from app.llm.client import get_llm_client
from app.tools import sentiment_engine

MACRO_KEYWORDS = [
    "gdp", "inflation", "interest rate", "repo rate", "cpi", "wpi", "currency", "rupee",
    "crude oil", "global markets", "fii", "dii", "fed", "federal reserve", "bond yield",
]


def _is_macro(item: dict) -> bool:
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    return any(k in text for k in MACRO_KEYWORDS)


class MacroAnalyst(BaseAgent):
    name = "Macroeconomic Analyst"
    agent_type = "analyst"
    expertise = "macro"

    def vote(self, ctx: AnalysisContext) -> AgentVote:
        macro_items = [n for n in ctx.market_news if _is_macro(n)]
        signal = sentiment_engine.analyze(macro_items)

        llm = get_llm_client()
        evidence_txt = " ".join(signal["evidence"])
        reasoning = llm.chat(
            system="You are a macroeconomic analyst on a trading committee. Summarize how the macro backdrop "
            "(GDP, inflation, rates, currency, global markets) affects this stock in 2-3 crisp sentences.",
            user=f"Symbol {ctx.symbol}. Signal: {signal['action']} (confidence {signal['confidence']}). Evidence: {evidence_txt}",
            fallback=f"Macro read for {ctx.symbol}: {signal['action']}. {evidence_txt or 'No material macro headlines this tick.'}",
        )

        return AgentVote(
            agent_name=self.name,
            agent_type=self.agent_type,
            action=signal["action"],
            confidence=signal["confidence"],
            reasoning=reasoning,
            evidence=signal["evidence"] or ["No macro-tagged headlines in the current window."],
            metrics=signal["metrics"],
        )
