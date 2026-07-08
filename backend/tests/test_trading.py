"""Isolated tests for the execution engine and cost model, using an in-memory
SQLite DB so they don't touch the real session DB."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Portfolio
from app.trading import execution_engine
from app.trading.costs import compute_costs


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_costs_buy_vs_sell_asymmetry():
    buy = compute_costs("BUY", 10, 1000.0)
    sell = compute_costs("SELL", 10, 1000.0)
    assert buy["stt"] == 0.0
    assert sell["stt"] > 0.0
    assert buy["stamp_duty"] > 0.0
    assert sell["stamp_duty"] == 0.0
    assert sell["total"] > buy["total"]  # STT only on sell side


def test_open_and_close_position_updates_cash(db):
    portfolio = Portfolio(cash_inr=10000.0, starting_capital=10000.0, leverage=2.0, status="active")
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)

    trade = execution_engine.open_position(db, portfolio, "RELIANCE.NS", "LONG", 5, 1000.0, decision_id=None)
    assert trade.action == "BUY"
    assert portfolio.cash_inr < 10000.0 - 5 * 1000.0  # cash reduced by notional + costs (costs > 0)

    position = execution_engine.get_open_position(db, portfolio, "RELIANCE.NS")
    assert position is not None
    assert position.quantity == 5

    cash_before_close = portfolio.cash_inr
    close_trade = execution_engine.close_position(db, portfolio, position, 1050.0, decision_id=None)
    assert close_trade.action == "SELL"
    assert portfolio.cash_inr > cash_before_close  # proceeds credited back
    assert position.status == "closed"
    assert position.realized_pnl is not None
    # profitable move (1000 -> 1050) minus costs should still be net positive
    assert position.realized_pnl > 0


def test_force_close_all(db):
    portfolio = Portfolio(cash_inr=10000.0, starting_capital=10000.0, leverage=2.0, status="active")
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)

    execution_engine.open_position(db, portfolio, "TCS.NS", "LONG", 2, 3000.0, decision_id=None)
    execution_engine.open_position(db, portfolio, "INFY.NS", "LONG", 3, 1500.0, decision_id=None)

    trades = execution_engine.force_close_all(db, portfolio, {"TCS.NS": 3100.0, "INFY.NS": 1480.0})
    assert len(trades) == 2
    assert execution_engine.get_open_exposure(db, portfolio) == 0.0
