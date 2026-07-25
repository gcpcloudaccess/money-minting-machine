"""Unit tests for historical volatility / IV-HV spread / regime labeling -
pure Python, no network/LLM required."""

import numpy as np
import pandas as pd

from app.tools import volatility_regime


def _daily_bars(n=40, start=1000.0, seed=1, vol=0.01) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, vol, n)
    closes = start * np.cumprod(1 + returns)
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes, "Volume": 1_000_000}, index=idx)


def test_historical_volatility_needs_minimum_bars():
    assert volatility_regime.historical_volatility(_daily_bars(n=5), window=20) is None


def test_historical_volatility_is_positive_and_annualized():
    hv = volatility_regime.historical_volatility(_daily_bars(n=40, vol=0.02), window=20)
    assert hv is not None
    assert hv > 0
    # Annualized (~sqrt(252)) should be meaningfully larger than the raw daily vol input (2%).
    assert hv > 10


def test_regime_label_buckets():
    assert volatility_regime.regime_label(None) == "unknown"
    assert volatility_regime.regime_label(10.0) == "rich"
    assert volatility_regime.regime_label(-10.0) == "cheap"
    assert volatility_regime.regime_label(2.0) == "fair"


def test_iv_hv_spread_requires_both_values():
    assert volatility_regime.iv_hv_spread(None, 20.0) is None
    assert volatility_regime.iv_hv_spread(25.0, 20.0) == 5.0


def test_analyze_degrades_gracefully_without_data():
    result = volatility_regime.analyze(None, None)
    assert result["action"] == "HOLD"
    assert result["metrics"]["regime"] == "unknown"
