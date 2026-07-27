"""Indian crypto exchange data access layer - CoinDCX's public REST API
(no API key needed for market data; see https://docs.coindcx.com/).

CoinDCX, not a global exchange, per explicit user request: BTC should trade
against an Indian venue's own INR order book, the same "Indian exchange
only" stance the rest of this app already takes for equities (NSE) and
options (NSE's own chain). yfinance was deliberately NOT used here even
though it can serve some crypto tickers - that data isn't sourced from an
Indian exchange, so it wouldn't satisfy that requirement.

Three endpoints:
  - GET  https://api.coindcx.com/exchange/ticker              - live last price / 24h high-low-volume for every market
  - GET  https://api.coindcx.com/exchange/v1/market_details    - resolves a market symbol (e.g. "BTCINR") to the
                                                                  candles endpoint's `pair` identifier (e.g. "I-BTC_INR")
  - GET  https://public.coindcx.com/market_data/candles        - OHLCV candles for a resolved pair

Every function degrades to None on any failure (network error, symbol not
listed, CoinDCX rate limit/bot-check) - same convention as
app/data/options_data.py - callers must treat None as "no data this run",
never crash a trading tick over it.
"""

from __future__ import annotations

import datetime as dt
import logging
import time

import httpx
import pandas as pd

logger = logging.getLogger("crypto_data")

TICKER_URL = "https://api.coindcx.com/exchange/ticker"
MARKET_DETAILS_URL = "https://api.coindcx.com/exchange/v1/market_details"
CANDLES_URL = "https://public.coindcx.com/market_data/candles"

_TIMEOUT = 8.0
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 1.5

# A default httpx client sends "python-httpx/<version>" as its User-Agent, which
# some exchange APIs (CoinDCX included, per anecdotal reports) bot-check and
# silently drop rather than reject with a clear 4xx - indistinguishable from a
# real network failure from this module's own retry/None-on-failure logic
# without checking response status/logs directly. A realistic browser
# User-Agent costs nothing and removes that as a possible cause; kept even if
# it turns out not to be the actual reason a given request fails.
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def _get_with_retry(url: str, params: dict | None = None) -> httpx.Response | None:
    """Every CoinDCX call in this module is best-effort (see module
    docstring - returns None on any failure, never crashes a tick), but a
    single transient timeout/hiccup was previously indistinguishable from a
    genuinely dead endpoint - retrying a couple of times with a short backoff
    before giving up on this call is cheap insurance against exactly that,
    and each failed attempt is logged (not swallowed silently) so a stretch
    of "insufficient bar history" agent reasoning is actually diagnosable
    from the backend logs instead of a pure guess."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = httpx.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            last_exc = exc
            logger.warning("CoinDCX request failed (attempt %d/%d) for %s: %s", attempt, _MAX_ATTEMPTS, url, exc)
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF_SECONDS * attempt)
    logger.error("CoinDCX request exhausted retries for %s: %s", url, last_exc)
    return None


# market symbol (CoinDCX's own naming, e.g. "BTCINR") -> resolved candles
# `pair` string (e.g. "I-BTC_INR") - resolved once via market_details and
# cached for the process lifetime, since this mapping essentially never
# changes for an already-listed market.
_PAIR_CACHE: dict[str, str] = {}


def get_ticker(market: str) -> dict | None:
    """Live snapshot for one market symbol (e.g. "BTCINR"): last_price, high,
    low, volume, change_24_hour, bid, ask, timestamp - or None if unreachable
    or the market isn't listed."""
    resp = _get_with_retry(TICKER_URL)
    if resp is None:
        return None
    try:
        rows = resp.json()
    except Exception:
        return None

    for row in rows:
        if row.get("market") == market:
            return row
    return None


def _resolve_pair(market: str) -> str | None:
    if market in _PAIR_CACHE:
        return _PAIR_CACHE[market]
    resp = _get_with_retry(MARKET_DETAILS_URL)
    if resp is None:
        return None
    try:
        rows = resp.json()
    except Exception:
        return None

    for row in rows:
        if row.get("symbol") == market and row.get("pair"):
            _PAIR_CACHE[market] = row["pair"]
            return row["pair"]
    return None


def get_candles(
    market: str, interval: str = "5m", limit: int = 200,
    start_time_ms: int | None = None, end_time_ms: int | None = None,
) -> pd.DataFrame | None:
    """OHLCV candles for `market` (e.g. "BTCINR"), shaped exactly like
    market_data.py's yfinance-sourced DataFrames (Open/High/Low/Close/Volume
    columns, ascending DatetimeIndex) so every downstream analyst/tool that
    consumes `bars`/`daily_bars` works unmodified regardless of whether the
    symbol came from yfinance or CoinDCX. Returns None if the pair can't be
    resolved or the candles request fails.

    start_time_ms/end_time_ms let a caller page backward through history
    beyond CoinDCX's single-request cap (1000 candles) - see
    scripts/fetch_backtest_data.py, which uses this to assemble a longer
    CSV for backtesting than any one request could return."""
    pair = _resolve_pair(market)
    if pair is None:
        return None

    params = {"pair": pair, "interval": interval, "limit": limit}
    if start_time_ms is not None:
        params["startTime"] = start_time_ms
    if end_time_ms is not None:
        params["endTime"] = end_time_ms

    resp = _get_with_retry(CANDLES_URL, params=params)
    if resp is None:
        return None
    try:
        rows = resp.json()
    except Exception:
        return None

    if not rows:
        logger.warning("CoinDCX candles request for %s (%s) returned an empty list - pair=%s interval=%s", market, CANDLES_URL, pair, interval)
        return None

    try:
        df = pd.DataFrame(rows)
        df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
        df.index = pd.to_datetime(df["time"], unit="ms", utc=True)
        df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
        df = df.sort_index()
        return df
    except (KeyError, ValueError, TypeError):
        return None


def get_latest_price(market: str) -> float | None:
    ticker = get_ticker(market)
    if ticker is None or ticker.get("last_price") is None:
        return None
    try:
        return float(ticker["last_price"])
    except (TypeError, ValueError):
        return None


def is_crypto_symbol(symbol: str, crypto_watchlist: tuple[str, ...]) -> bool:
    return symbol in crypto_watchlist


def utcnow_ms() -> int:
    return int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
