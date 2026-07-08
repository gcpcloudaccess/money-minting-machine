"""Custom technical indicator engine (pandas/numpy math, not a talib wrapper).

Computes RSI, EMA/MACD, and volume-trend from raw OHLCV bars, then fuses them
into a single directional signal with a confidence score.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50.0)


def ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def volume_trend(volume: pd.Series, window: int = 10) -> float:
    if len(volume) < window + 1:
        return 0.0
    recent = volume.tail(window).mean()
    prior = volume.tail(window * 2).head(window).mean()
    if prior <= 0:
        return 0.0
    return float((recent - prior) / prior)


def analyze(bars: pd.DataFrame) -> dict:
    """Returns a structured technical signal from OHLCV bars.

    {action, confidence, evidence: [str], metrics: {...}}
    """
    if bars is None or len(bars) < 15:
        return {
            "action": "WAIT",
            "confidence": 0.2,
            "evidence": ["Insufficient bar history for a reliable technical read."],
            "metrics": {},
        }

    close = bars["Close"]
    rsi_series = rsi(close)
    macd_line, signal_line, hist = macd(close)
    vtrend = volume_trend(bars["Volume"]) if "Volume" in bars else 0.0

    last_rsi = float(rsi_series.iloc[-1])
    last_hist = float(hist.iloc[-1])
    prev_hist = float(hist.iloc[-2]) if len(hist) > 1 else last_hist
    macd_cross_up = prev_hist <= 0 < last_hist
    macd_cross_down = prev_hist >= 0 > last_hist

    votes: list[tuple[str, float, str]] = []  # (direction, strength, evidence)

    if last_rsi <= 30:
        votes.append(("BUY", (30 - last_rsi) / 30, f"RSI {last_rsi:.1f} indicates oversold conditions."))
    elif last_rsi >= 70:
        votes.append(("SELL", (last_rsi - 70) / 30, f"RSI {last_rsi:.1f} indicates overbought conditions."))
    else:
        votes.append(("HOLD", 0.3, f"RSI {last_rsi:.1f} is in neutral range."))

    last_close = float(close.iloc[-1])
    if macd_cross_up:
        votes.append(("BUY", 0.7, "MACD histogram just crossed positive (bullish momentum shift)."))
    elif macd_cross_down:
        votes.append(("SELL", 0.7, "MACD histogram just crossed negative (bearish momentum shift)."))
    elif last_hist > 0:
        votes.append(("BUY", min(abs(last_hist) / (last_close * 0.01 + 1e-9), 0.5), "MACD histogram positive, momentum favors upside."))
    else:
        votes.append(("SELL", min(abs(last_hist) / (last_close * 0.01 + 1e-9), 0.5), "MACD histogram negative, momentum favors downside."))

    if vtrend > 0.2:
        votes.append(("BUY", min(vtrend, 0.6), f"Volume trending up {vtrend*100:.0f}% vs prior window, confirming move."))
    elif vtrend < -0.2:
        votes.append(("HOLD", 0.3, f"Volume trending down {vtrend*100:.0f}%, weak conviction behind recent move."))

    buy_score = sum(s for d, s, _ in votes if d == "BUY")
    sell_score = sum(s for d, s, _ in votes if d == "SELL")
    hold_score = sum(s for d, s, _ in votes if d == "HOLD")

    scores = {"BUY": buy_score, "SELL": sell_score, "HOLD": hold_score}
    action = max(scores, key=scores.get)
    total = sum(scores.values()) or 1.0
    confidence = round(min(scores[action] / total, 1.0), 3)

    return {
        "action": action,
        "confidence": max(confidence, 0.15),
        "evidence": [e for _, _, e in votes],
        "metrics": {
            "rsi": round(last_rsi, 2),
            "macd_histogram": round(last_hist, 4),
            "volume_trend_pct": round(vtrend * 100, 2),
            "last_close": round(float(close.iloc[-1]), 2),
        },
    }
