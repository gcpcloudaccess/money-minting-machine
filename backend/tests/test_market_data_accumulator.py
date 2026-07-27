"""Tests for the in-memory live-tick bar accumulator in app/data/market_data.py.

This is a resilience layer: a source's own historical-candles endpoint
(CoinDCX especially - see app/data/crypto_data.py's bot-check note) can
return too little history for the Technical/Risk/Algo Signal agents to work
with even when the simpler live-price/ticker endpoint is perfectly reachable.
record_live_tick() builds this app's own growing price series from real
observations every tick (see session_runner.py); _with_accumulated_fallback()
only ever supplements a thin result, never replaces a source that's already
returning enough bars on its own. In-memory only, by design - resets on every
container restart rather than being persisted (see market_data.py docstring
in MarketDataProvider.__init__)."""

from __future__ import annotations

import pandas as pd

from app.data import market_data


def _provider() -> market_data.MarketDataProvider:
    return market_data.MarketDataProvider(mode="live")


def test_record_live_tick_appends_a_point(monkeypatch):
    p = _provider()
    monkeypatch.setattr(p, "get_latest_price", lambda symbol: 123.45)
    p.record_live_tick("BTCINR")
    bars = p._accumulated_bars("BTCINR")
    assert len(bars) == 1
    assert bars["Close"].iloc[0] == 123.45
    assert bars["Open"].iloc[0] == bars["High"].iloc[0] == bars["Low"].iloc[0] == 123.45


def test_record_live_tick_accumulates_across_calls(monkeypatch):
    p = _provider()
    prices = iter([100.0, 101.0, 99.0])
    monkeypatch.setattr(p, "get_latest_price", lambda symbol: next(prices))
    for _ in range(3):
        p.record_live_tick("BTCINR")
    bars = p._accumulated_bars("BTCINR")
    assert len(bars) == 3
    assert list(bars["Close"]) == [100.0, 101.0, 99.0]
    assert bars.index.is_monotonic_increasing


def test_record_live_tick_degrades_gracefully_on_price_failure(monkeypatch):
    p = _provider()

    def _raise(symbol):
        raise ValueError("no price data")

    monkeypatch.setattr(p, "get_latest_price", _raise)
    p.record_live_tick("BTCINR")  # must not raise
    assert p._accumulated_bars("BTCINR").empty


def test_accumulator_is_capped_at_max_points(monkeypatch):
    p = _provider()
    monkeypatch.setattr(market_data, "_MAX_ACCUMULATED_TICKS", 5)
    monkeypatch.setattr(p, "get_latest_price", lambda symbol: 100.0)
    for _ in range(10):
        p.record_live_tick("BTCINR")
    bucket = p._live_ticks["BTCINR"]
    assert bucket.maxlen == 5
    assert len(bucket) == 5


def test_with_accumulated_fallback_noop_when_source_already_has_enough_bars():
    p = _provider()
    rich = pd.DataFrame({
        "Open": [1.0] * 30, "High": [1.0] * 30, "Low": [1.0] * 30, "Close": [1.0] * 30, "Volume": [0.0] * 30,
    })
    rich.attrs["source_symbol"] = "BTCINR"
    rich.attrs["used_comex_proxy"] = False
    out = p._with_accumulated_fallback("BTCINR", rich, lookback_bars=200)
    assert len(out) == 30  # untouched - already >= _MIN_USABLE_BARS
    assert out.attrs["source_symbol"] == "BTCINR"


def test_with_accumulated_fallback_supplements_thin_source(monkeypatch):
    p = _provider()
    prices = iter(range(25))
    monkeypatch.setattr(p, "get_latest_price", lambda symbol: float(next(prices)))
    for _ in range(25):
        p.record_live_tick("BTCINR")

    thin = pd.DataFrame(
        {"Open": [5.0], "High": [5.0], "Low": [5.0], "Close": [5.0], "Volume": [0.0]},
        index=pd.DatetimeIndex([pd.Timestamp.now(tz="UTC")]),
    )
    thin.attrs["source_symbol"] = "BTCINR"
    thin.attrs["used_comex_proxy"] = False
    out = p._with_accumulated_fallback("BTCINR", thin, lookback_bars=200)
    assert len(out) > 1  # supplemented, not left at the source's thin 1-row frame
    assert out.attrs["source_symbol"] == "BTCINR"  # transparency fields preserved, not overwritten


def test_with_accumulated_fallback_handles_non_datetime_index_defensively():
    """A thin result with a plain RangeIndex (not the DatetimeIndex every real
    source in this module actually returns) must not crash the fallback -
    see market_data.py's defensive index coercion."""
    p = _provider()
    p._live_ticks["BTCINR"] = market_data.collections.deque(
        [(pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=1), 4.0)], maxlen=market_data._MAX_ACCUMULATED_TICKS
    )
    thin = pd.DataFrame({"Open": [5.0], "High": [5.0], "Low": [5.0], "Close": [5.0], "Volume": [0.0]})  # RangeIndex
    out = p._with_accumulated_fallback("BTCINR", thin, lookback_bars=200)
    assert len(out) == 2


def test_with_accumulated_fallback_returns_source_unchanged_when_nothing_accumulated():
    p = _provider()
    thin = pd.DataFrame({"Open": [5.0], "High": [5.0], "Low": [5.0], "Close": [5.0], "Volume": [0.0]})
    thin.attrs["source_symbol"] = "BTCINR"
    out = p._with_accumulated_fallback("BTCINR", thin, lookback_bars=200)
    assert len(out) == 1  # no accumulated history yet - nothing to add


def test_get_recent_bars_records_nothing_by_itself(monkeypatch):
    """record_live_tick is only ever called by session_runner.py's tick loop,
    never implicitly by get_recent_bars - a Stock Search preview (execute=False)
    shouldn't silently start building history for a symbol nobody is
    scheduled to keep polling."""
    p = _provider()
    monkeypatch.setattr(market_data.yf, "Ticker", lambda symbol: _EmptyTicker())
    p.get_recent_bars("NIFTYBEES.NS")
    assert p._live_ticks == {}


class _EmptyTicker:
    def history(self, period: str, interval: str) -> pd.DataFrame:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
