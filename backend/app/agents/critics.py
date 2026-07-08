"""Critic agents for the debate loop. Each critic reviews the analyst votes
already cast for this tick and casts its own vote — critics are full
participants in the trust-weighted consensus, not just commentary."""

from __future__ import annotations

from app.agents.base import AgentVote, AnalysisContext, BaseAgent
from app.llm.client import get_llm_client
from app.tools import opportunity_discovery, risk_model


def _action_confidences(votes: list[AgentVote], action: str) -> list[float]:
    return [v.confidence for v in votes if v.action == action]


class RiskCritic(BaseAgent):
    name = "Risk Critic"
    agent_type = "critic"
    expertise = "risk"

    def vote(self, ctx: AnalysisContext, analyst_votes: list[AgentVote]) -> AgentVote:
        risk_signal = risk_model.analyze(ctx.bars)
        bullish_conf = sum(_action_confidences(analyst_votes, "BUY"))
        risk_level = risk_signal["metrics"].get("risk_level", "MEDIUM")

        if risk_level == "HIGH" and bullish_conf > 0:
            action, confidence = "HOLD", 0.6
            challenge = f"Committee leans bullish (combined confidence {bullish_conf:.2f}) but volatility regime is HIGH — risk/reward is not clearly favorable."
        elif risk_level == "LOW":
            action, confidence = "BUY", 0.3
            challenge = "Volatility regime is LOW; downside risk of acting on the group's lean is limited."
        else:
            action, confidence = "HOLD", 0.35
            challenge = "Risk regime is MEDIUM; no strong objection, but position sizing should stay conservative."

        llm = get_llm_client()
        reasoning = llm.chat(
            system="You are the Risk Critic in an investment committee debate. Challenge weak risk assumptions in 2 sentences.",
            user=f"Symbol {ctx.symbol}. {challenge}",
            fallback=challenge,
        )
        return AgentVote(agent_name=self.name, agent_type=self.agent_type, action=action, confidence=confidence, reasoning=reasoning, evidence=[challenge], metrics=risk_signal["metrics"])


class ProfitCritic(BaseAgent):
    name = "Profit Critic"
    agent_type = "critic"
    expertise = "technical"

    def vote(self, ctx: AnalysisContext, analyst_votes: list[AgentVote]) -> AgentVote:
        bullish_conf = sum(_action_confidences(analyst_votes, "BUY"))
        bearish_conf = sum(_action_confidences(analyst_votes, "SELL"))

        if bullish_conf > bearish_conf and bullish_conf > 0.8:
            action, confidence = "BUY", min(0.7, bullish_conf / max(len(analyst_votes), 1))
            challenge = f"Bullish evidence is broad-based (combined confidence {bullish_conf:.2f}) — profit case looks credible, not just noise."
        elif bearish_conf > bullish_conf and bearish_conf > 0.8:
            action, confidence = "SELL", min(0.7, bearish_conf / max(len(analyst_votes), 1))
            challenge = f"Bearish evidence is broad-based (combined confidence {bearish_conf:.2f}) — downside case looks credible."
        else:
            action, confidence = "WAIT", 0.4
            challenge = "Evidence for a profitable move this tick is thin/mixed; conviction is not high enough to size up."

        llm = get_llm_client()
        reasoning = llm.chat(
            system="You are the Profit Critic in an investment committee debate. Judge whether the profit case is credible in 2 sentences.",
            user=f"Symbol {ctx.symbol}. {challenge}",
            fallback=challenge,
        )
        return AgentVote(agent_name=self.name, agent_type=self.agent_type, action=action, confidence=confidence, reasoning=reasoning, evidence=[challenge], metrics={"bullish_conf": round(bullish_conf, 2), "bearish_conf": round(bearish_conf, 2)})


class MacroCritic(BaseAgent):
    name = "Macro Critic"
    agent_type = "critic"
    expertise = "macro"

    def vote(self, ctx: AnalysisContext, analyst_votes: list[AgentVote]) -> AgentVote:
        macro_votes = [v for v in analyst_votes if v.agent_name in ("Macroeconomic Analyst", "Geopolitical Analyst", "Government Policy Analyst")]
        stock_votes = [v for v in analyst_votes if v.agent_name in ("Technical Analyst", "Fundamental Analyst")]

        macro_actions = {v.action for v in macro_votes}
        stock_actions = {v.action for v in stock_votes}
        conflict = bool(macro_actions & {"SELL"}) and bool(stock_actions & {"BUY"})

        if conflict:
            action, confidence = "HOLD", 0.55
            challenge = "Macro/policy/geopolitical backdrop is negative while stock-specific signals are bullish — a top-down headwind could override a bottom-up setup."
        elif macro_votes and all(v.action == "BUY" for v in macro_votes):
            action, confidence = "BUY", 0.4
            challenge = "Macro backdrop is supportive and does not contradict the stock-specific case."
        else:
            action, confidence = "HOLD", 0.3
            challenge = "No strong macro conflict detected this tick."

        llm = get_llm_client()
        reasoning = llm.chat(
            system="You are the Macro Critic in an investment committee debate. Flag any top-down vs bottom-up conflict in 2 sentences.",
            user=f"Symbol {ctx.symbol}. {challenge}",
            fallback=challenge,
        )
        return AgentVote(agent_name=self.name, agent_type=self.agent_type, action=action, confidence=confidence, reasoning=reasoning, evidence=[challenge], metrics={})


class OpportunityCritic(BaseAgent):
    name = "Opportunity Critic"
    agent_type = "critic"
    expertise = "opportunity"

    def vote(self, ctx: AnalysisContext, analyst_votes: list[AgentVote]) -> AgentVote:
        current_lean = max(set(v.action for v in analyst_votes), key=lambda a: sum(v.confidence for v in analyst_votes if v.action == a))
        result = opportunity_discovery.find_alternatives(ctx.symbol, current_lean, ctx.peer_bars or {ctx.symbol: ctx.bars})

        llm = get_llm_client()
        evidence_txt = " ".join(result["evidence"])
        reasoning = llm.chat(
            system="You are the Opportunity Critic in an investment committee debate. State plainly whether a better "
            "risk-adjusted alternative exists in the watchlist, in 2 sentences.",
            user=f"Symbol {ctx.symbol}. {evidence_txt}",
            fallback=evidence_txt,
        )
        return AgentVote(
            agent_name=self.name,
            agent_type=self.agent_type,
            action=result["action"],
            confidence=result["confidence"],
            reasoning=reasoning,
            evidence=result["evidence"],
            metrics={"alternatives": result.get("alternatives", [])},
        )


ALL_CRITICS = [RiskCritic, ProfitCritic, MacroCritic, OpportunityCritic]
