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

# CoinDCX (Indian crypto exchange - see app/data/crypto_data.py; deliberately
# NOT a global venue, per the same "Indian exchange only" stance NSE already
# takes for equities/options). weekdays=all 7 days and a full 00:00-23:59:59
# open window makes is_open() always True: crypto markets don't close for
# weekends or Indian market holidays, which is the whole point of adding it -
# trades should execute around the clock, independent of NSE's session hours.
# suffix="" (no ticker suffix scheme) - infer_exchange_from_symbol() below
# resolves crypto symbols by watchlist membership instead.
#
# PI (Pi Network) was deliberately left out: as of this build it isn't listed
# on any major/vetted Indian exchange (CoinDCX, WazirX, Bitbns, ZebPay) - the
# only Indian venue offering PI/INR found was Flitpay, a much smaller,
# less-established platform not worth depending on for trading data yet.
CRYPTO_INDIA = Exchange(
    code="CRYPTO_INDIA", label="India Crypto (CoinDCX)", tz=ZoneInfo("Asia/Kolkata"),
    open_time=dt.time(0, 0), close_time=dt.time(23, 59, 59), currency="INR", suffix="",
    benchmark_symbol="BTCINR",  # self-referential until a second crypto symbol is added - see module docstring
    watchlist=("BTCINR",),
    weekdays=(0, 1, 2, 3, 4, 5, 6),  # Mon-Sun - crypto never closes
)

# Registry - kept as a tuple/dict-keyed lookup so callers that iterate
# ALL_EXCHANGES or look up by code don't need special-casing per exchange.
ALL_EXCHANGES: tuple[Exchange, ...] = (NSE, CRYPTO_INDIA)
_BY_CODE = {ex.code: ex for ex in ALL_EXCHANGES}

_SUFFIX_TO_EXCHANGE = {ex.suffix: ex for ex in ALL_EXCHANGES if ex.suffix}
_WATCHLIST_TO_EXCHANGE = {symbol: ex for ex in ALL_EXCHANGES for symbol in ex.watchlist}


def get_exchange(code: str) -> Exchange:
    return _BY_CODE[code]


def get_open_exchange(now: dt.datetime | None = None) -> Exchange | None:
    """Returns the first currently-open exchange in ALL_EXCHANGES order (NSE
    checked first). Since CRYPTO_INDIA is always open, this only ever returns
    None if ALL_EXCHANGES were somehow empty - kept as Exchange | None rather
    than a bare Exchange for API stability with existing callers, and because
    a single "the one open exchange" concept no longer really applies now
    that more than one exchange can be open at once (see
    app/orchestration/session_runner.py, which ticks every open exchange
    independently rather than relying on this function to pick just one)."""
    for exchange in ALL_EXCHANGES:
        if exchange.is_open(now):
            return exchange
    return None


def infer_exchange_from_symbol(symbol: str) -> Exchange:
    """For ad-hoc symbols typed into Stock Search rather than picked from a
    watchlist. Checks exact watchlist membership first (covers crypto symbols
    like "BTCINR", which have no ticker suffix scheme), then falls back to
    suffix matching (NSE's ".NS"), then defaults to NSE."""
    if symbol.upper() in _WATCHLIST_TO_EXCHANGE:
        return _WATCHLIST_TO_EXCHANGE[symbol.upper()]
    for suffix, exchange in _SUFFIX_TO_EXCHANGE.items():
        if symbol.upper().endswith(suffix):
            return exchange
    return NSE
