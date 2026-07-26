"""Catalyst/events calendar: earnings dates, F&O expiry, and RBI MPC meeting
dates - the events a positional options thesis has to survive (or be timed
around) between entry and expiry.

Same "don't fabricate what we don't have a free live feed for" stance as
app/config.py's MACRO_* settings: RBI MPC dates have no free live feed, so
they're a manually-updated setting (RBI_MPC_DATES in .env, sourced from the
RBI website - published well in advance, so periodic manual updates are
fine), not scraped or guessed. F&O expiry is computed from NSE's public
weekday rule. Earnings dates come from yfinance, which does carry them for
NSE tickers (unlike options data)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import yfinance as yf

from app.config import get_settings


@dataclass
class CatalystEvent:
    date: dt.date
    kind: str  # earnings | fno_expiry | rbi_mpc
    label: str

    @property
    def days_away(self) -> int:
        return (self.date - dt.datetime.now(dt.timezone.utc).date()).days


def _next_weekday_on_or_after(start: dt.date, weekday: int) -> dt.date:
    delta = (weekday - start.weekday()) % 7
    return start + dt.timedelta(days=delta)


def next_fno_expiries(symbol: str, count: int = 3, today: dt.date | None = None) -> list[dt.date]:
    """Next `count` NSE F&O expiry dates for this symbol's weekly/monthly
    cadence. NSE has changed the specific weekday for index weekly expiries
    more than once (Thursday, then Tuesday, and it may change again) - rather
    than hardcode a weekday that will silently go stale, this reads
    Settings.options_expiry_weekday (default Tuesday, matching the most
    recent NSE change as of this build) so it's a one-line config fix instead
    of a code change when NSE moves it again. Single-stock options only have
    a monthly expiry (last trading day of the weekday cycle in the expiry
    month), not weekly."""
    settings = get_settings()
    today = today or dt.datetime.now(dt.timezone.utc).date()
    weekday = settings.options_expiry_weekday

    is_index = symbol in ("^NSEI", "^NSEBANK")
    if is_index:
        out = []
        cursor = _next_weekday_on_or_after(today, weekday)
        for _ in range(count):
            out.append(cursor)
            cursor = cursor + dt.timedelta(days=7)
        return out

    # Single-stock: monthly expiry only - last `weekday` of each of the next `count` months.
    out = []
    year, month = today.year, today.month
    for _ in range(count):
        if month == 12:
            next_month_first = dt.date(year + 1, 1, 1)
        else:
            next_month_first = dt.date(year, month + 1, 1)
        last_day_of_month = next_month_first - dt.timedelta(days=1)
        back = (last_day_of_month.weekday() - weekday) % 7
        expiry = last_day_of_month - dt.timedelta(days=back)
        if expiry >= today:
            out.append(expiry)
        month = (month % 12) + 1
        if month == 1:
            year += 1
    return out[:count]


def get_upcoming_earnings(symbol: str) -> dt.date | None:
    """Next known earnings date, or None if yfinance has nothing for this
    ticker (common for smaller NSE names - not every symbol has analyst-
    estimate coverage)."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.get_earnings_dates(limit=8)
        if df is None or df.empty:
            return None
        today = dt.datetime.now(dt.timezone.utc).date()
        future = [ts.date() for ts in df.index if ts.date() >= today]
        return min(future) if future else None
    except Exception:
        return None


def get_rbi_mpc_dates() -> list[dt.date]:
    settings = get_settings()
    if not settings.rbi_mpc_dates:
        return []
    out = []
    for token in settings.rbi_mpc_dates.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.append(dt.date.fromisoformat(token))
        except ValueError:
            continue
    return out


def get_catalyst_events(symbol: str, horizon_days: int = 45) -> list[CatalystEvent]:
    """All known catalysts for `symbol` within the next `horizon_days` -
    earnings, its next F&O expiry, and any upcoming RBI MPC meeting (relevant
    to every symbol since it's a market-wide rate event). This is what the
    Catalyst Analyst and the dashboard's event timeline both consume."""
    today = dt.datetime.now(dt.timezone.utc).date()
    cutoff = today + dt.timedelta(days=horizon_days)
    events: list[CatalystEvent] = []

    earnings = get_upcoming_earnings(symbol)
    if earnings and earnings <= cutoff:
        events.append(CatalystEvent(date=earnings, kind="earnings", label=f"{symbol} earnings"))

    # F&O expiry only genuinely applies to symbols with a real listed options
    # chain. next_fno_expiries() would happily compute a synthetic monthly
    # date for anything (it has no way to know a symbol lacks F&O contracts),
    # but fabricating an expiry catalyst for GOLDBEES/SILVERBEES/BTCINR (none
    # of which have listed NSE options) would be a fake event, contradicting
    # this module's own "don't fabricate what we don't have a feed for"
    # stance. Restrict to the two index symbols that actually have one.
    if symbol in ("^NSEI", "^NSEBANK"):
        for expiry in next_fno_expiries(symbol, count=2, today=today):
            if expiry <= cutoff:
                events.append(CatalystEvent(date=expiry, kind="fno_expiry", label=f"{symbol} F&O expiry"))

    for mpc_date in get_rbi_mpc_dates():
        if today <= mpc_date <= cutoff:
            events.append(CatalystEvent(date=mpc_date, kind="rbi_mpc", label="RBI MPC policy announcement"))

    return sorted(events, key=lambda e: e.date)
