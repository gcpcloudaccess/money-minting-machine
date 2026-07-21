import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cash_inr: Mapped[float] = mapped_column(Float)
    starting_capital: Mapped[float] = mapped_column(Float)
    leverage: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | closed
    exchange: Mapped[str] = mapped_column(String(16), default="NSE")  # NSE only in this build - which market this session trades
    session_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    session_end: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    positions: Mapped[list["Position"]] = relationship(back_populates="portfolio")
    trades: Mapped[list["Trade"]] = relationship(back_populates="portfolio")


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8))  # LONG | SHORT
    quantity: Mapped[float] = mapped_column(Float)
    avg_price: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | closed
    opened_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    exchange: Mapped[str] = mapped_column(String(16), default="NSE")
    currency: Mapped[str] = mapped_column(String(8), default="INR")  # local currency the position was priced in
    fx_rate_to_inr: Mapped[float] = mapped_column(Float, default=1.0)  # rate at open time, for explainability

    portfolio: Mapped["Portfolio"] = relationship(back_populates="positions")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    verdict: Mapped[str] = mapped_column(String(16))  # BUY | SELL | HOLD | WAIT | SWITCH
    directional_confidence: Mapped[float] = mapped_column(Float)
    consensus_reasoning: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    alternatives_json: Mapped[dict] = mapped_column(JSON, default=dict)
    critic_feedback_json: Mapped[dict] = mapped_column(JSON, default=dict)
    expected_risk_return_json: Mapped[dict] = mapped_column(JSON, default=dict)
    executed: Mapped[bool] = mapped_column(Boolean, default=False)

    agent_votes: Mapped[list["AgentVote"]] = relationship(back_populates="decision")
    trades: Mapped[list["Trade"]] = relationship(back_populates="decision")


class AgentVote(Base):
    __tablename__ = "agent_votes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id"))
    agent_name: Mapped[str] = mapped_column(String(64))
    agent_type: Mapped[str] = mapped_column(String(16))  # analyst | critic
    action: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column(Float)
    reasoning: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    weight_used: Mapped[float] = mapped_column(Float, default=0.0)

    decision: Mapped["Decision"] = relationship(back_populates="agent_votes")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    decision_id: Mapped[int | None] = mapped_column(ForeignKey("decisions.id"), nullable=True)
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"), nullable=True)
    symbol: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(16))  # BUY | SELL
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)  # INR-equivalent price used for all ledger math
    gross_value: Mapped[float] = mapped_column(Float)
    total_costs: Mapped[float] = mapped_column(Float)
    cost_breakdown_json: Mapped[dict] = mapped_column(JSON, default=dict)
    net_cash_impact: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    exchange: Mapped[str] = mapped_column(String(16), default="NSE")
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    price_local: Mapped[float] = mapped_column(Float, default=0.0)  # price in the exchange's own currency, for display
    fx_rate_to_inr: Mapped[float] = mapped_column(Float, default=1.0)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="trades")
    decision: Mapped["Decision"] = relationship(back_populates="trades")
    position: Mapped["Position | None"] = relationship()


class AgentReliability(Base):
    __tablename__ = "agent_reliability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(64), unique=True)
    success_count: Mapped[float] = mapped_column(Float, default=1.0)  # Beta prior alpha
    fail_count: Mapped[float] = mapped_column(Float, default=1.0)  # Beta prior beta
    trust_score: Mapped[float] = mapped_column(Float, default=0.6)
    last_updated: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResearchNote(Base):
    __tablename__ = "research_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    category: Mapped[str] = mapped_column(String(32))  # news | policy | technical | fundamental ...
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(String(256), default="")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    event_type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
