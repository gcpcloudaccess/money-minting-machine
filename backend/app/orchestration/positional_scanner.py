"""Positional Scanner: the ranking pass that actually produces a "best
positional options pick" - the single biggest structural gap identified in
docs/POSITIONAL_OPTIONS_ENHANCEMENT_PLAN.md. session_runner.py's tick loop
evaluates one symbol at a time from a 3-symbol intraday watchlist and outputs
a single verdict; this module instead runs the full (18-agent) committee,
in positional mode, across Settings.positional_universe every scan, and
returns a ranked list - there is no "best pick" without ranking a real
universe of candidates against each other.

Deliberately NOT wired into APScheduler's per-tick loop: a positional thesis
doesn't need re-evaluating every 10 minutes, and scanning 20 symbols x ~19
agents is much more LLM/time expensive than one intraday symbol - see
app/main.py's /positional/scan endpoint (on-demand) instead of an automatic
schedule for this build. Wiring a once-daily schedule for this is a natural
next step (see app/schedule usage elsewhere in this repo) once this has been
run and validated a few times manually.
"""

from __future__ import annotations

import logging
import uuid

from app.agents.base import AnalysisContext
from app.agents.debate_loop import run_positional_debate
from app.agents.strategy_architect import build_strategy_for_verdict
from app.config import get_settings
from app.consensus import reliability_tracker
from app.consensus.trust_weighted_consensus import compute_consensus
from app.data import calendar_data, fundamentals as fundamentals_data, news_data, options_data
from app.data.market_data import MarketDataProvider
from app.db.models import PositionalPick
from app.db.session import DbSession as Session
from app.reporting import report_agent

logger = logging.getLogger("positional_scanner")

# Ranked list is sorted on directional_confidence alone, downweighted when the
# pick isn't actually tradable (no options chain / no strategy could be
# built) - a directionally-perfect pick nobody can place isn't the "best
# pick" in practice. See docs/POSITIONAL_OPTIONS_ENHANCEMENT_PLAN.md.
NO_STRATEGY_PENALTY = 0.5


def _gather_positional_context(provider: MarketDataProvider, symbol: str, universe: list[str]) -> AnalysisContext:
    daily_bars = provider.get_daily_bars(symbol)
    try:
        benchmark_bars = provider.get_daily_bars("^NSEI")
    except Exception:
        benchmark_bars = None
    bars = provider.get_recent_bars(symbol)

    fundamentals = fundamentals_data.get_fundamentals(symbol)
    company_query = news_data.symbol_news_query(symbol, fundamentals)
    symbol_news = news_data.fetch_symbol_news(company_query)
    market_news = news_data.fetch_market_news()
    try:
        financial_statements = fundamentals_data.get_financial_statements(symbol)
    except Exception:
        financial_statements = {}

    chain = options_data.get_option_chain(symbol)
    iv_history = options_data.get_iv_history(symbol)
    if chain is not None and chain.legs:
        atm = chain.atm_strike()
        atm_leg = next((leg for leg in chain.legs if leg.strike == atm), None)
        if atm_leg is not None:
            ivs = [v for v in (atm_leg.call_iv, atm_leg.put_iv) if v is not None]
            if ivs:
                options_data.record_atm_iv(symbol, sum(ivs) / len(ivs))
                iv_history = options_data.get_iv_history(symbol)  # pick up today's just-recorded point

    settings = get_settings()
    catalyst_events = [
        {"date": e.date.isoformat(), "kind": e.kind, "label": e.label, "days_away": e.days_away}
        for e in calendar_data.get_catalyst_events(symbol, horizon_days=settings.max_days_to_expiry_positional)
    ]

    return AnalysisContext(
        symbol=symbol, bars=bars, fundamentals=fundamentals,
        symbol_news=symbol_news, market_news=market_news, peer_bars={},
        daily_bars=daily_bars, benchmark_bars=benchmark_bars, open_positions=[],
        financial_statements=financial_statements, historical_context=[],
        horizon="positional", option_chain=chain, iv_history=iv_history, catalyst_events=catalyst_events,
    )


def scan_symbol(db: Session, provider: MarketDataProvider, symbol: str, universe: list[str]) -> dict:
    """Runs the full positional committee for one symbol and returns a plain
    dict (not yet persisted) - split out from scan_universe() so a single
    symbol can be re-scanned on demand (see app/main.py's per-symbol
    drill-down endpoint) without re-running the whole universe."""
    ctx = _gather_positional_context(provider, symbol, universe)

    analyst_votes, debate_vote, critic_votes = run_positional_debate(ctx)
    all_votes = analyst_votes + [debate_vote] + critic_votes

    trust_scores = reliability_tracker.get_all_trust_scores(db)
    consensus = compute_consensus(all_votes, trust_scores, mode="positional")

    strategy = build_strategy_for_verdict(consensus.winning_action, consensus.directional_confidence, analyst_votes, ctx.option_chain)

    iv_vote = next((v for v in analyst_votes if v.agent_name == "IV & Options Chain Analyst"), None)
    iv_rank = iv_vote.metrics.get("iv_rank") if iv_vote else None

    next_catalyst = ctx.catalyst_events[0] if ctx.catalyst_events else None

    rank_score = consensus.directional_confidence
    if consensus.winning_action in ("BUY", "SELL") and strategy is None:
        rank_score *= NO_STRATEGY_PENALTY

    reasoning_text = report_agent.build_consensus_reasoning(symbol, consensus, all_votes, "")

    return {
        "symbol": symbol,
        "direction": consensus.verdict,
        "winning_action": consensus.winning_action,
        "directional_confidence": consensus.directional_confidence,
        "rank_score": round(rank_score, 3),
        "strategy": strategy,
        "iv_rank": iv_rank,
        "next_catalyst": next_catalyst,
        "consensus_reasoning": reasoning_text,
        "agent_details": consensus.agent_details,
        "agent_votes": [v.model_dump() for v in all_votes],
        "spot_price": ctx.option_chain.underlying_price if ctx.option_chain else None,
        "has_options_data": ctx.option_chain is not None,
    }


def _persist(db: Session, scan_id: str, result: dict) -> PositionalPick:
    strategy = result["strategy"]
    structure_json = {}
    if strategy is not None:
        structure_json = {
            "structure_type": strategy.structure_type,
            "expiry": strategy.expiry,
            "legs": [{"action": l.action, "option_type": l.option_type, "strike": l.strike, "premium": l.premium} for l in strategy.legs],
            "max_loss": strategy.max_loss,
            "max_profit": strategy.max_profit,
            "breakeven": strategy.breakeven,
            "payoff_points": strategy.payoff_points,
            "rationale": strategy.rationale,
            "data_complete": strategy.data_complete,
        }

    next_catalyst = result["next_catalyst"]
    row = PositionalPick(
        scan_id=scan_id,
        symbol=result["symbol"],
        direction=result["direction"],
        directional_confidence=result["directional_confidence"],
        rank_score=result["rank_score"],
        structure_type=strategy.structure_type if strategy else None,
        structure_json=structure_json,
        iv_rank=result["iv_rank"],
        days_to_next_catalyst=next_catalyst["days_away"] if next_catalyst else None,
        next_catalyst_label=next_catalyst["label"] if next_catalyst else None,
        consensus_reasoning=result["consensus_reasoning"],
        agent_details_json={"agent_details": result["agent_details"], "agent_votes": result["agent_votes"]},
    )
    db.add(row)
    return row


def scan_universe(db: Session, provider: MarketDataProvider | None = None, universe: list[str] | None = None) -> list[dict]:
    """Runs scan_symbol() for every symbol in the positional universe
    (Settings.positional_universe by default), persists every result, and
    returns them ranked by rank_score descending - the actual "best
    positional pick(s)" deliverable. A failure on one symbol is logged and
    skipped rather than aborting the whole scan, matching session_runner.py's
    per-symbol error isolation."""
    settings = get_settings()
    provider = provider or MarketDataProvider(settings.data_mode)
    universe = universe or settings.positional_universe_symbols
    scan_id = str(uuid.uuid4())

    results = []
    for symbol in universe:
        try:
            result = scan_symbol(db, provider, symbol, universe)
            _persist(db, scan_id, result)
            results.append(result)
        except Exception:
            logger.exception("Positional scan failed for %s", symbol)

    db.commit()
    results.sort(key=lambda r: r["rank_score"], reverse=True)
    return results
