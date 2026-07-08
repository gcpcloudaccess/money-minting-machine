"""Live FX rates for converting a foreign exchange's local-currency price
into INR-equivalent terms, so the portfolio ledger (cash, exposure, P&L,
"Overall Return") stays in a single currency exactly as it does today for
NSE-only trading - only the price entering the pipeline gets converted, once,
at the source (see supervisor.py).

Same graceful-degradation shape as llm/client.py and data/fundamentals.py:
a live yfinance quote when available, a small static fallback table (approximate,
clearly not real-time) when the fetch fails, so a network hiccup never stops
a paper trade from pricing."""

from __future__ import annotations

import logging
import time

import yfinance as yf

logger = logging.getLogger("fx")

CACHE_TTL_SECONDS = 15 * 60  # equity data already tolerates ~15min staleness; match it

# Approximate fallback rates (currency -> INR) - only used if the live fetch fails.
_FALLBACK_RATES = {"INR": 1.0, "USD": 86.0, "GBP": 109.0, "SGD": 64.0}

_cache: dict[str, tuple[float, float]] = {}  # currency -> (rate, fetched_at_epoch)


def get_fx_rate(currency: str) -> float:
    currency = currency.upper()
    if currency == "INR":
        return 1.0

    cached = _cache.get(currency)
    if cached and (time.time() - cached[1]) < CACHE_TTL_SECONDS:
        return cached[0]

    try:
        ticker = yf.Ticker(f"{currency}INR=X")
        bars = ticker.history(period="5d", interval="1d")
        if bars.empty:
            raise ValueError(f"No FX data for {currency}INR=X")
        rate = float(bars["Close"].iloc[-1])
    except Exception as exc:
        logger.warning("FX fetch failed for %s, using fallback rate: %s: %s", currency, type(exc).__name__, exc)
        rate = _FALLBACK_RATES.get(currency, 1.0)

    _cache[currency] = (rate, time.time())
    return rate
