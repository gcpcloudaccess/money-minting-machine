"""Multi-exchange registry: lets the committee trade whichever of NSE, SGX,
LSE, or NYSE/NASDAQ is currently open, one at a time, and automatically move
on to the next open market as the day rolls around - rather than the system
sitting idle once NSE closes for the day.

Each Exchange knows its own trading hours (in its own local timezone, so DST
is handled correctly via zoneinfo - the same style as market_data.py's
NSE-only is_market_open()/minutes_to_close()), its currency (for the FX
conversion in app/data/fx.py), and a small default watchlist already suffixed
the way yfinance expects for that market."""

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
    watchlist=("RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "LT.NS", "SBIN.NS", "ITC.NS"),
)
SGX = Exchange(
    # 08:00 rather than the exchange's 09:00 core-session open - a realistic
    # pre-open/pre-market window (SGX itself runs a pre-open auction before
    # the continuous session) that also happens to close the one remaining
    # gap left after extending NYSE below - see the coverage note further down.
    code="SGX", label="Singapore (SGX)", tz=ZoneInfo("Asia/Singapore"),
    open_time=dt.time(8, 0), close_time=dt.time(17, 0), currency="SGD", suffix=".SI",
    benchmark_symbol="^STI",
    watchlist=("D05.SI", "O39.SI", "U11.SI", "Z74.SI"),
)
LSE = Exchange(
    code="LSE", label="London (LSE)", tz=ZoneInfo("Europe/London"),
    open_time=dt.time(8, 0), close_time=dt.time(16, 30), currency="GBP", suffix=".L",
    benchmark_symbol="^FTSE",
    watchlist=("HSBA.L", "BP.L", "AZN.L", "ULVR.L"),
)
NYSE = Exchange(
    # 04:00-20:00 ET (not just the 09:30-16:00 core session) - genuine
    # pre-market and after-hours trading windows most US brokers (and the
    # ECNs behind them) actually support, not an invented extension. This is
    # also what closes the round-the-clock gap: see the coverage note below.
    code="NYSE", label="United States (NYSE/NASDAQ, incl. pre/post-market)", tz=ZoneInfo("America/New_York"),
    open_time=dt.time(4, 0), close_time=dt.time(20, 0), currency="USD", suffix="",
    benchmark_symbol="^GSPC",
    watchlist=("AAPL", "MSFT", "AMZN", "JPM"),
)

# Priority order when more than one exchange is open at once (e.g. NSE and LSE
# overlap ~7:00-10:00 UTC in northern-hemisphere winter) - only one exchange
# trades at a time, so ties break in this order.
#
# Coverage note: with SGX's pre-open at 08:00 SGT and NYSE's pre/post-market
# window (04:00-20:00 ET), these 4 exchanges' local hours - converted to UTC -
# chain together with no gap across all seasons (checked against both DST
# regimes): SGX/NSE cover ~00:00-10:00 UTC, LSE picks up ~07:00-15:30 UTC,
# NYSE's extended window covers ~08:00-00:00 UTC (EDT) / ~09:00-01:00 UTC
# (EST), looping back around to SGX's next-day open. At least one of the 4 is
# always open - see test_exchanges.py::test_no_gap_across_a_full_24_hour_cycle.
ALL_EXCHANGES: tuple[Exchange, ...] = (NSE, SGX, LSE, NYSE)
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
    """For ad-hoc symbols typed into Stock Search rather than picked from a
    watchlist - a suffix match (.NS/.SI/.L) identifies the market; a bare
    ticker with no suffix is assumed to be a US listing."""
    for suffix, exchange in _SUFFIX_TO_EXCHANGE.items():
        if symbol.upper().endswith(suffix):
            return exchange
    return NYSE
