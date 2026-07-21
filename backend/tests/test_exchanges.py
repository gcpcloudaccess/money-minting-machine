"""Tests for the exchange registry (app/data/exchanges.py) - NSE only in this
build. No network, no LLM key required."""

import datetime as dt
from zoneinfo import ZoneInfo

from app.data import exchanges as ex


def test_nse_open_during_its_own_hours_on_a_weekday():
    t = dt.datetime(2026, 7, 8, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))  # Wednesday
    assert ex.NSE.is_open(t)
    assert ex.get_open_exchange(t).code == "NSE"


def test_nse_closed_on_weekend():
    # 2026-07-11 is a Saturday
    t = dt.datetime(2026, 7, 11, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert not ex.NSE.is_open(t)
    assert ex.get_open_exchange(t) is None


def test_nse_closed_before_open_and_after_close():
    before = dt.datetime(2026, 7, 8, 9, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    after = dt.datetime(2026, 7, 8, 15, 45, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert not ex.NSE.is_open(before)
    assert not ex.NSE.is_open(after)


def test_infer_exchange_from_symbol_suffix_and_fallback():
    assert ex.infer_exchange_from_symbol("RELIANCE.NS").code == "NSE"
    assert ex.infer_exchange_from_symbol("GOLDBEES.NS").code == "NSE"
    # No suffix (e.g. the ^NSEI index symbol, or a bare foreign ticker) - this
    # build only supports NSE, so it still resolves there.
    assert ex.infer_exchange_from_symbol("^NSEI").code == "NSE"
    assert ex.infer_exchange_from_symbol("AAPL").code == "NSE"


def test_only_nse_is_registered():
    assert [e.code for e in ex.ALL_EXCHANGES] == ["NSE"]
    assert ex.NSE.currency == "INR"


def test_default_watchlist_is_nifty_spot_and_mcx_gold_silver_proxies():
    assert ex.NSE.watchlist == ("^NSEI", "GOLDBEES.NS", "SILVERBEES.NS")
