"""Market data access layer.

Wraps yfinance for NSE intraday data, and app/data/crypto_data.py (CoinDCX)
for crypto - see CRYPTO_SYMBOLS below for how a symbol is routed to one
source or the other. Supports two modes (see Settings.data_mode):

- "live": pulls current/delayed quotes and bars directly from yfinance (NSE)
  or CoinDCX (crypto). NSE data is only meaningful while NSE is open
  (09:15-15:30 IST, Mon-Fri); crypto is always meaningful, live-fetched fresh
  on every call regardless of the day/time.
- "replay": downloads a window of recent historical bars once, caches them to
  disk, and replays them bar-by-bar as the session ticks forward. Lets the
  whole pipeline run and be demoed regardless of the wall-clock time. For
  crypto specifically, the replay cursor WRAPS AROUND instead of stopping at
  the end of the cached window (see advance()) - a 24/7 market shouldn't ever
  report itself as "session exhausted" the way a finite NSE trading day does.

COMEX fallback (live mode only, NSE symbols only): GOLDBEES.NS/SILVERBEES.NS
have no fresh intraday NSE bars once NSE closes for the day, which would
otherwise leave their technical/algo reads frozen on a stale last-close price
until NSE reopens. get_recent_bars()/get_daily_bars() fall back to the COMEX
gold/silver futures (GC=F/SI=F) while NSE is shut, purely so Stock Search and
the Dashboard keep producing a live, moving analysis - see _COMEX_PROXY
below. get_latest_price() deliberately does NOT use this fallback: it's the
tradable reference price for position sizing/P&L, and no trade can execute
outside NSE hours anyway (see session_runner.py), so it always stays tied to
the symbol's own real NSE price. None of this applies to crypto, which has no
market-hours concept to work around in the first place.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from app.config import get_settings
from app.data import crypto_data
from app.data.exchanges import CRYPTO_INDIA

IST = ZoneInfo("Asia/Kolkata")
CACHE_DIR = Path(__file__).resolve().parents[3] / "data_cache"
CACHE_DIR.mkdir(exist_ok=True)

REPLAY_WARMUP_BARS = 60  # ensure enough history for indicators before the first "current" bar

# NSE-listed gold/silver ETF -> COMEX futures symbol used purely as a live
# analysis-feed proxy while NSE is closed. Nifty (NIFTYBEES.NS) has no clean
# always-on global proxy at this scope, so it isn't included - its analysis
# simply pauses with the rest of the NSE universe outside market hours.
_COMEX_PROXY: dict[str, str] = {"GOLDBEES.NS": "GC=F", "SILVERBEES.NS": "SI=F"}

# Which symbols route to CoinDCX (app/data/crypto_data.py) instead of
# yfinance. Sourced from the exchange registry rather than duplicated here,
# so adding a second crypto symbol only ever means editing
# app/data/exchanges.py's CRYPTO_INDIA.watchlist.
CRYPTO_SYMBOLS = frozenset(CRYPTO_INDIA.watchlist)


def _is_crypto(symbol: str) -> bool:
    return symbol in CRYPTO_SYMBOLS


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


_TROY_OUNCE_GRAMS = 31.1034768  # exact, physical - not an ETF-specific assumption


def get_global_commodity_reference(symbol: str) -> dict | None:
    """Best-effort global reference price for gold/silver, always live
    regardless of market hours or data_mode - a real MCX futures feed isn't
    freely available (the official MCX API costs ~Rs 20L/year, no legitimate
    free alternative found), so this uses the same COMEX futures (GC=F/SI=F)
    this app already fetches as an NSE-closed fallback, converted from
    USD/troy oz to INR using live USDINR. Deliberately reported in India's
    standard retail gold/silver quoting units (Rs per 10g / Rs per kg) rather
    than "per GOLDBEES/SILVERBEES unit" - this app has no verified live
    source for the ETF's exact grams-of-gold-per-unit ratio, and a wrong
    assumption there would be more misleading than a differently-unit'd but
    honestly-labeled global comparison. Purely a display reference, never
    used in any trading/decision logic - same boundary as the existing COMEX
    fallback (see module docstring)."""
    proxy_symbol = _COMEX_PROXY.get(symbol)
    if proxy_symbol is None:
        return None
    try:
        futures_bars = yf.Ticker(proxy_symbol).history(period="5d", interval="1d")
        usdinr_bars = yf.Ticker("INR=X").history(period="5d", interval="1d")
        if futures_bars.empty or usdinr_bars.empty:
            return None
        troy_oz_price_usd = float(futures_bars["Close"].iloc[-1])
        usdinr = float(usdinr_bars["Close"].iloc[-1])
    except Exception:
        return None

    price_per_gram_inr = (troy_oz_price_usd * usdinr) / _TROY_OUNCE_GRAMS
    if symbol == "GOLDBEES.NS":
        return {"label": "Global gold (COMEX)", "value_inr": round(price_per_gram_inr * 10, 2), "unit": "per 10g"}
    return {"label": "Global silver (COMEX)", "value_inr": round(price_per_gram_inr * 1000, 2), "unit": "per kg"}


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
        elif _is_crypto(symbol):
            df = crypto_data.get_candles(symbol, interval="5m", limit=1000)
            if df is None or df.empty:
                df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
            else:
                df.to_csv(path)
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
        if _is_crypto(symbol):
            # Always fresh-fetched: no market-hours proxy logic applies to a
            # 24/7 market, and there's no reason to serve a cached/stale frame
            # in live mode when CoinDCX is reachable on every call.
            df = crypto_data.get_candles(symbol, interval="5m", limit=lookback_bars)
            if df is None:
                df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
            df.attrs["source_symbol"] = symbol
            df.attrs["used_comex_proxy"] = False
            return df
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
        if _is_crypto(symbol):
            if symbol in self._daily_cache:
                return self._daily_cache[symbol]
            df = crypto_data.get_candles(symbol, interval="1d", limit=200)
            if df is None:
                df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
            df.attrs["source_symbol"] = symbol
            df.attrs["used_comex_proxy"] = False
            self._daily_cache[symbol] = df
            return df
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
        if _is_crypto(symbol) and self.mode != "replay":
            # Ticker endpoint, not the last candle close - the more accurate
            # "right now" price for position sizing/P&L on a market that never
            # stops moving between candle closes.
            price = crypto_data.get_latest_price(symbol)
            if price is None:
                raise ValueError(f"No price data available for {symbol}")
            return price
        # allow_proxy=False: this is the tradable reference price (position
        # sizing / P&L), always the symbol's own real NSE price - see module
        # docstring for why the COMEX proxy never applies here. Crypto in
        # replay mode falls through to the replay cursor's own last close,
        # same as every other replayed symbol, for a self-consistent replay.
        bars = self.get_recent_bars(symbol, lookback_bars=1, allow_proxy=False)
        if bars.empty:
            raise ValueError(f"No price data available for {symbol}")
        return float(bars["Close"].iloc[-1])

    def advance(self, symbol: str, steps: int = 1) -> None:
        """Move the replay cursor forward. No-op in live mode. For crypto,
        wraps back to the start of the cached window instead of clamping at
        the end - a 24/7 market shouldn't ever report "session exhausted"
        (see is_session_exhausted()) just because the cached replay history
        ran out; it should keep looping so trades keep executing indefinitely,
        matching how the real market never stops."""
        if self.mode != "replay":
            return
        df = self._load_replay_data(symbol)
        current = self._replay_index.get(symbol, REPLAY_WARMUP_BARS)
        if _is_crypto(symbol):
            next_idx = current + steps
            if next_idx >= len(df) - 1:
                next_idx = min(REPLAY_WARMUP_BARS, max(len(df) - 1, 1))
            self._replay_index[symbol] = next_idx
        else:
            self._replay_index[symbol] = min(current + steps, len(df) - 1)

    def advance_all(self, symbols: list[str], steps: int = 1) -> None:
        for s in symbols:
            self.advance(s, steps)

    def is_session_exhausted(self, symbol: str) -> bool:
        if self.mode != "replay" or _is_crypto(symbol):
            return False
        df = self._load_replay_data(symbol)
        return self._replay_index.get(symbol, 0) >= len(df) - 1
