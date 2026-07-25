"""Tests for the exchange registry (app/data/exchanges.py) - NSE (session
hours) plus CRYPTO_INDIA (always open) in this build. No network, no LLM key
required."""

import datetime as dt
from zoneinfo import ZoneInfo

from app.data import exchanges as ex


def test_nse_open_during_its_own_hours_on_a_weekday():
    t = dt.datetime(2026, 7, 8, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))  # Wednesday
    assert ex.NSE.is_open(t)
    assert ex.get_open_exchange(t).code == "NSE"  # NSE checked first in ALL_EXCHANGES order


def test_nse_closed_on_weekend_but_crypto_stays_open():
    # 2026-07-11 is a Saturday
    t = dt.datetime(2026, 7, 11, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert not ex.NSE.is_open(t)
    assert ex.CRYPTO_INDIA.is_open(t)
    # get_open_exchange() returns the first open exchange in ALL_EXCHANGES order -
    # with NSE closed, that's crypto, not None (see session_runner.py, which
    # ticks every open exchange independently rather than relying on this
    # function alone to decide what runs).
    assert ex.get_open_exchange(t).code == "CRYPTO_INDIA"


def test_nse_closed_before_open_and_after_close():
    before = dt.datetime(2026, 7, 8, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    after = dt.datetime(2026, 7, 8, 15, 45, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert not ex.NSE.is_open(before)
    assert not ex.NSE.is_open(after)


def test_crypto_open_every_day_including_weekend_and_late_night():
    saturday_midnight = dt.datetime(2026, 7, 11, 0, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    sunday_late = dt.datetime(2026, 7, 12, 23, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    weekday_after_nse_close = dt.datetime(2026, 7, 8, 20, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    for t in (saturday_midnight, sunday_late, weekday_after_nse_close):
        assert ex.CRYPTO_INDIA.is_open(t)


def test_infer_exchange_from_symbol_suffix_and_fallback():
    assert ex.infer_exchange_from_symbol("RELIANCE.NS").code == "NSE"
    assert ex.infer_exchange_from_symbol("GOLDBEES.NS").code == "NSE"
    # No suffix (e.g. the ^NSEI index symbol, or a bare foreign ticker) - falls
    # back to NSE, the default exchange.
    assert ex.infer_exchange_from_symbol("^NSEI").code == "NSE"
    assert ex.infer_exchange_from_symbol("AAPL").code == "NSE"


def test_infer_exchange_from_symbol_resolves_crypto_by_watchlist():
    assert ex.infer_exchange_from_symbol("BTCINR").code == "CRYPTO_INDIA"
    assert ex.infer_exchange_from_symbol("btcinr").code == "CRYPTO_INDIA"  # case-insensitive


def test_nse_and_crypto_india_are_registered():
    assert [e.code for e in ex.ALL_EXCHANGES] == ["NSE", "CRYPTO_INDIA"]
    assert ex.NSE.currency == "INR"
    assert ex.CRYPTO_INDIA.currency == "INR"


def test_default_watchlist_is_nifty_spot_and_mcx_gold_silver_proxies():
    assert ex.NSE.watchlist == ("^NSEI", "GOLDBEES.NS", "SILVERBEES.NS")


def test_crypto_watchlist_is_btc_only():
    # PI (Pi Network) deliberately excluded - not listed on any major/vetted
    # Indian exchange yet, see CRYPTO_INDIA's definition in exchanges.py.
    assert ex.CRYPTO_INDIA.watchlist == ("BTCINR",)
