"""Exchange registry: NSE only.

This build is scoped to the Indian market exclusively - the tradable universe
is the Nifty 50 index itself (^NSEI - yfinance has no NSE Nifty *futures*
contract data at all, only the spot index and NSE cash-market/ETF symbols, so
this is a paper-trading abstraction: "buying" ^NSEI means a synthetic
notional position sized in index points, not a real placeable order - fine
here since nothing is ever actually executed on a real exchange) plus MCX
gold/silver, tracked through their NSE-listed ETF proxies (GOLDBEES.NS /
SILVERBEES.NS) since yfinance doesn't carry live MCX commodity futures data
either. The gold/silver ETFs stay genuinely tradable NSE instruments; only
the Nifty leg is a deliberate simulation-only exception, per explicit choice
over the NIFTYBEES.NS ETF alternative.

Each Exchange knows its own trading hours (in its own local timezone, so DST
is handled correctly via zoneinfo - the same style as market_data.py's
NSE-only is_market_open()/minutes_to_close()), its currency (for the FX
conversion in app/data/fx.py, always a no-op at INR here), and its default
watchlist."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Exchange:
    code: str
    label: str
    tz: ZoneInfo
    open_time: dt.time
    close_time: dt.time
    currency: str
    suffix: str  # yfinance ticker suffix for this market, "" for US (bare tickers)
    benchmark_symbol: str
    watchlist: tuple[str, ...] = field(default_factory=tuple)
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)  # Mon-Fri

    def is_open(self, now: dt.datetime | None = None) -> bool:
        local = (now or dt.datetime.now(self.tz)).astimezone(self.tz)
        if local.weekday() not in self.weekdays:
            return False
        open_dt = local.replace(hour=self.open_time.hour, minute=self.open_time.minute, second=0, microsecond=0)
        close_dt = local.replace(hour=self.close_time.hour, minute=self.close_time.minute, second=0, microsecond=0)
        return open_dt <= local <= close_dt

    def minutes_to_close(self, now: dt.datetime | None = None) -> float:
        local = (now or dt.datetime.now(self.tz)).astimezone(self.tz)
        close_dt = local.replace(hour=self.close_time.hour, minute=self.close_time.minute, second=0, microsecond=0)
        return max((close_dt - local).total_seconds() / 60.0, 0.0)


NSE = Exchange(
    code="NSE", label="India (NSE)", tz=ZoneInfo("Asia/Kolkata"),
    open_time=dt.time(9, 15), close_time=dt.time(15, 30), currency="INR", suffix=".NS",
    benchmark_symbol="^NSEI",
    # Scoped down (2026-07-21) to exactly the 3 instruments the app is meant to
    # trade: the Nifty 50 index directly (^NSEI - see module docstring for why
    # this is a synthetic paper-only position rather than a real futures
    # contract) and MCX gold/silver via their NSE-listed ETF proxies.
    watchlist=("^NSEI", "GOLDBEES.NS", "SILVERBEES.NS"),
)

# Single-exchange registry - kept as a tuple/dict-keyed lookup (rather than
# collapsing straight to the NSE constant) so callers that iterate
# ALL_EXCHANGES or look up by code don't need special-casing.
ALL_EXCHANGES: tuple[Exchange, ...] = (NSE,)
_BY_CODE = {ex.code: ex for ex in ALL_EXCHANGES}

_SUFFIX_TO_EXCHANGE = {ex.suffix: ex for ex in ALL_EXCHANGES if ex.suffix}


def get_exchange(code: str) -> Exchange:
    return _BY_CODE[code]


def get_open_exchange(now: dt.datetime | None = None) -> Exchange | None:
    for exchange in ALL_EXCHANGES:
        if exchange.is_open(now):
            return exchange
    return None


def infer_exchange_from_symbol(symbol: str) -> Exchange:
    """For ad-hoc symbols typed into Stock Search rather than picked from the
    watchlist - a .NS suffix match confirms NSE; anything else still resolves
    to NSE since it's the only exchange this build supports."""
    for suffix, exchange in _SUFFIX_TO_EXCHANGE.items():
        if symbol.upper().endswith(suffix):
            return exchange
    return NSE
