"""Isolated tests for the execution engine and cost model, using an in-memory
SQLite DB so they don't touch the real session DB. NSE only in this build."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Portfolio
from app.portfolio import portfolio_manager
from app.trading import execution_engine
from app.trading.costs import compute_costs, COST_PROFILES


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


def test_switch_verdict_without_existing_position_opens_long(db):
    """SWITCH means "prefer a different stock" relative to an existing holding -
    with no current position in this symbol, that has nothing to switch out of,
    so it should resolve to a real BUY rather than silently no-op'ing a verdict
    the consensus engine already committed to."""
    portfolio = Portfolio(cash_inr=10000.0, starting_capital=10000.0, leverage=2.0, status="active")
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)

    result = portfolio_manager.process_decision(
        db, portfolio, "RELIANCE.NS", verdict="SWITCH", directional_confidence_pct=25.0,
        risk_level="MEDIUM", volatility=0.01, price=1000.0, decision_id=None,
    )
    assert result["executed"] is True
    assert result["action"] == "OPEN_LONG_FROM_SWITCH"
    position = execution_engine.get_open_position(db, portfolio, "RELIANCE.NS")
    assert position is not None


def test_switch_verdict_with_existing_position_closes_it(db):
    portfolio = Portfolio(cash_inr=10000.0, starting_capital=10000.0, leverage=2.0, status="active")
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    execution_engine.open_position(db, portfolio, "RELIANCE.NS", "LONG", 5, 1000.0, decision_id=None)

    result = portfolio_manager.process_decision(
        db, portfolio, "RELIANCE.NS", verdict="SWITCH", directional_confidence_pct=25.0,
        risk_level="MEDIUM", volatility=0.01, price=1010.0, decision_id=None,
    )
    assert result["executed"] is True
    assert result["action"] == "CLOSE_LONG"
    assert execution_engine.get_open_position(db, portfolio, "RELIANCE.NS") is None


def test_nse_cost_profile_produces_nonnegative_costs():
    assert list(COST_PROFILES) == ["NSE"]
    buy = compute_costs("BUY", 10, 10_000.0, exchange="NSE", fx_rate_to_inr=1.0)
    sell = compute_costs("SELL", 10, 10_000.0, exchange="NSE", fx_rate_to_inr=1.0)
    assert buy["total"] >= 0
    assert sell["total"] >= 0


def test_get_active_portfolio_tags_new_portfolio_with_nse(db):
    portfolio = execution_engine.get_active_portfolio(db, exchange="NSE")
    assert portfolio.exchange == "NSE"


def test_get_active_portfolio_defaults_to_nse_when_no_exchange_given(db):
    portfolio = execution_engine.get_active_portfolio(db)
    assert portfolio.exchange == "NSE"


def test_open_position_stores_exchange_and_fx_metadata(db):
    portfolio = Portfolio(cash_inr=10000.0, starting_capital=10000.0, leverage=2.0, status="active", exchange="NSE")
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)

    trade = execution_engine.open_position(
        db, portfolio, "NIFTYBEES.NS", "LONG", 5, 250.0, decision_id=None,
        exchange="NSE", currency="INR", price_local=250.0, fx_rate_to_inr=1.0,
    )
    position = execution_engine.get_open_position(db, portfolio, "NIFTYBEES.NS")

    assert trade.exchange == "NSE"
    assert trade.currency == "INR"
    assert trade.price_local == 250.0
    assert trade.fx_rate_to_inr == 1.0
    assert position.exchange == "NSE"
    assert position.currency == "INR"


def test_force_close_all(db):
    portfolio = Portfolio(cash_inr=10000.0, starting_capital=10000.0, leverage=2.0, status="active")
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)

    execution_engine.open_position(db, portfolio, "GOLDBEES.NS", "LONG", 2, 3000.0, decision_id=None)
    execution_engine.open_position(db, portfolio, "SILVERBEES.NS", "LONG", 3, 1500.0, decision_id=None)

    trades = execution_engine.force_close_all(db, portfolio, {"GOLDBEES.NS": 3100.0, "SILVERBEES.NS": 1480.0})
    assert len(trades) == 2
    assert execution_engine.get_open_exposure(db, portfolio) == 0.0
