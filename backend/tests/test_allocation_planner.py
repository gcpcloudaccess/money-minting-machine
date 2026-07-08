"""Tests for the Investment Planner's asset-allocation & goal-setting agent -
no network, no LLM key required."""

from app.agents import allocation_planner


def test_unknown_risk_tolerance_falls_back_to_moderate():
    plan = allocation_planner.build_plan("not_a_real_profile", 10_000.0, 20_000.0)
    assert plan.risk_tolerance == "moderate"


def test_caps_scale_with_max_exposure_not_starting_capital():
    plan = allocation_planner.build_plan("moderate", 10_000.0, 20_000.0)
    profile = allocation_planner.RISK_PROFILES["moderate"]
    assert plan.symbol_cap_inr == round(20_000.0 * profile["symbol_cap_pct"] / 100, 2)
    assert plan.sector_cap_inr == round(20_000.0 * profile["sector_cap_pct"] / 100, 2)


def test_goals_scale_with_starting_capital_not_leveraged_exposure():
    plan = allocation_planner.build_plan("moderate", 10_000.0, 20_000.0)
    profile = allocation_planner.RISK_PROFILES["moderate"]
    assert plan.profit_target_inr == round(10_000.0 * profile["profit_target_pct"] / 100, 2)
    assert plan.loss_limit_inr == round(10_000.0 * profile["loss_limit_pct"] / 100, 2)


def test_aggressive_profile_takes_more_risk_than_conservative():
    conservative = allocation_planner.build_plan("conservative", 10_000.0, 20_000.0)
    aggressive = allocation_planner.build_plan("aggressive", 10_000.0, 20_000.0)
    assert aggressive.symbol_cap_inr > conservative.symbol_cap_inr
    assert aggressive.sector_cap_inr > conservative.sector_cap_inr
    assert aggressive.profit_target_inr > conservative.profit_target_inr
    # Loss limits are negative - "more risk tolerant" means a larger (more negative) limit.
    assert aggressive.loss_limit_inr < conservative.loss_limit_inr


def test_reasoning_mentions_key_figures():
    plan = allocation_planner.build_plan("moderate", 10_000.0, 20_000.0)
    assert "moderate" in plan.reasoning
    assert f"{plan.symbol_cap_inr:,.0f}" in plan.reasoning
    assert f"{plan.profit_target_inr:,.0f}" in plan.reasoning
