"""Persists per-agent historical reliability as a Beta(success, fail) estimate,
updated whenever a trade this agent voted on resolves (closes) in the market.
Backs the `trust_score` factor in the consensus weight formula."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import AgentReliability


def get_all_trust_scores(db: Session) -> dict[str, float]:
    rows = db.query(AgentReliability).all()
    return {r.agent_name: _reliability_score(r) for r in rows}


def get_trust_score(db: Session, agent_name: str) -> float:
    row = db.query(AgentReliability).filter_by(agent_name=agent_name).one_or_none()
    if row is None:
        return 0.5  # neutral prior for an agent with no track record yet
    return _reliability_score(row)


def _reliability_score(row: AgentReliability) -> float:
    return row.success_count / (row.success_count + row.fail_count)


def _get_or_create(db: Session, agent_name: str) -> AgentReliability:
    row = db.query(AgentReliability).filter_by(agent_name=agent_name).one_or_none()
    if row is None:
        row = AgentReliability(agent_name=agent_name, success_count=1.0, fail_count=1.0, trust_score=0.5)
        db.add(row)
        db.flush()
    return row


def record_outcome(db: Session, agent_name: str, was_correct: bool) -> None:
    row = _get_or_create(db, agent_name)
    if was_correct:
        row.success_count += 1.0
    else:
        row.fail_count += 1.0
    row.trust_score = _reliability_score(row)
    db.add(row)


def record_trade_outcome(db: Session, agent_votes: list[dict], trade_was_profitable: bool) -> None:
    """agent_votes: list of {agent_name, action} for the decision that led to this trade.
    An agent "was correct" if it voted the direction the trade actually took and that
    trade turned out profitable (or voted against a trade that would have lost)."""
    for v in agent_votes:
        acted_with_trade = v["action"] in ("BUY", "SELL", "SWITCH")
        was_correct = acted_with_trade == trade_was_profitable if acted_with_trade else True
        record_outcome(db, v["agent_name"], was_correct)
    db.commit()
