"""IV & Options Chain Analyst: reads the options market itself (implied
volatility rank, put-call OI ratio, max pain, OI buildup) rather than the
underlying's price action - a genuinely different information source from
every other analyst in this committee, and the one the whole "positional
options pick" goal is missing without it (see docs/
POSITIONAL_OPTIONS_ENHANCEMENT_PLAN.md: this system had zero options
infrastructure before this agent existed).

Positional-mode only: intraday ticks don't populate AnalysisContext.option_chain
(see app/orchestration/session_runner.py vs positional_scanner.py), so this
agent degrades to a low-confidence HOLD with a clear "no options data" note
whenever it's run outside a positional scan - it never silently fabricates a
view."""

from __future__ import annotations

import datetime as dt

from app.agents.base import AgentVote, AnalysisContext, BaseAgent, prior_stage_summary
from app.llm.client import get_llm_client
from app.tools import options_analytics

_EXPIRY_FORMATS = ("%d-%b-%Y", "%Y-%m-%d")


def _parse_expiry(expiry: str) -> dt.date | None:
    for fmt in _EXPIRY_FORMATS:
        try:
            return dt.datetime.strptime(expiry, fmt).date()
        except ValueError:
            continue
    return None


def _days_to_expiry(expiry: str | None) -> float:
    if not expiry:
        return 30.0
    parsed = _parse_expiry(expiry)
    if parsed is None:
        return 30.0
    return max((parsed - dt.datetime.now(dt.timezone.utc).date()).days, 1)


def _spot_change_pct(ctx: AnalysisContext) -> float:
    bars = ctx.daily_bars if ctx.daily_bars is not None and len(ctx.daily_bars) >= 2 else ctx.bars
    if bars is None or len(bars) < 2:
        return 0.0
    prev, last = float(bars["Close"].iloc[-2]), float(bars["Close"].iloc[-1])
    return round((last - prev) / prev * 100, 2) if prev else 0.0


class IVOptionsAnalyst(BaseAgent):
    name = "IV & Options Chain Analyst"
    agent_type = "analyst"
    expertise = "options_iv"

    def vote(self, ctx: AnalysisContext) -> AgentVote:
        if ctx.option_chain is None:
            return AgentVote(
                agent_name=self.name, agent_type=self.agent_type, action="HOLD", confidence=0.15,
                reasoning=f"No live options chain available for {ctx.symbol} this run (NSE unreachable, or not an F&O symbol).",
                evidence=["No live options chain data this run."], metrics={},
            )

        expiry = ctx.option_chain.nearest_expiry()
        days_to_expiry = _days_to_expiry(expiry)
        signal = options_analytics.analyze(ctx.option_chain, ctx.iv_history, _spot_change_pct(ctx), days_to_expiry)

        llm = get_llm_client()
        evidence_txt = " ".join(signal["evidence"])
        context_txt = prior_stage_summary(ctx)
        reasoning = llm.chat(
            system=(
                "You are the IV & Options Chain Analyst on a trading committee evaluating a multi-week positional "
                "options trade. Summarize what the options market itself (implied volatility, open interest "
                "positioning, max pain) suggests in 2-3 crisp sentences - this is about options-market positioning, "
                "not the stock's own price action, which other analysts already cover."
            ),
            user=f"Symbol {ctx.symbol}. Signal: {signal['action']} (confidence {signal['confidence']}). Evidence: {evidence_txt}\n\n{context_txt}",
            fallback=f"Options-market read for {ctx.symbol}: {signal['action']}. {evidence_txt}",
        )

        return AgentVote(
            agent_name=self.name, agent_type=self.agent_type, action=signal["action"], confidence=signal["confidence"],
            reasoning=reasoning, evidence=signal["evidence"], metrics=signal["metrics"],
        )
