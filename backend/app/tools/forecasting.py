"""Lightweight time-series forecasting engine: linear-trend projection with an
uncertainty band derived from fit residuals. Deliberately simple/fast (no heavy
DL dependency) so it can run every tick within a hackathon time budget."""

from __future__ import annotations

import numpy as np
import pandas as pd


def forecast_next(bars: pd.DataFrame, horizon_bars: int = 3) -> dict:
    if bars is None or len(bars) < 10:
        return {"action": "WAIT", "confidence": 0.2, "evidence": ["Not enough history to forecast."], "metrics": {}}

    close = bars["Close"].to_numpy(dtype=float)
    x = np.arange(len(close))

    coeffs = np.polyfit(x, close, deg=1)
    slope, intercept = coeffs[0], coeffs[1]
    fitted = slope * x + intercept
    residuals = close - fitted
    resid_std = float(np.std(residuals)) or 1e-6

    last_price = close[-1]
    projected = slope * (x[-1] + horizon_bars) + intercept
    pct_move = (projected - last_price) / last_price if last_price else 0.0

    ss_res = float(np.sum(residuals**2))
    ss_tot = float(np.sum((close - close.mean()) ** 2)) or 1e-9
    r_squared = max(0.0, 1 - ss_res / ss_tot)

    if pct_move > 0.002:
        action = "BUY"
    elif pct_move < -0.002:
        action = "SELL"
    else:
        action = "HOLD"

    confidence = round(min(0.9, max(0.15, r_squared * min(abs(pct_move) * 40, 1.0))), 3)

    return {
        "action": action,
        "confidence": confidence,
        "evidence": [
            f"Linear trend projects {pct_move*100:+.2f}% move over next {horizon_bars} bars "
            f"(fit R²={r_squared:.2f})."
        ],
        "metrics": {
            "slope_per_bar": round(float(slope), 4),
            "r_squared": round(r_squared, 3),
            "projected_price": round(float(projected), 2),
            "residual_std": round(resid_std, 4),
        },
    }
