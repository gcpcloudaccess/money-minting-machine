"""Tests for the COMEX gold/silver analysis-feed fallback in
app/data/market_data.py - no network (yf.Ticker is monkeypatched), no LLM key
required.

The fallback exists so GOLDBEES.NS/SILVERBEES.NS keep producing a live,
moving technical/algo read even while NSE is shut (which would otherwise
freeze their bars on a stale last close). It must never affect
get_latest_price() (the tradable reference price), never apply in replay
mode (already clock-independent), and never apply to symbols with no COMEX
mapping (e.g. NIFTYBEES.NS)."""

from __future__ import annotations

import pandas as pd
import pytest

from app.data import market_data


class _FakeTicker:
    """Records which symbol yfinance was asked for and returns a small,
    valid-looking OHLCV frame regardless of symbol."""

    calls: list[str] = []

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        _FakeTicker.calls.append(symbol)

    def history(self, period: str, interval: str) -> pd.DataFrame:
        return pd.DataFrame({
            "Open": [100.0, 101.0], "High": [102.0, 103.0], "Low": [99.0, 100.0],
            "Close": [101.0, 102.0], "Volume": [1000, 1200],
        })


@pytest.fixture(autouse=True)
def _patch_ticker(monkeypatch):
    _FakeTicker.calls = []
    monkeypatch.setattr(market_data.yf, "Ticker", _FakeTicker)
    yield


@pytest.fixture(autouse=True)
def _clear_daily_cache_between_tests():
    yield
    # each test builds its own MarketDataProvider instance, so no shared
    # cache state actually leaks - kept for symmetry/clarity if that changes.


def _provider(mode="live"):
    return market_data.MarketDataProvider(mode=mode)


def test_effective_symbol_uses_proxy_when_nse_closed(monkeypatch):
    monkeypatch.setattr(market_data, "is_market_open", lambda now=None: False)
    p = _provider("live")
    fetch_symbol, used_proxy = p._effective_symbol("GOLDBEES.NS", allow_proxy=True)
    assert fetch_symbol == "GC=F"
    assert used_proxy is True

    fetch_symbol, used_proxy = p._effective_symbol("SILVERBEES.NS", allow_proxy=True)
    assert fetch_symbol == "SI=F"
    assert used_proxy is True


def test_effective_symbol_uses_real_symbol_when_nse_open(monkeypatch):
    monkeypatch.setattr(market_data, "is_market_open", lambda now=None: True)
    p = _provider("live")
    fetch_symbol, used_proxy = p._effective_symbol("GOLDBEES.NS", allow_proxy=True)
    assert fetch_symbol == "GOLDBEES.NS"
    assert used_proxy is False


def test_effective_symbol_never_proxies_unmapped_symbols(monkeypatch):
    monkeypatch.setattr(market_data, "is_market_open", lambda now=None: False)
    p = _provider("live")
    fetch_symbol, used_proxy = p._effective_symbol("NIFTYBEES.NS", allow_proxy=True)
    assert fetch_symbol == "NIFTYBEES.NS"
    assert used_proxy is False


def test_effective_symbol_never_proxies_in_replay_mode(monkeypatch):
    monkeypatch.setattr(market_data, "is_market_open", lambda now=None: False)
    p = _provider("replay")
    fetch_symbol, used_proxy = p._effective_symbol("GOLDBEES.NS", allow_proxy=True)
    assert fetch_symbol == "GOLDBEES.NS"
    assert used_proxy is False


def test_effective_symbol_respects_allow_proxy_false(monkeypatch):
    monkeypatch.setattr(market_data, "is_market_open", lambda now=None: False)
    p = _provider("live")
    fetch_symbol, used_proxy = p._effective_symbol("GOLDBEES.NS", allow_proxy=False)
    assert fetch_symbol == "GOLDBEES.NS"
    assert used_proxy is False


def test_get_recent_bars_fetches_proxy_and_tags_attrs_when_nse_closed(monkeypatch):
    monkeypatch.setattr(market_data, "is_market_open", lambda now=None: False)
    p = _provider("live")
    bars = p.get_recent_bars("GOLDBEES.NS")
    assert "GC=F" in _FakeTicker.calls
    assert bars.attrs["source_symbol"] == "GC=F"
    assert bars.attrs["used_comex_proxy"] is True


def test_get_recent_bars_fetches_real_symbol_when_nse_open(monkeypatch):
    monkeypatch.setattr(market_data, "is_market_open", lambda now=None: True)
    p = _provider("live")
    bars = p.get_recent_bars("GOLDBEES.NS")
    assert _FakeTicker.calls == ["GOLDBEES.NS"]
    assert bars.attrs["source_symbol"] == "GOLDBEES.NS"
    assert bars.attrs["used_comex_proxy"] is False


def test_get_latest_price_never_uses_proxy_even_when_nse_closed(monkeypatch):
    """This is the tradable reference price (position sizing / P&L) - it must
    always reflect the symbol's own real NSE price, never the COMEX proxy,
    regardless of market hours."""
    monkeypatch.setattr(market_data, "is_market_open", lambda now=None: False)
    p = _provider("live")
    price = p.get_latest_price("GOLDBEES.NS")
    assert _FakeTicker.calls == ["GOLDBEES.NS"]  # never GC=F
    assert price == 102.0


def test_get_daily_bars_caches_by_fetched_symbol_not_requested_symbol(monkeypatch):
    """A COMEX-proxied daily frame must not be served once NSE reopens and the
    real symbol becomes fetchable again - caching by the symbol actually
    fetched (rather than the requested one) guarantees that."""
    p = _provider("live")

    monkeypatch.setattr(market_data, "is_market_open", lambda now=None: False)
    closed_bars = p.get_daily_bars("GOLDBEES.NS")
    assert closed_bars.attrs["source_symbol"] == "GC=F"
    assert "GC=F" in _FakeTicker.calls

    monkeypatch.setattr(market_data, "is_market_open", lambda now=None: True)
    open_bars = p.get_daily_bars("GOLDBEES.NS")
    assert open_bars.attrs["source_symbol"] == "GOLDBEES.NS"
    assert "GOLDBEES.NS" in _FakeTicker.calls


def test_nifty_has_no_comex_mapping():
    assert "NIFTYBEES.NS" not in market_data._COMEX_PROXY
