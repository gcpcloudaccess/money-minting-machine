"""Unit tests proving NSE and CRYPTO_INDIA keep independent, concurrently-
active portfolios (app/trading/execution_engine.py's get_active_portfolio is
now exchange-scoped - see app/orchestration/session_runner.py for why this
matters: crypto trades 24/7 while NSE only trades its own session hours, so
there's no longer a single global "the active portfolio"). Uses an in-memory
SQLite DB (not the fixture-based `db` in test_trading.py, so this also runs
outside pytest) - no network/LLM key required."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.trading import execution_engine


def _make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_nse_and_crypto_get_separate_portfolios():
    db = _make_db()
    nse_portfolio = execution_engine.get_active_portfolio(db, exchange="NSE")
    crypto_portfolio = execution_engine.get_active_portfolio(db, exchange="CRYPTO_INDIA")
    assert nse_portfolio.id != crypto_portfolio.id
    assert nse_portfolio.exchange == "NSE"
    assert crypto_portfolio.exchange == "CRYPTO_INDIA"
    db.close()


def test_repeated_calls_return_the_same_portfolio_per_exchange():
    db = _make_db()
    first = execution_engine.get_active_portfolio(db, exchange="CRYPTO_INDIA")
    second = execution_engine.get_active_portfolio(db, exchange="CRYPTO_INDIA")
    assert first.id == second.id
    db.close()


def test_closing_one_exchange_does_not_affect_the_other():
    db = _make_db()
    nse_portfolio = execution_engine.get_active_portfolio(db, exchange="NSE")
    crypto_portfolio = execution_engine.get_active_portfolio(db, exchange="CRYPTO_INDIA")

    nse_portfolio.status = "closed"
    db.add(nse_portfolio)
    db.commit()

    # NSE gets a fresh portfolio since its old one is now closed...
    new_nse_portfolio = execution_engine.get_active_portfolio(db, exchange="NSE")
    assert new_nse_portfolio.id != nse_portfolio.id

    # ...but crypto's is completely untouched.
    still_crypto_portfolio = execution_engine.get_active_portfolio(db, exchange="CRYPTO_INDIA")
    assert still_crypto_portfolio.id == crypto_portfolio.id
    assert still_crypto_portfolio.status == "active"
    db.close()


def test_default_exchange_is_still_nse():
    db = _make_db()
    portfolio = execution_engine.get_active_portfolio(db)
    assert portfolio.exchange == "NSE"
    db.close()
