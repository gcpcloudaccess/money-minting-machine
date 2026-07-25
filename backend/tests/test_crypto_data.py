"""Unit tests for the CoinDCX crypto data client (app/data/crypto_data.py) -
httpx.get is mocked so these run offline/deterministically; also proves
graceful degradation (returns None, never raises) when the network call
fails, matching app/data/options_data.py's convention."""

from unittest.mock import MagicMock, patch

from app.data import crypto_data


def _fake_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_get_ticker_finds_matching_market():
    payload = [
        {"market": "ETHINR", "last_price": "200000"},
        {"market": "BTCINR", "last_price": "5000000", "high": "5100000", "low": "4900000"},
    ]
    with patch("app.data.crypto_data.httpx.get", return_value=_fake_response(payload)):
        ticker = crypto_data.get_ticker("BTCINR")
    assert ticker is not None
    assert ticker["last_price"] == "5000000"


def test_get_ticker_returns_none_for_unlisted_market():
    payload = [{"market": "ETHINR", "last_price": "200000"}]
    with patch("app.data.crypto_data.httpx.get", return_value=_fake_response(payload)):
        assert crypto_data.get_ticker("DOGEINR") is None


def test_get_ticker_degrades_gracefully_on_network_failure():
    with patch("app.data.crypto_data.httpx.get", side_effect=ConnectionError("no network")):
        assert crypto_data.get_ticker("BTCINR") is None


def test_get_latest_price_parses_float():
    payload = [{"market": "BTCINR", "last_price": "5123456.78"}]
    with patch("app.data.crypto_data.httpx.get", return_value=_fake_response(payload)):
        price = crypto_data.get_latest_price("BTCINR")
    assert price == 5123456.78


def test_resolve_pair_caches_result():
    crypto_data._PAIR_CACHE.clear()
    market_details_payload = [
        {"symbol": "BTCINR", "pair": "I-BTC_INR"},
        {"symbol": "ETHINR", "pair": "I-ETH_INR"},
    ]
    with patch("app.data.crypto_data.httpx.get", return_value=_fake_response(market_details_payload)) as mock_get:
        pair1 = crypto_data._resolve_pair("BTCINR")
        pair2 = crypto_data._resolve_pair("BTCINR")  # should hit cache, not call httpx again
    assert pair1 == "I-BTC_INR"
    assert pair2 == "I-BTC_INR"
    assert mock_get.call_count == 1


def test_get_candles_shapes_dataframe_like_yfinance():
    crypto_data._PAIR_CACHE["BTCINR"] = "I-BTC_INR"  # skip market_details round-trip
    candles_payload = [
        {"open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 12.5, "time": 1_700_000_000_000},
        {"open": 105.0, "high": 108.0, "low": 100.0, "close": 106.0, "volume": 8.2, "time": 1_700_000_300_000},
    ]
    with patch("app.data.crypto_data.httpx.get", return_value=_fake_response(candles_payload)):
        df = crypto_data.get_candles("BTCINR", interval="5m", limit=200)
    assert df is not None
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(df) == 2
    assert df.index.is_monotonic_increasing
    assert float(df["Close"].iloc[0]) == 105.0


def test_get_candles_returns_none_when_pair_unresolvable():
    crypto_data._PAIR_CACHE.clear()
    with patch("app.data.crypto_data.httpx.get", return_value=_fake_response([])):
        assert crypto_data.get_candles("UNLISTEDCOIN") is None
