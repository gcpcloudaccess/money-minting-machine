"""Unit tests for the CRYPTO_INDIA cost profile (app/trading/costs.py) -
CoinDCX trading fee + GST on the fee + Section 194S TDS on sell-side turnover
only. No network/DB required."""

from app.trading.costs import COST_PROFILES, compute_costs


def test_crypto_profile_registered():
    assert "CRYPTO_INDIA" in COST_PROFILES


def test_buy_has_no_tds_sell_does():
    buy = compute_costs("BUY", 0.01, 5_000_000.0, exchange="CRYPTO_INDIA")
    sell = compute_costs("SELL", 0.01, 5_000_000.0, exchange="CRYPTO_INDIA")
    assert buy["tds"] == 0.0
    assert sell["tds"] > 0.0
    # 1% TDS on turnover (0.01 * 5,000,000 = 50,000) = 500
    assert sell["tds"] == 500.0


def test_trading_fee_and_gst_on_fee_not_turnover():
    turnover = 100_000.0
    result = compute_costs("BUY", 1, turnover, exchange="CRYPTO_INDIA")
    expected_fee = turnover * 0.002
    expected_gst = expected_fee * 0.18
    assert result["trading_fee"] == round(expected_fee, 2)
    assert result["gst"] == round(expected_gst, 2)
    # GST must be computed on the fee, not turnover - would be ~100x too large otherwise.
    assert result["gst"] < result["trading_fee"]


def test_total_sums_components():
    result = compute_costs("SELL", 0.005, 5_000_000.0, exchange="CRYPTO_INDIA")
    assert result["total"] == round(result["trading_fee"] + result["gst"] + result["tds"], 2)


def test_crypto_costs_are_nonnegative():
    for action in ("BUY", "SELL"):
        result = compute_costs(action, 0.02, 5_000_000.0, exchange="CRYPTO_INDIA")
        assert result["total"] >= 0


def test_unknown_exchange_still_falls_back_to_nse():
    result = compute_costs("BUY", 10, 1000.0, exchange="LSE")
    assert "brokerage" in result  # NSE-shaped fallback, not crypto-shaped
