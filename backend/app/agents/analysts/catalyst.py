"""Catalyst & Events Analyst: earnings dates, F&O expiry, RBI MPC meetings -
the events a positional options thesis has to survive between entry and
expiry (see app/data/calendar_data.py). This is what stops the system from
recommending a 3-week call the day before an earnings-day IV crush wipes out
the premium regardless of whether the direction was right.

Deliberately conservative in how much it moves the verdict (see its
DAYS_AHEAD_ALERT threshold and its lower expertise_relevance in
POSITIONAL_EXPERTISE_RELEVANCE): it should flag risk around a genuine
near-term catalyst, not silently veto every pick just because SOME event
exists somewhere in the horizon."""

from __future__ import annotations

from app.agents.base import AgentVote, AnalysisContext, BaseAgent, prior_stage_summary
from app.llm.client import get_llm_client

DAYS_AHEAD_ALERT = 5  # a catalyst this close to entry is a real near-term risk, not just calendar noise


class CatalystAnalyst(BaseAgent):
    name = "Catalyst & Events Analyst"
    agent_type = "analyst"
    expertise = "catalysts"

    def vote(self, ctx: AnalysisContext) -> AgentVote:
        events = sorted(ctx.catalyst_events, key=lambda e: e.get("days_away", 999))
        if not events:
            return AgentVote(
                agent_name=self.name, agent_type=self.agent_type, action="HOLD", confidence=0.2,
                reasoning=f"No known upcoming catalysts for {ctx.symbol} in the scan horizon.",
                evidence=["No earnings/expiry/RBI MPC events found in horizon."], metrics={"events": []},
            )

        near = [e for e in events if e.get("days_away", 999) <= DAYS_AHEAD_ALERT]
        evidence = [f"{e['label']} in {e['days_away']}d ({e['date']})." for e in events[:4]]

        if near:
            earnings_near = any(e["kind"] == "earnings" for e in near)
            action = "WAIT"
            confidence = 0.55 if earnings_near else 0.35
            evidence.insert(0, f"{len(near)} catalyst(s) within {DAYS_AHEAD_ALERT} days - elevated near-term event risk" + (" (earnings: IV crush risk)." if earnings_near else "."))
        else:
            action, confidence = "HOLD", 0.2
            evidence.insert(0, f"Nearest catalyst is {events[0]['days_away']}d away - no immediate event risk to a fresh entry.")

        llm = get_llm_client()
        evidence_txt = " ".join(evidence)
        context_txt = prior_stage_summary(ctx)
        reasoning = llm.chat(
            system=(
                "You are the Catalyst & Events Analyst on a trading committee evaluating a multi-week positional "
                "options trade. Summarize in 2-3 crisp sentences what's coming up (earnings, F&O expiry, RBI policy) "
                "and whether it's safe to hold an options position through it, especially IV-crush risk around "
                "earnings."
            ),
            user=f"Symbol {ctx.symbol}. Signal: {action} (confidence {confidence}). Evidence: {evidence_txt}\n\n{context_txt}",
            fallback=f"Catalyst read for {ctx.symbol}: {action}. {evidence_txt}",
        )

        return AgentVote(
            agent_name=self.name, agent_type=self.agent_type, action=action, confidence=confidence,
            reasoning=reasoning, evidence=evidence, metrics={"events": events},
        )
