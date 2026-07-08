"""Investment Planner Agent (Asset Allocation & Goal Setting): translates the
session's configured risk tolerance into concrete allocation caps (per-symbol,
per-sector) and session-level profit/loss goals that gate new trade entries.

This is distinct from InvestmentPlanner in agents/planner.py, which only
decides *which watchlist symbols* to analyze each tick (workflow scheduling).
This agent decides *how much capital may go where*, and *when to stop taking
new risk for the day* - the asset-allocation and goal-setting responsibilities
from the architecture spec."""

from __future__ import annotations

from dataclasses import dataclass

# Percentages are of max_exposure_inr (the leveraged capital base) for allocation
# caps, and of starting_capital_inr (unleveraged) for profit/loss goals, since a
# profit/loss target should be judged against capital actually at risk, not the
# leveraged buying power.
RISK_PROFILES = {
    "conservative": {"symbol_cap_pct": 20.0, "sector_cap_pct": 35.0, "profit_target_pct": 2.0, "loss_limit_pct": -1.5},
    "moderate": {"symbol_cap_pct": 35.0, "sector_cap_pct": 50.0, "profit_target_pct": 4.0, "loss_limit_pct": -3.0},
    "aggressive": {"symbol_cap_pct": 50.0, "sector_cap_pct": 70.0, "profit_target_pct": 7.0, "loss_limit_pct": -5.0},
}
DEFAULT_RISK_TOLERANCE = "moderate"


@dataclass
class AllocationPlan:
    risk_tolerance: str
    max_exposure_inr: float
    symbol_cap_inr: float
    sector_cap_inr: float
    profit_target_inr: float
    loss_limit_inr: float
    reasoning: str


def build_plan(risk_tolerance: str, starting_capital_inr: float, max_exposure_inr: float) -> AllocationPlan:
    tolerance = risk_tolerance if risk_tolerance in RISK_PROFILES else DEFAULT_RISK_TOLERANCE
    profile = RISK_PROFILES[tolerance]

    symbol_cap_inr = round(max_exposure_inr * profile["symbol_cap_pct"] / 100, 2)
    sector_cap_inr = round(max_exposure_inr * profile["sector_cap_pct"] / 100, 2)
    profit_target_inr = round(starting_capital_inr * profile["profit_target_pct"] / 100, 2)
    loss_limit_inr = round(starting_capital_inr * profile["loss_limit_pct"] / 100, 2)

    reasoning = (
        f"Risk tolerance '{tolerance}': no single symbol may draw more than ₹{symbol_cap_inr:,.0f} "
        f"({profile['symbol_cap_pct']:.0f}% of the ₹{max_exposure_inr:,.0f} leveraged exposure budget); "
        f"no single sector may draw more than ₹{sector_cap_inr:,.0f} ({profile['sector_cap_pct']:.0f}%). "
        f"Session goal: stop opening new positions once profit reaches +₹{profit_target_inr:,.0f} "
        f"({profile['profit_target_pct']:.1f}% of starting capital), or once loss reaches "
        f"₹{loss_limit_inr:,.0f} ({profile['loss_limit_pct']:.1f}%)."
    )

    return AllocationPlan(
        risk_tolerance=tolerance,
        max_exposure_inr=max_exposure_inr,
        symbol_cap_inr=symbol_cap_inr,
        sector_cap_inr=sector_cap_inr,
        profit_target_inr=profit_target_inr,
        loss_limit_inr=loss_limit_inr,
        reasoning=reasoning,
    )
