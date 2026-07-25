"""Unit tests for F&O expiry date computation (app/data/calendar_data.py) -
pure date math, no network required."""

import datetime as dt

from app.data import calendar_data


def test_index_weekly_expiries_land_on_configured_weekday():
    today = dt.date(2026, 7, 25)  # a Saturday
    expiries = calendar_data.next_fno_expiries("^NSEI", count=4, today=today)
    assert len(expiries) == 4
    for e in expiries:
        assert e.weekday() == calendar_data.get_settings().options_expiry_weekday
        assert e >= today


def test_index_weekly_expiries_are_seven_days_apart():
    today = dt.date(2026, 7, 25)
    expiries = calendar_data.next_fno_expiries("^NSEI", count=3, today=today)
    assert (expiries[1] - expiries[0]).days == 7
    assert (expiries[2] - expiries[1]).days == 7


def test_stock_monthly_expiries_are_last_configured_weekday_of_month():
    today = dt.date(2026, 7, 25)
    expiries = calendar_data.next_fno_expiries("RELIANCE.NS", count=2, today=today)
    assert len(expiries) == 2
    for e in expiries:
        assert e.weekday() == calendar_data.get_settings().options_expiry_weekday
        # Must be the LAST such weekday in its month - adding 7 days should push into the next month.
        assert (e + dt.timedelta(days=7)).month != e.month


def test_rbi_mpc_dates_empty_by_default():
    # Default Settings() has RBI_MPC_DATES unset - must degrade to an empty list, not raise.
    assert isinstance(calendar_data.get_rbi_mpc_dates(), list)


def test_get_catalyst_events_never_raises_without_network():
    # get_upcoming_earnings() hits yfinance - must degrade gracefully (empty/partial list) if unreachable, never raise.
    events = calendar_data.get_catalyst_events("RELIANCE.NS", horizon_days=45)
    assert isinstance(events, list)
    for e in events:
        assert e.kind in ("earnings", "fno_expiry", "rbi_mpc")
