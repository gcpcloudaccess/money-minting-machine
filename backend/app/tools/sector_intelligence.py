"""Sector/peer-relative intelligence: ranks a symbol's recent momentum against
the rest of the watchlist (proxy universe) to flag relative strength/weakness."""

from __future__ import annotations

import pandas as pd


def _momentum(bars: pd.DataFrame, lookback: int = 20) -> float | None:
    if bars is None or len(bars) < 2:
        return None
    window = bars.tail(lookback)
    start = float(window["Close"].iloc[0])
    end = float(window["Close"].iloc[-1])
    if start == 0:
        return None
    return (end - start) / start


def analyze(symbol: str, target_bars: pd.DataFrame, peer_bars: dict[str, pd.DataFrame]) -> dict:
    target_mom = _momentum(target_bars)
    if target_mom is None:
        return {"action": "WAIT", "confidence": 0.2, "evidence": ["Not enough data for peer comparison."], "metrics": {}}

    peer_moms = {}
    for sym, bars in peer_bars.items():
        if sym == symbol:
            continue
        m = _momentum(bars)
        if m is not None:
            peer_moms[sym] = m

    if not peer_moms:
        return {
            "action": "HOLD",
            "confidence": 0.25,
            "evidence": [f"Momentum {target_mom*100:+.2f}%, no peer universe available for comparison."],
            "metrics": {"momentum_pct": round(target_mom * 100, 2)},
        }

    avg_peer = sum(peer_moms.values()) / len(peer_moms)
    rank = sum(1 for m in peer_moms.values() if target_mom > m)
    percentile = rank / len(peer_moms)
    relative = target_mom - avg_peer

    if percentile >= 0.7:
        action = "BUY"
    elif percentile <= 0.3:
        action = "SELL"
    else:
        action = "HOLD"

    confidence = round(max(0.2, min(0.85, abs(percentile - 0.5) * 2 * 0.7 + min(abs(relative) * 10, 0.3))), 3)

    return {
        "action": action,
        "confidence": confidence,
        "evidence": [
            f"{symbol} momentum {target_mom*100:+.2f}% vs watchlist average {avg_peer*100:+.2f}% "
            f"(percentile {percentile*100:.0f}% among {len(peer_moms)} peers)."
        ],
        "metrics": {
            "momentum_pct": round(target_mom * 100, 2),
            "peer_avg_momentum_pct": round(avg_peer * 100, 2),
            "percentile": round(percentile, 2),
        },
    }
