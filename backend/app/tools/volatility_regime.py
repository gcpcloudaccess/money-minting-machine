"""Volatility regime: historical (realized) vol vs implied vol, and vol term
structure across expiries - what tells the Strategy Architect whether to buy
premium (long options) or sell it (spreads), independent of the directional
call. A correct BUY direction with IV priced richer than realized vol is
still a bad long-option trade (the IV crush after the move offsets the
directional gain); a correct direction with IV priced cheap is a good one.
"""

from __future__ import annotations

import math

import pandas as pd

from app.data.options_data import OptionChainSnapshot


def historical_volatility(daily_bars: pd.DataFrame | None, window: int = 20) -> float | None:
    """Annualized close-to-close realized volatility (%) over the trailing
    `window` daily bars - the standard sqrt(252) annualization, matching the
    convention already used by the vendored risk_agent (see
    app/agents/analysts/risk.py's daily-bars-only note)."""
    if daily_bars is None or len(daily_bars) < window + 1:
        return None
    closes = daily_bars["Close"].tail(window + 1)
    log_returns = [math.log(closes.iloc[i] / closes.iloc[i - 1]) for i in range(1, len(closes)) if closes.iloc[i - 1] > 0]
    if len(log_returns) < 2:
        return None
    mean = sum(log_returns) / len(log_returns)
    variance = sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1)
    daily_vol = math.sqrt(variance)
    return round(daily_vol * math.sqrt(252) * 100, 2)


def iv_hv_spread(iv: float | None, hv: float | None) -> float | None:
    if iv is None or hv is None:
        return None
    return round(iv - hv, 2)


def regime_label(spread: float | None) -> str:
    """Simple, explainable buckets rather than a continuous score - the
    Strategy Architect branches on these labels directly."""
    if spread is None:
        return "unknown"
    if spread >= 8:
        return "rich"       # IV well above realized - premium expensive, favor spreads/selling premium
    if spread <= -8:
        return "cheap"      # IV well below realized - premium cheap, favor buying options outright
    return "fair"


def term_structure(chain: OptionChainSnapshot | None) -> str:
    """Compares ATM IV of the nearest vs a further-out expiry. Contango (near
    < far) is the normal state; backwardation (near > far) usually signals a
    near-term event (earnings, a pending announcement) the market is pricing
    a spike around - directly relevant to whether it's safe to hold an
    options position through that date."""
    if chain is None or len(chain.expiries) < 2:
        return "unknown"

    def _atm_iv(expiry: str) -> float | None:
        atm = chain.atm_strike(expiry)
        leg = next((leg for leg in chain.legs_for_expiry(expiry) if leg.strike == atm), None)
        if leg is None:
            return None
        ivs = [v for v in (leg.call_iv, leg.put_iv) if v is not None]
        return sum(ivs) / len(ivs) if ivs else None

    near_iv = _atm_iv(chain.expiries[0])
    far_iv = _atm_iv(chain.expiries[1])
    if near_iv is None or far_iv is None:
        return "unknown"
    if near_iv > far_iv * 1.05:
        return "backwardation"
    if far_iv > near_iv * 1.05:
        return "contango"
    return "flat"


def analyze(daily_bars: pd.DataFrame | None, chain: OptionChainSnapshot | None) -> dict:
    """{action, confidence, evidence, metrics} - but note this agent's
    "action" is really a premium-cost signal, not a directional one: BUY here
    means "IV favors buying options", SELL means "IV favors selling/spreads",
    consumed by the Strategy Architect alongside the consensus direction, not
    as a standalone directional vote weighted the same way as Technical/
    Fundamental. See app/agents/analysts/volatility_regime.py."""
    hv = historical_volatility(daily_bars)
    current_iv = None
    if chain is not None and chain.legs:
        atm = chain.atm_strike()
        leg = next((leg for leg in chain.legs if leg.strike == atm), None)
        if leg is not None:
            ivs = [v for v in (leg.call_iv, leg.put_iv) if v is not None]
            current_iv = sum(ivs) / len(ivs) if ivs else None

    spread = iv_hv_spread(current_iv, hv)
    regime = regime_label(spread)
    structure = term_structure(chain)

    evidence = []
    if hv is not None:
        evidence.append(f"20-day realized volatility {hv:.1f}% (annualized).")
    if current_iv is not None:
        evidence.append(f"ATM implied volatility {current_iv:.1f}%.")
    if spread is not None:
        evidence.append(f"IV-HV spread {spread:+.1f}pp -> premium regime: {regime}.")
    if structure != "unknown":
        evidence.append(f"Vol term structure: {structure}" + (" - market pricing a near-term event." if structure == "backwardation" else "."))

    if regime == "cheap":
        action, confidence = "BUY", 0.55  # "BUY" = buy premium
    elif regime == "rich":
        action, confidence = "SELL", 0.55  # "SELL" = sell/spread premium
    else:
        action, confidence = "HOLD", 0.3

    return {
        "action": action,
        "confidence": confidence,
        "evidence": evidence or ["Insufficient daily-bar or options data for a volatility regime read this run."],
        "metrics": {
            "historical_volatility_pct": hv,
            "implied_volatility_pct": round(current_iv, 2) if current_iv is not None else None,
            "iv_hv_spread": spread,
            "regime": regime,
            "term_structure": structure,
        },
    }
