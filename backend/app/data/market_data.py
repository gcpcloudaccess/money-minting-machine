"""Market data access layer.

Wraps yfinance for NSE intraday data. Supports two modes (see Settings.data_mode):

- "live": pulls current/delayed quotes and bars directly from yfinance. Only
  meaningful while NSE is open (09:15-15:30 IST, Mon-Fri).
- "replay": downloads a window of recent historical intraday bars once, caches
  them to disk, and replays them bar-by-bar as the session ticks forward. Lets
  the whole pipeline run and be demoed regardless of the wall-clock time.

COMEX fallback (live mode only): GOLDBEES.NS/SILVERBEES.NS have no fresh
intraday NSE bars once NSE closes for the day, which would otherwise leave
their technical/algo reads frozen on a stale last-close price until NSE
reopens. get_recent_bars()/get_daily_bars() fall back to the COMEX gold/silver
futures (GC=F/SI=F) while NSE is shut, purely so Stock Search and the
Dashboard keep producing a live, moving analysis - see _COMEX_PROXY below.
get_latest_price() deliberately does NOT use this fallback: it's the tradable
reference price for position sizing/P&L, and no trade can execute outside NSE
hours anyway (see session_runner.py), so it always stays tied to the symbol's
own real NSE price.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from app.config import get_settings

IST = ZoneInfo("Asia/Kolkata")
CACHE_DIR = Path(__file__).resolve().parents[3] / "data_cache"
CACHE_DIR.mkdir(exist_ok=True)

REPLAY_WARMUP_BARS = 60  # ensure enough history for indicators before the first "current" bar

# NSE-listed gold/silver ETF -> COMEX futures symbol used purely as a live
# analysis-feed proxy while NSE is closed. Nifty (NIFTYBEES.NS) has no clean
# always-on global proxy at this scope, so it isn't included - its analysis
# simply pauses with the rest of the NSE universe outside market hours.
_COMEX_PROXY: dict[str, str] = {"GOLDBEES.NS": "GC=F", "SILVERBEES.NS": "SI=F"}


def is_market_open(now: dt.datetime | None = None) -> bool:
    now = (now or dt.datetime.now(IST)).astimezone(IST)
    if now.weekday() >= 5:
        return False
    open_t = now.replace(hour=9, minute=15, second=0, microsecond=0)
    close_t = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_t <= now <= close_t


def minutes_to_close(now: dt.datetime | None = None) -> float:
    now = (now or dt.datetime.now(IST)).astimezone(IST)
    close_t = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return max((close_t - now).total_seconds() / 60.0, 0.0)


class MarketDataProvider:
    """Stateful provider: holds a replay cursor per symbol when in replay mode."""

    def __init__(self, mode: str | None = None) -> None:
        self.mode = mode or get_settings().data_mode
        self._replay_cache: dict[str, pd.DataFrame] = {}
        self._replay_index: dict[str, int] = {}
        self._daily_cache: dict[str, pd.DataFrame] = {}

    # -- internal -----------------------------------------------------
    def _effective_symbol(self, symbol: str, allow_proxy: bool) -> tuple[str, bool]:
        """Returns (symbol_to_fetch, used_proxy). Only ever substitutes in
        live mode, only for the mapped gold/silver symbols, and only while
        NSE itself is closed - during NSE hours (or in replay mode, which is
        clock-independent by design) the real symbol is always used."""
        if allow_proxy and self.mode == "live" and symbol in _COMEX_PROXY and not is_market_open():
            return _COMEX_PROXY[symbol], True
        return symbol, False

    def _cache_path(self, symbol: str) -> Path:
        safe = symbol.replace("/", "_")
        return CACHE_DIR / f"{safe}_5m.csv"

    def _load_replay_data(self, symbol: str) -> pd.DataFrame:
        if symbol in self._replay_cache:
            return self._replay_cache[symbol]

        path = self._cache_path(symbol)
        if path.exists():
            df = pd.read_csv(path, index_col=0, parse_dates=True)
        else:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="5d", interval="5m")
            if df.empty:
                # fall back to daily bars if intraday history unavailable (e.g. illiquid symbol)
                df = ticker.history(period="1mo", interval="1d")
            df.to_csv(path)
        self._replay_cache[symbol] = df
        self._replay_index.setdefault(symbol, min(REPLAY_WARMUP_BARS, max(len(df) - 1, 1)))
        return df

    # -- public API -----------------------------------------------------
    def get_recent_bars(self, symbol: str, lookback_bars: int = 200, allow_proxy: bool = True) -> pd.DataFrame:
        if self.mode == "replay":
            df = self._load_replay_data(symbol)
            idx = self._replay_index.get(symbol, REPLAY_WARMUP_BARS)
            window = df.iloc[max(0, idx - lookback_bars) : idx]
            return window
        fetch_symbol, used_proxy = self._effective_symbol(symbol, allow_proxy)
        ticker = yf.Ticker(fetch_symbol)
        df = ticker.history(period="5d", interval="5m")
        result = df.tail(lookback_bars)
        result.attrs["source_symbol"] = fetch_symbol
        result.attrs["used_comex_proxy"] = used_proxy
        return result

    def get_daily_bars(self, symbol: str, period: str = "6mo", allow_proxy: bool = True) -> pd.DataFrame:
        """Daily OHLCV history - independent of live/replay mode and the intraday
        replay cursor. Used by risk models that are calibrated for daily bars
        (e.g. annualization assuming ~252 trading days/year); feeding those
        models 5-minute intraday bars would silently understate volatility.

        Cached by the symbol actually fetched (not always the requested
        symbol) so a COMEX-proxied frame never gets served stale once NSE
        reopens and the real symbol becomes fetchable again."""
        fetch_symbol, used_proxy = self._effective_symbol(symbol, allow_proxy)
        if fetch_symbol in self._daily_cache:
            return self._daily_cache[fetch_symbol]
        ticker = yf.Ticker(fetch_symbol)
        df = ticker.history(period=period, interval="1d")
        df.attrs["source_symbol"] = fetch_symbol
        df.attrs["used_comex_proxy"] = used_proxy
        self._daily_cache[fetch_symbol] = df
        return df

    def get_latest_price(self, symbol: str) -> float:
        # allow_proxy=False: this is the tradable reference price (position
        # sizing / P&L), always the symbol's own real NSE price - see module
        # docstring for why the COMEX proxy never applies here.
        bars = self.get_recent_bars(symbol, lookback_bars=1, allow_proxy=False)
        if bars.empty:
            raise ValueError(f"No price data available for {symbol}")
        return float(bars["Close"].iloc[-1])

    def advance(self, symbol: str, steps: int = 1) -> None:
        """Move the replay cursor forward. No-op in live mode."""
        if self.mode != "replay":
            return
        df = self._load_replay_data(symbol)
        current = self._replay_index.get(symbol, REPLAY_WARMUP_BARS)
        self._replay_index[symbol] = min(current + steps, len(df) - 1)

    def advance_all(self, symbols: list[str], steps: int = 1) -> None:
        for s in symbols:
            self.advance(s, steps)

    def is_session_exhausted(self, symbol: str) -> bool:
        if self.mode != "replay":
            return False
        df = self._load_replay_data(symbol)
        return self._replay_index.get(symbol, 0) >= len(df) - 1
