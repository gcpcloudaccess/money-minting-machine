"""NSE options chain data access layer.

There is no options-chain data in yfinance for NSE symbols (equities or the
Nifty index) - unlike market_data.py/fundamentals.py, which both sit on top
of yfinance, this module talks to NSE's own public (undocumented) JSON API
directly via httpx, since that's the only free source of Indian options data
(strikes, OI, IV, LTP) that exists.

NSE's API requires a warm session: it rejects requests without cookies set by
first hitting a normal HTML page, and expects a browser-like User-Agent. This
matches the well-known pattern used by open-source NSE scraping tools
(e.g. nsepython) rather than inventing a new one.

Network reality: NSE's API is picky (rate limits, occasional bot-detection
challenges, no data outside/just-around market hours for older expiries) and
is unreachable from network-sandboxed environments entirely. Every function
here degrades to returning None on any failure rather than raising, mirroring
the fallback pattern already used for MACRO_* settings (app/agents/analysts/
macro.py) and the COMEX proxy (market_data.py) - the rest of the pipeline
(agents, consensus, dashboard) must keep working and clearly say "no options
data this run" rather than crash the whole positional scan over one symbol's
chain fetch failing.

IV rank/percentile needs IV *history*, which NSE's snapshot endpoint doesn't
provide - so every successful fetch appends that day's ATM IV to a small CSV
under data_cache/ (see market_data.py's CACHE_DIR), building up real history
over time the app is actually run, the same "accumulate as you go" approach
used nowhere else yet in this codebase but consistent with its cache_dir
convention.
"""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.data.market_data import CACHE_DIR

NSE_HOME = "https://www.nseindia.com"
NSE_INDEX_CHAIN_URL = "https://www.nseindia.com/api/option-chain-indices"
NSE_EQUITY_CHAIN_URL = "https://www.nseindia.com/api/option-chain-equities"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/option-chain",
}

# Index symbols use a different NSE endpoint + a different ticker naming
# convention than equities. Extend as more indices are added to the
# positional universe.
_INDEX_SYMBOL_MAP = {"^NSEI": "NIFTY", "^NSEBANK": "BANKNIFTY"}

IV_HISTORY_MIN_DAYS = 20  # below this, iv_rank() reports "insufficient history" rather than a misleading number


@dataclass
class OptionLeg:
    strike: float
    expiry: str  # ISO date
    call_iv: float | None
    call_oi: float | None
    call_ltp: float | None
    call_bid: float | None
    call_ask: float | None
    put_iv: float | None
    put_oi: float | None
    put_ltp: float | None
    put_bid: float | None
    put_ask: float | None


@dataclass
class OptionChainSnapshot:
    symbol: str
    underlying_price: float
    expiries: list[str]
    legs: list[OptionLeg] = field(default_factory=list)
    fetched_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    def legs_for_expiry(self, expiry: str) -> list[OptionLeg]:
        return [leg for leg in self.legs if leg.expiry == expiry]

    def atm_strike(self, expiry: str | None = None) -> float | None:
        pool = self.legs_for_expiry(expiry) if expiry else self.legs
        if not pool:
            return None
        return min((leg.strike for leg in pool), key=lambda s: abs(s - self.underlying_price))

    def nearest_expiry(self) -> str | None:
        return self.expiries[0] if self.expiries else None


def _nse_symbol(symbol: str) -> tuple[str, bool]:
    """Returns (nse_symbol, is_index)."""
    if symbol in _INDEX_SYMBOL_MAP:
        return _INDEX_SYMBOL_MAP[symbol], True
    # Equities: strip the yfinance .NS suffix NSE's own API doesn't use.
    return symbol.split(".")[0].upper(), False


def _fetch_raw_chain(symbol: str, timeout: float = 8.0) -> dict | None:
    nse_symbol, is_index = _nse_symbol(symbol)
    url = NSE_INDEX_CHAIN_URL if is_index else NSE_EQUITY_CHAIN_URL
    try:
        with httpx.Client(headers=_HEADERS, timeout=timeout, follow_redirects=True) as client:
            client.get(NSE_HOME)  # warm up session cookies - NSE rejects a cold GET to /api/*
            resp = client.get(url, params={"symbol": nse_symbol})
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


def _parse_chain(symbol: str, raw: dict) -> OptionChainSnapshot | None:
    try:
        records = raw["records"]
        underlying_price = float(records["underlyingValue"])
        expiries = list(records["expiryDates"])
        legs: list[OptionLeg] = []
        for row in records["data"]:
            ce = row.get("CE") or {}
            pe = row.get("PE") or {}
            legs.append(
                OptionLeg(
                    strike=float(row["strikePrice"]),
                    expiry=str(row["expiryDate"]),
                    call_iv=ce.get("impliedVolatility"),
                    call_oi=ce.get("openInterest"),
                    call_ltp=ce.get("lastPrice"),
                    call_bid=ce.get("bidprice"),
                    call_ask=ce.get("askPrice"),
                    put_iv=pe.get("impliedVolatility"),
                    put_oi=pe.get("openInterest"),
                    put_ltp=pe.get("lastPrice"),
                    put_bid=pe.get("bidprice"),
                    put_ask=pe.get("askPrice"),
                )
            )
        return OptionChainSnapshot(symbol=symbol, underlying_price=underlying_price, expiries=expiries, legs=legs)
    except (KeyError, TypeError, ValueError):
        return None


def get_option_chain(symbol: str) -> OptionChainSnapshot | None:
    """Live NSE options chain for one symbol, or None if unavailable (network
    blocked, symbol has no listed options/isn't in F&O, NSE bot-check, etc.).
    Callers (options analytics tools, agents) must treat None as "no options
    data this run", not an error."""
    raw = _fetch_raw_chain(symbol)
    if raw is None:
        return None
    return _parse_chain(symbol, raw)


# ---------------------------------------------------------------- IV history
def _iv_history_path(symbol: str) -> Path:
    safe = symbol.replace("/", "_").replace("^", "")
    return CACHE_DIR / f"{safe}_atm_iv_history.csv"


def record_atm_iv(symbol: str, atm_iv: float, as_of: dt.date | None = None) -> None:
    """Appends today's ATM IV to this symbol's history file (idempotent per
    day - overwrites today's row if called more than once). Call this once
    per positional scan per symbol so iv_rank() has something to compare
    against after the app has been run for a few weeks."""
    as_of = as_of or dt.datetime.now(dt.timezone.utc).date()
    path = _iv_history_path(symbol)
    rows: dict[str, float] = {}
    if path.exists():
        with path.open(newline="") as f:
            for r in csv.reader(f):
                if len(r) == 2:
                    rows[r[0]] = float(r[1])
    rows[as_of.isoformat()] = atm_iv
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        for date_str in sorted(rows):
            writer.writerow([date_str, rows[date_str]])


def get_iv_history(symbol: str) -> list[float]:
    path = _iv_history_path(symbol)
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return [float(r[1]) for r in csv.reader(f) if len(r) == 2]
