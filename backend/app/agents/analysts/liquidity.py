"""Liquidity/Open-Interest Analyst: bid-ask spread and open interest depth at
the ATM strike - a gate, not a directional call. A "best pick" that's
directionally perfect but untradeable (wide spreads, thin OI) shouldn't reach
the top of the ranked list; this agent is what stops that from happening.

Wide bid-ask spreads and thin OI push its vote toward WAIT (don't enter at
size) rather than expressing any directional view of its own - matching the
"gate, not a voter with an opinion" role described in docs/
POSITIONAL_OPTIONS_ENHANCEMENT_PLAN.md."""

from __future__ import annotations

from app.agents.base import AgentVote, AnalysisContext, BaseAgent, prior_stage_summary
from app.llm.client import get_llm_client

WIDE_SPREAD_PCT = 8.0     # bid-ask spread wider than this (% of mid) flags poor tradability
THIN_OI = 500              # open interest below this at the ATM strike flags thin liquidity


def _spread_pct(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        return None
    mid = (bid + ask) / 2
    return round((ask - bid) / mid * 100, 2) if mid else None


class LiquidityAnalyst(BaseAgent):
    name = "Liquidity Analyst"
    agent_type = "analyst"
    expertise = "liquidity"

    def vote(self, ctx: AnalysisContext) -> AgentVote:
        chain = ctx.option_chain
        if chain is None or not chain.legs:
            return AgentVote(
                agent_name=self.name, agent_type=self.agent_type, action="HOLD", confidence=0.15,
                reasoning=f"No options chain available for {ctx.symbol} - liquidity unassessed.",
                evidence=["No options chain data this run."], metrics={},
            )

        atm = chain.atm_strike()
        leg = next((l for l in chain.legs if l.strike == atm), None)
        if leg is None:
            return AgentVote(
                agent_name=self.name, agent_type=self.agent_type, action="HOLD", confidence=0.15,
                reasoning=f"Could not resolve an ATM strike for {ctx.symbol}.",
                evidence=["ATM strike unresolved."], metrics={},
            )

        call_spread = _spread_pct(leg.call_bid, leg.call_ask)
        put_spread = _spread_pct(leg.put_bid, leg.put_ask)
        worst_spread = max(v for v in (call_spread, put_spread) if v is not None) if any(v is not None for v in (call_spread, put_spread)) else None
        min_oi = min((v for v in (leg.call_oi, leg.put_oi) if v is not None), default=None)

        evidence = []
        if worst_spread is not None:
            evidence.append(f"ATM bid-ask spread ~{worst_spread:.1f}% of mid.")
        if min_oi is not None:
            evidence.append(f"ATM open interest {min_oi:,.0f} contracts.")

        illiquid = (worst_spread is not None and worst_spread > WIDE_SPREAD_PCT) or (min_oi is not None and min_oi < THIN_OI)
        if illiquid:
            action, confidence = "WAIT", 0.5
            evidence.insert(0, "Options market too thin to trade at reasonable size/cost - flagging this pick as untradeable regardless of directional conviction.")
        else:
            action, confidence = "HOLD", 0.2
            evidence.insert(0, "No liquidity concerns at the ATM strike.")

        llm = get_llm_client()
        evidence_txt = " ".join(evidence)
        context_txt = prior_stage_summary(ctx)
        reasoning = llm.chat(
            system=(
                "You are the Liquidity Analyst on a trading committee. In 1-2 crisp sentences, state whether this "
                "symbol's options are liquid enough to actually trade at the ATM strike - bid-ask spread and open "
                "interest, not direction."
            ),
            user=f"Symbol {ctx.symbol}. Signal: {action} (confidence {confidence}). Evidence: {evidence_txt}\n\n{context_txt}",
            fallback=f"Liquidity read for {ctx.symbol}: {action}. {evidence_txt}",
        )

        return AgentVote(
            agent_name=self.name, agent_type=self.agent_type, action=action, confidence=confidence,
            reasoning=reasoning, evidence=evidence,
            metrics={"atm_spread_pct": worst_spread, "atm_min_oi": min_oi},
        )
