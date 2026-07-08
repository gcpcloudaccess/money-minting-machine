"""Custom risk scoring: realized volatility, parametric VaR, and max drawdown
computed directly from OHLCV bars."""

from __future__ import annotations

import numpy as np
import pandas as pd

Z_95 = 1.645


def compute_risk_metrics(bars: pd.DataFrame) -> dict:
    if bars is None or len(bars) < 10:
        return {"volatility": None, "var_95_pct": None, "max_drawdown_pct": None}

    close = bars["Close"]
    returns = close.pct_change().dropna()
    if returns.empty:
        return {"volatility": None, "var_95_pct": None, "max_drawdown_pct": None}

    vol = float(returns.std())
    var_95 = float(Z_95 * vol)

    running_max = close.cummax()
    drawdown = (close - running_max) / running_max
    max_dd = float(drawdown.min())

    return {
        "volatility": round(vol, 5),
        "var_95_pct": round(var_95 * 100, 3),
        "max_drawdown_pct": round(max_dd * 100, 3),
    }


def analyze(bars: pd.DataFrame) -> dict:
    metrics = compute_risk_metrics(bars)
    vol = metrics["volatility"]

    if vol is None:
        return {"action": "WAIT", "confidence": 0.2, "evidence": ["Insufficient data for risk assessment."], "metrics": metrics}

    if vol > 0.015:
        risk_level = "HIGH"
        action = "HOLD"
        base_conf = 0.7
    elif vol > 0.007:
        risk_level = "MEDIUM"
        action = "HOLD"
        base_conf = 0.4
    else:
        risk_level = "LOW"
        action = "BUY"
        base_conf = 0.3

    evidence = [
        f"Per-bar volatility {vol*100:.2f}% -> {risk_level} risk regime.",
        f"Parametric 95% VaR ≈ {metrics['var_95_pct']:.2f}% of position value per bar.",
        f"Max drawdown over lookback window: {metrics['max_drawdown_pct']:.2f}%.",
    ]

    return {
        "action": action,
        "confidence": round(base_conf, 3),
        "evidence": evidence,
        "metrics": {**metrics, "risk_level": risk_level},
    }
