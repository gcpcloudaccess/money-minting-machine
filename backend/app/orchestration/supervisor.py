"""Supervisor: wires the full per-symbol pipeline for one committee run —
data gathering -> analyst/critic debate -> trust-weighted consensus ->
portfolio decision -> persistence. Used both for scheduled session ticks and
for on-demand "Stock Search" analysis (execute=False previews without trading)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.base import AnalysisContext
from app.agents.debate_loop import run_debate
from app.consensus import reliability_tracker
from app.consensus.trust_weighted_consensus import compute_consensus
from app.data import fundamentals as fundamentals_data
from app.data import news_data
from app.data.market_data import MarketDataProvider
from app.db.models import AgentVote as AgentVoteRow
from app.db.models import Decision, Position
from app.portfolio import portfolio_manager, scenario_analysis
from app.reporting import alert_agent, audit_log, report_agent
from app.trading import execution_engine

BENCHMARK_SYMBOL = "^NSEI"  # Nifty 50 - used by the Risk Assessment Analyst for beta/correlation/regime risk


def _current_open_positions(db: Session, symbol: str, sector: str | None) -> list[dict]:
    portfolio = execution_engine.get_active_portfolio(db)
    positions = db.query(Position).filter_by(portfolio_id=portfolio.id, status="open").all()
    out = []
    for p in positions:
        out.append({
            "symbol": p.symbol,
            "weight": p.quantity * p.avg_price,
            "sector": sector if p.symbol == symbol else None,
        })
    return out


def run_committee_for_symbol(
    db: Session,
    provider: MarketDataProvider,
    symbol: str,
    watchlist: list[str],
    execute: bool = True,
) -> dict:
    bars = provider.get_recent_bars(symbol)
    peer_bars = {s: provider.get_recent_bars(s) for s in watchlist if s != symbol}
    peer_bars[symbol] = bars

    try:
        daily_bars = provider.get_daily_bars(symbol)
    except Exception:
        daily_bars = None
    try:
        benchmark_bars = provider.get_daily_bars(BENCHMARK_SYMBOL)
    except Exception:
        benchmark_bars = None

    fundamentals = fundamentals_data.get_fundamentals(symbol)
    company_query = fundamentals.get("short_name") or symbol.split(".")[0]
    symbol_news = news_data.fetch_symbol_news(company_query)
    market_news = news_data.fetch_market_news()
    open_positions = _current_open_positions(db, symbol, fundamentals.get("sector"))

    ctx = AnalysisContext(
        symbol=symbol, bars=bars, fundamentals=fundamentals,
        symbol_news=symbol_news, market_news=market_news, peer_bars=peer_bars,
        daily_bars=daily_bars, benchmark_bars=benchmark_bars, open_positions=open_positions,
    )

    analyst_votes, debate_vote, critic_votes = run_debate(ctx)
    all_votes = analyst_votes + [debate_vote] + critic_votes

    trust_scores = reliability_tracker.get_all_trust_scores(db)
    consensus = compute_consensus(all_votes, trust_scores)

    risk_vote = next((v for v in analyst_votes if v.agent_name == "Risk Assessment Analyst"), None)
    risk_level = (risk_vote.metrics.get("risk_level") if risk_vote else None) or "MEDIUM"
    volatility = risk_vote.metrics.get("volatility") if risk_vote else None

    opp_vote = next((v for v in critic_votes if v.agent_name == "Opportunity Critic"), None)
    alternatives = opp_vote.metrics.get("alternatives", []) if opp_vote else []

    price = provider.get_latest_price(symbol)
    reasoning_text = report_agent.build_consensus_reasoning(symbol, consensus, all_votes)

    decision_row = Decision(
        symbol=symbol,
        verdict=consensus.verdict,
        directional_confidence=consensus.directional_confidence,
        consensus_reasoning=reasoning_text,
        evidence_json={"agent_details": consensus.agent_details},
        alternatives_json={"alternatives": alternatives},
        critic_feedback_json={"critics": [v.model_dump() for v in critic_votes]},
        expected_risk_return_json={},
    )
    db.add(decision_row)
    db.flush()

    for v in all_votes:
        db.add(
            AgentVoteRow(
                decision_id=decision_row.id,
                agent_name=v.agent_name,
                agent_type=v.agent_type,
                action=v.action,
                confidence=v.confidence,
                reasoning=v.reasoning,
                evidence_json={"evidence": v.evidence},
                weight_used=consensus.agent_weights.get(v.agent_name, 0.0),
            )
        )

    if execute:
        portfolio = execution_engine.get_active_portfolio(db)
        execution_result = portfolio_manager.process_decision(
            db, portfolio, symbol, consensus.verdict, consensus.directional_confidence,
            risk_level, volatility, price, decision_row.id,
        )
    else:
        nominal_qty = max(int(1000 / price), 1) if price else 1
        execution_result = {
            "executed": False,
            "reason": "Preview mode (Stock Search) - no trade executed.",
            "scenario": scenario_analysis.stress_test(price, nominal_qty, "LONG", volatility),
        }

    if execution_result.get("scenario"):
        decision_row.expected_risk_return_json = execution_result["scenario"]
    decision_row.executed = bool(execution_result.get("executed"))
    db.add(decision_row)
    db.commit()
    db.refresh(decision_row)

    alerts = alert_agent.evaluate(symbol, consensus.verdict, consensus.directional_confidence, risk_level, alternatives)
    audit_log.log_event(db, "committee_decision", {
        "symbol": symbol, "verdict": consensus.verdict,
        "directional_confidence": consensus.directional_confidence,
        "executed": decision_row.executed, "alerts": alerts,
    })

    return {
        "symbol": symbol,
        "price": price,
        "verdict": consensus.verdict,
        "directional_confidence": consensus.directional_confidence,
        "consensus_reasoning": reasoning_text,
        "agent_votes": [v.model_dump() for v in analyst_votes],
        "debate": debate_vote.model_dump(),
        "critic_feedback": [v.model_dump() for v in critic_votes],
        "alternatives": alternatives,
        "expected_risk_return": decision_row.expected_risk_return_json,
        "execution": execution_result,
        "alerts": alerts,
        "decision_id": decision_row.id,
    }
