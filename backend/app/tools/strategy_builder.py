"""Strategy Architect's core math: turns a consensus direction + conviction +
volatility regime into an actual options structure (which strikes, which
expiry, long premium vs a spread) with max loss/profit, breakeven(s), and a
payoff curve for the dashboard chart.

This is the piece that turns "BUY, 62% directional confidence" into a
placeable options trade - see app/agents/strategy_architect.py for the
wrapper that calls this with live chain data, and docs/
POSITIONAL_OPTIONS_ENHANCEMENT_PLAN.md for why this exists as its own
non-voting stage rather than another analyst in the consensus.

All P&L figures here are PER SHARE (i.e. per one unit of the underlying), not
per NSE lot - NSE lot sizes are set/changed by the exchange periodically per
symbol and aren't available from the option chain response itself, so
multiplying by lot size is left to the caller/UI with a clear label rather
than silently guessing a lot size here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.data.options_data import OptionChainSnapshot, OptionLeg

HIGH_CONVICTION = 40.0  # directional_confidence (0-100) above which a single-leg long option is preferred even in a fair/rich regime


@dataclass
class StrategyLeg:
    action: str  # BUY | SELL
    option_type: str  # CALL | PUT
    strike: float
    premium: float | None


@dataclass
class StrategyPick:
    structure_type: str
    direction: str
    expiry: str
    legs: list[StrategyLeg]
    max_loss: float | None
    max_profit: float | None  # None means uncapped (long call/put)
    breakeven: list[float]
    payoff_points: list[tuple[float, float]] = field(default_factory=list)
    rationale: str = ""
    data_complete: bool = True  # False when premiums were missing and figures are estimates/absent


def _intrinsic(option_type: str, strike: float, spot: float) -> float:
    if option_type == "CALL":
        return max(spot - strike, 0.0)
    return max(strike - spot, 0.0)


def _payoff_at(legs: list[StrategyLeg], spot: float) -> float:
    total = 0.0
    for leg in legs:
        premium = leg.premium or 0.0
        sign = 1.0 if leg.action == "BUY" else -1.0
        total += sign * (_intrinsic(leg.option_type, leg.strike, spot) - premium)
    return total


def _payoff_curve(legs: list[StrategyLeg], spot: float, points: int = 41) -> list[tuple[float, float]]:
    lo, hi = spot * 0.75, spot * 1.25
    step = (hi - lo) / (points - 1)
    return [(round(lo + i * step, 2), round(_payoff_at(legs, lo + i * step), 2)) for i in range(points)]


def _nearest_leg(chain: OptionChainSnapshot, expiry: str, strike: float) -> OptionLeg | None:
    candidates = chain.legs_for_expiry(expiry)
    if not candidates:
        return None
    return min(candidates, key=lambda leg: abs(leg.strike - strike))


def _otm_strike(chain: OptionChainSnapshot, expiry: str, from_strike: float, option_type: str, steps: int) -> float:
    """Walks `steps` listed strikes out-of-the-money from from_strike (further
    from spot in the direction that's OTM for `option_type`)."""
    strikes = sorted({leg.strike for leg in chain.legs_for_expiry(expiry)})
    if from_strike not in strikes:
        strikes = sorted(strikes + [from_strike])
    idx = strikes.index(from_strike)
    if option_type == "CALL":
        target_idx = min(idx + steps, len(strikes) - 1)
    else:
        target_idx = max(idx - steps, 0)
    return strikes[target_idx]


def build_strategy(
    direction: str,
    directional_confidence: float,
    iv_regime: str,
    chain: OptionChainSnapshot | None,
    expiry: str | None = None,
    spread_width_steps: int = 2,
) -> StrategyPick | None:
    """direction: BUY or SELL (consensus winning_action). iv_regime: cheap |
    fair | rich | unknown (from volatility_regime.regime_label). Returns None
    when there's no options chain to build a real structure from - callers
    fall back to reporting the directional pick without a structure."""
    if direction not in ("BUY", "SELL") or chain is None or not chain.legs:
        return None

    expiry = expiry or chain.nearest_expiry()
    if expiry is None:
        return None
    spot = chain.underlying_price
    atm = chain.atm_strike(expiry)
    if atm is None:
        return None
    atm_leg = _nearest_leg(chain, expiry, atm)
    if atm_leg is None:
        return None

    option_type = "CALL" if direction == "BUY" else "PUT"

    # Cheap premium, or high conviction: buy the option outright rather than
    # give up upside to a spread - the whole point of a spread is reducing
    # premium cost/theta drag, which matters less when premium is already
    # cheap or when conviction is strong enough to justify full exposure.
    if iv_regime == "cheap" or directional_confidence >= HIGH_CONVICTION:
        premium = atm_leg.call_ltp if option_type == "CALL" else atm_leg.put_ltp
        legs = [StrategyLeg(action="BUY", option_type=option_type, strike=atm, premium=premium)]
        data_complete = premium is not None
        max_loss = premium
        max_profit = None  # uncapped
        breakeven = [atm + premium] if option_type == "CALL" and premium else ([atm - premium] if premium else [])
        structure_type = f"long_{option_type.lower()}"
        rationale = (
            f"IV regime is {iv_regime} and directional confidence is "
            f"{directional_confidence:.0f}% - buying the ATM {option_type.lower()} outright "
            "rather than giving up upside to a spread."
        )

    # Rich premium and moderate-to-strong conviction: debit spread caps cost
    # and theta exposure while still expressing the direction.
    elif iv_regime == "rich" and directional_confidence >= 20.0:
        far_strike = _otm_strike(chain, expiry, atm, option_type, spread_width_steps)
        far_leg = _nearest_leg(chain, expiry, far_strike)
        near_premium = atm_leg.call_ltp if option_type == "CALL" else atm_leg.put_ltp
        far_premium = (far_leg.call_ltp if option_type == "CALL" else far_leg.put_ltp) if far_leg else None
        legs = [
            StrategyLeg(action="BUY", option_type=option_type, strike=atm, premium=near_premium),
            StrategyLeg(action="SELL", option_type=option_type, strike=far_strike, premium=far_premium),
        ]
        data_complete = near_premium is not None and far_premium is not None
        if data_complete:
            net_debit = round(near_premium - far_premium, 2)
            width = abs(far_strike - atm)
            max_loss = max(net_debit, 0.0)
            max_profit = round(max(width - net_debit, 0.0), 2)
            breakeven = [round(atm + net_debit, 2)] if option_type == "CALL" else [round(atm - net_debit, 2)]
        else:
            max_loss = max_profit = None
            breakeven = []
        structure_type = f"{'bull' if option_type == 'CALL' else 'bear'}_{option_type.lower()}_debit_spread"
        rationale = (
            f"IV regime is rich - a debit spread (buy ATM {option_type.lower()}, sell an OTM "
            f"{option_type.lower()} {spread_width_steps} strikes out) caps premium paid and theta "
            "exposure versus buying the option outright."
        )

    # Rich premium, weaker conviction: sell a credit spread instead of paying
    # rich premium for a directional view the committee isn't fully behind.
    else:
        short_type = "PUT" if direction == "BUY" else "CALL"  # bull put spread for BUY, bear call spread for SELL
        short_strike = _otm_strike(chain, expiry, atm, short_type, 1)
        long_strike = _otm_strike(chain, expiry, short_strike, short_type, spread_width_steps)
        short_leg = _nearest_leg(chain, expiry, short_strike)
        long_leg = _nearest_leg(chain, expiry, long_strike)
        short_premium = (short_leg.put_ltp if short_type == "PUT" else short_leg.call_ltp) if short_leg else None
        long_premium = (long_leg.put_ltp if short_type == "PUT" else long_leg.call_ltp) if long_leg else None
        legs = [
            StrategyLeg(action="SELL", option_type=short_type, strike=short_strike, premium=short_premium),
            StrategyLeg(action="BUY", option_type=short_type, strike=long_strike, premium=long_premium),
        ]
        data_complete = short_premium is not None and long_premium is not None
        if data_complete:
            net_credit = round(short_premium - long_premium, 2)
            width = abs(short_strike - long_strike)
            max_profit = max(net_credit, 0.0)
            max_loss = round(max(width - net_credit, 0.0), 2)
            breakeven = [round(short_strike - net_credit, 2)] if short_type == "PUT" else [round(short_strike + net_credit, 2)]
        else:
            max_loss = max_profit = None
            breakeven = []
        structure_type = f"{'bull_put' if direction == 'BUY' else 'bear_call'}_credit_spread"
        rationale = (
            f"IV regime is rich and conviction is moderate ({directional_confidence:.0f}%) - selling a "
            f"{structure_type.replace('_', ' ')} collects rich premium with defined, capped risk instead of "
            "paying up for a directional option the committee isn't strongly behind."
        )

    payoff_points = _payoff_curve(legs, spot) if spot else []

    return StrategyPick(
        structure_type=structure_type,
        direction=direction,
        expiry=expiry,
        legs=legs,
        max_loss=max_loss,
        max_profit=max_profit,
        breakeven=breakeven,
        payoff_points=payoff_points,
        rationale=rationale,
        data_complete=data_complete,
    )
