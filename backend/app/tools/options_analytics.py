"""Options chain analytics: IV rank/percentile, put-call OI ratio, max pain,
and straddle-implied expected move - the reads that tell a positional options
thesis apart from a plain "stock will go up" call (whether premium is cheap
or rich, whether the options market's own positioning agrees with the
directional case, how far the market is pricing the stock to move).

Pure-Python math over an OptionChainSnapshot (app/data/options_data.py) - no
I/O here, same separation-of-concerns as technical_indicators.py (indicator
math) vs market_data.py (fetching)."""

from __future__ import annotations

from app.data.options_data import IV_HISTORY_MIN_DAYS, OptionChainSnapshot


def iv_rank(current_iv: float, iv_history: list[float]) -> float | None:
    """0-100: where current IV sits within its own recent range (NOT a
    percentile-of-days-below, which is iv_percentile below) - the standard
    "IV Rank" definition options traders use to judge cheap vs rich premium."""
    if len(iv_history) < IV_HISTORY_MIN_DAYS:
        return None
    lo, hi = min(iv_history), max(iv_history)
    if hi <= lo:
        return 50.0
    return round(max(0.0, min(100.0, 100.0 * (current_iv - lo) / (hi - lo))), 1)


def iv_percentile(current_iv: float, iv_history: list[float]) -> float | None:
    """0-100: share of historical days where IV was below today's - a
    distribution-shape-aware complement to iv_rank (two symbols can share the
    same rank but very different percentiles if their IV distribution is
    skewed)."""
    if len(iv_history) < IV_HISTORY_MIN_DAYS:
        return None
    below = sum(1 for v in iv_history if v < current_iv)
    return round(100.0 * below / len(iv_history), 1)


def put_call_oi_ratio(chain: OptionChainSnapshot, expiry: str | None = None) -> float | None:
    legs = chain.legs_for_expiry(expiry) if expiry else chain.legs
    call_oi = sum(leg.call_oi or 0 for leg in legs)
    put_oi = sum(leg.put_oi or 0 for leg in legs)
    if call_oi <= 0:
        return None
    return round(put_oi / call_oi, 3)


def max_pain(chain: OptionChainSnapshot, expiry: str | None = None) -> float | None:
    """The strike at which option WRITERS collectively lose the least (and
    buyers the most) at expiry - a classic (imperfect, but widely used)
    "where the market wants to pin the price" heuristic, since writers are
    typically the better-capitalized side and have some ability to influence
    price into expiry via hedging flows."""
    legs = chain.legs_for_expiry(expiry) if expiry else chain.legs
    if not legs:
        return None

    strikes = [leg.strike for leg in legs]
    best_strike, best_pain = None, None
    for candidate in strikes:
        pain = 0.0
        for leg in legs:
            call_oi = leg.call_oi or 0
            put_oi = leg.put_oi or 0
            if candidate > leg.strike:
                pain += (candidate - leg.strike) * call_oi
            if candidate < leg.strike:
                pain += (leg.strike - candidate) * put_oi
        if best_pain is None or pain < best_pain:
            best_pain, best_strike = pain, candidate
    return best_strike


def expected_move(chain: OptionChainSnapshot, days_to_expiry: float, expiry: str | None = None) -> float | None:
    """Straddle-implied expected move (₹) to expiry, from the ATM call+put
    premium - the options market's own read of how far the stock is priced to
    move, independent of any agent's directional view. Uses the simple
    "ATM straddle premium ≈ 0.8 x expected move" approximation (the constant
    from the lognormal first-absolute-moment; standard practical shortcut,
    not exact)."""
    atm = chain.atm_strike(expiry)
    if atm is None:
        return None
    leg = next((leg for leg in chain.legs_for_expiry(expiry or chain.nearest_expiry()) if leg.strike == atm), None)
    if leg is None or leg.call_ltp is None or leg.put_ltp is None:
        return None
    straddle_premium = leg.call_ltp + leg.put_ltp
    return round(straddle_premium * 0.8, 2)


def oi_buildup_signal(chain: OptionChainSnapshot, spot_change_pct: float, expiry: str | None = None) -> dict:
    """Classic OI-buildup read: combines price direction with which side (put
    or call) OI is concentrated on to classify long buildup / short buildup /
    unwinding - a genuinely different information source from price action
    alone (it's what the options market is doing, not the stock)."""
    pcr = put_call_oi_ratio(chain, expiry)
    if pcr is None:
        return {"label": "unavailable", "pcr": None}

    if spot_change_pct > 0 and pcr < 0.9:
        label = "long_buildup"  # price up, call-heavy OI - bullish positioning building
    elif spot_change_pct < 0 and pcr > 1.1:
        label = "short_buildup"  # price down, put-heavy OI - bearish positioning building
    elif spot_change_pct > 0 and pcr > 1.1:
        label = "short_covering"  # price up despite put-heavy OI - bears closing out
    elif spot_change_pct < 0 and pcr < 0.9:
        label = "long_unwinding"  # price down despite call-heavy OI - bulls closing out
    else:
        label = "neutral"
    return {"label": label, "pcr": pcr}


def analyze(chain: OptionChainSnapshot | None, iv_history: list[float], spot_change_pct: float, days_to_expiry: float) -> dict:
    """Structured signal in the same {action, confidence, evidence, metrics}
    shape as technical_indicators.analyze()/risk_model.analyze(), so the IV &
    Options Chain Analyst can blend it exactly like every other agent blends
    its tool outputs (see app/agents/base.py blend_signals)."""
    if chain is None or not chain.legs:
        return {
            "action": "HOLD",
            "confidence": 0.15,
            "evidence": ["No live options chain data this run (NSE unreachable or symbol not in F&O) - IV/OI read skipped."],
            "metrics": {},
        }

    atm = chain.atm_strike()
    atm_leg = next((leg for leg in chain.legs if leg.strike == atm), None)
    current_iv = None
    if atm_leg is not None:
        ivs = [v for v in (atm_leg.call_iv, atm_leg.put_iv) if v is not None]
        current_iv = round(sum(ivs) / len(ivs), 2) if ivs else None

    rank = iv_rank(current_iv, iv_history) if current_iv is not None else None
    pctile = iv_percentile(current_iv, iv_history) if current_iv is not None else None
    pain = max_pain(chain)
    buildup = oi_buildup_signal(chain, spot_change_pct)
    move = expected_move(chain, days_to_expiry)

    evidence = []
    votes: list[tuple[str, float]] = []

    if current_iv is not None:
        evidence.append(f"ATM IV {current_iv:.1f}%" + (f" (IV rank {rank:.0f}/100)" if rank is not None else " (IV rank needs more history)"))
    if pain is not None:
        evidence.append(f"Max pain strike ₹{pain:,.0f}" + (f" vs spot ₹{chain.underlying_price:,.0f}" if chain.underlying_price else ""))
        if chain.underlying_price and pain < chain.underlying_price * 0.98:
            votes.append(("SELL", 0.3))
        elif chain.underlying_price and pain > chain.underlying_price * 1.02:
            votes.append(("BUY", 0.3))
    if buildup["label"] != "unavailable":
        evidence.append(f"OI buildup: {buildup['label'].replace('_', ' ')} (PCR {buildup['pcr']}).")
        if buildup["label"] in ("long_buildup", "short_covering"):
            votes.append(("BUY", 0.5))
        elif buildup["label"] in ("short_buildup", "long_unwinding"):
            votes.append(("SELL", 0.5))
    if move is not None:
        evidence.append(f"Options market prices an expected move of ~₹{move:,.0f} by nearest expiry.")

    if not votes:
        action, confidence = "HOLD", 0.2
    else:
        totals: dict[str, float] = {}
        for a, s in votes:
            totals[a] = totals.get(a, 0.0) + s
        action = max(totals, key=totals.get)
        confidence = round(min(0.85, max(0.2, totals[action] / max(len(votes), 1))), 3)

    return {
        "action": action,
        "confidence": confidence,
        "evidence": evidence or ["Options chain fetched but no strong IV/OI signal this run."],
        "metrics": {
            "atm_iv": current_iv,
            "iv_rank": rank,
            "iv_percentile": pctile,
            "max_pain": pain,
            "oi_buildup": buildup["label"],
            "put_call_oi_ratio": buildup.get("pcr"),
            "expected_move_inr": move,
        },
    }
