"""Relative Strength Analyst: how this symbol has performed versus the Nifty
50 benchmark over the positional lookback window - a screening signal more
than a per-symbol timing one. Matters most once the universe is wide (see
Settings.positional_universe): a stock in a genuine uptrend but merely
tracking the index isn't as strong a positional candidate as one meaningfully
outperforming it, and this is the cheapest signal to compute across a whole
universe every scan (ctx.daily_bars / ctx.benchmark_bars are already fetched
for every symbol regardless, see app/orchestration/supervisor.py)."""

from __future__ import annotations

from app.agents.base import AgentVote, AnalysisContext, BaseAgent, prior_stage_summary
from app.llm.client import get_llm_client

LOOKBACK_DAYS = 20


def _period_return(bars, window: int) -> float | None:
    if bars is None or len(bars) < window + 1:
        return None
    closes = bars["Close"]
    start, end = float(closes.iloc[-(window + 1)]), float(closes.iloc[-1])
    return round((end - start) / start * 100, 2) if start else None


class RelativeStrengthAnalyst(BaseAgent):
    name = "Relative Strength Analyst"
    agent_type = "analyst"
    expertise = "relative_strength"

    def vote(self, ctx: AnalysisContext) -> AgentVote:
        own_return = _period_return(ctx.daily_bars, LOOKBACK_DAYS)
        bench_return = _period_return(ctx.benchmark_bars, LOOKBACK_DAYS)

        if own_return is None or bench_return is None:
            return AgentVote(
                agent_name=self.name, agent_type=self.agent_type, action="HOLD", confidence=0.15,
                reasoning=f"Insufficient daily-bar history for {ctx.symbol} or the benchmark to compute relative strength.",
                evidence=["Insufficient daily-bar history for a relative strength read."], metrics={},
            )

        rs_spread = round(own_return - bench_return, 2)
        evidence = [
            f"{ctx.symbol} {LOOKBACK_DAYS}d return {own_return:+.1f}% vs Nifty 50 benchmark {bench_return:+.1f}% "
            f"(relative strength {rs_spread:+.1f}pp)."
        ]

        if rs_spread >= 3.0:
            action, confidence = "BUY", round(min(0.75, 0.4 + rs_spread / 20), 3)
            evidence.append("Meaningfully outperforming the index - a stronger positional candidate than a pure index-tracker.")
        elif rs_spread <= -3.0:
            action, confidence = "SELL", round(min(0.75, 0.4 + abs(rs_spread) / 20), 3)
            evidence.append("Meaningfully underperforming the index.")
        else:
            action, confidence = "HOLD", 0.25
            evidence.append("Tracking the index closely - no strong relative-strength edge either way.")

        llm = get_llm_client()
        evidence_txt = " ".join(evidence)
        context_txt = prior_stage_summary(ctx)
        reasoning = llm.chat(
            system=(
                "You are the Relative Strength Analyst on a trading committee screening candidates for a positional "
                "options trade. In 2-3 crisp sentences, summarize how this stock has performed versus the Nifty 50 "
                "benchmark recently and what that says about it as a positional candidate versus just buying the index."
            ),
            user=f"Symbol {ctx.symbol}. Signal: {action} (confidence {confidence}). Evidence: {evidence_txt}\n\n{context_txt}",
            fallback=f"Relative strength read for {ctx.symbol}: {action}. {evidence_txt}",
        )

        return AgentVote(
            agent_name=self.name, agent_type=self.agent_type, action=action, confidence=confidence,
            reasoning=reasoning, evidence=evidence,
            metrics={"own_return_pct": own_return, "benchmark_return_pct": bench_return, "relative_strength_pp": rs_spread},
        )
