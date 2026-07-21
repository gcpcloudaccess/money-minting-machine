"""Portfolio Manager Agent: turns a consensus verdict for one symbol into a
concrete portfolio action (open / close / switch / no-op), coordinating
position sizing, scenario analysis, execution advice, and the execution engine.
Long-only for this build (no margin shorting) - keeps the paper-trading model
simple and safe to reason about within a hackathon timeframe."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents import allocation_planner
from app.config import get_settings
from app.data import exchanges, fundamentals
from app.db.models import Portfolio
from app.portfolio import execution_advisor, position_sizing, scenario_analysis
from app.trading import execution_engine


def process_decision(
    db: Session,
    portfolio: Portfolio,
    symbol: str,
    verdict: str,
    directional_confidence_pct: float,
    risk_level: str,
    volatility: float | None,
    price: float,
    decision_id: int | None,
    exchange: str = "NSE",
    price_local: float | None = None,
    fx_rate_to_inr: float = 1.0,
) -> dict:
    """`price` is always INR (NSE-only, INR-only build - no conversion needed);
    `price_local`/`fx_rate_to_inr` are only threaded through to execution_engine
    for schema compatibility on the Trade row."""
    existing = execution_engine.get_open_position(db, portfolio, symbol)
    advice = execution_advisor.advise(verdict, directional_confidence_pct, risk_level)

    if verdict in ("HOLD", "WAIT"):
        return {"executed": False, "reason": f"Consensus verdict is {verdict}; no action taken.", "advice": advice}

    # SWITCH with no current holding in this symbol has nothing to switch *out of* - the
    # Opportunity Critic's signal ("a better alternative exists") only makes sense relative
    # to an existing position. Without one, the committee still found enough directional
    # conviction to clear the decisive threshold, so treat it as a BUY on this symbol rather
    # than silently no-op'ing a verdict the rest of the system already committed to.
    if verdict == "BUY" or (verdict == "SWITCH" and existing is None):
        if existing is not None:
            return {"executed": False, "reason": f"Already long {symbol}; no additional entry this tick.", "advice": advice}

        settings = get_settings()
        plan = allocation_planner.build_plan(settings.risk_tolerance, portfolio.starting_capital, portfolio.leverage * portfolio.starting_capital)

        # Investment Planner's session-level goals: once today's approximate P&L (cash +
        # cost-basis of open positions - starting capital) hits the profit target or loss
        # limit, stop opening *new* risk for the rest of the session. Existing positions are
        # still monitored/closed normally elsewhere - this only gates fresh entries.
        open_exposure = execution_engine.get_open_exposure(db, portfolio)
        running_pnl_estimate = portfolio.cash_inr + open_exposure - portfolio.starting_capital
        if running_pnl_estimate >= plan.profit_target_inr:
            return {
                "executed": False,
                "reason": f"Daily profit target of ₹{plan.profit_target_inr:,.0f} reached (~₹{running_pnl_estimate:,.0f}) — no new entries this session.",
                "advice": advice, "allocation_plan": plan.__dict__,
            }
        if running_pnl_estimate <= plan.loss_limit_inr:
            return {
                "executed": False,
                "reason": f"Daily loss limit of ₹{plan.loss_limit_inr:,.0f} hit (~₹{running_pnl_estimate:,.0f}) — no new entries this session.",
                "advice": advice, "allocation_plan": plan.__dict__,
            }

        # Skip the sector lookup entirely when there's nothing open to compare against -
        # avoids a network round-trip on every trade decision in the common case (a flat
        # portfolio, or the first entry of the session) where sector_exposure is trivially 0.
        open_positions = execution_engine.get_open_positions(db, portfolio)
        if open_positions:
            symbol_sector = fundamentals.get_sector(symbol)
            sector_exposure = sum(
                p.quantity * p.avg_price for p in open_positions if fundamentals.get_sector(p.symbol) == symbol_sector
            )
        else:
            sector_exposure = 0.0
        sizing = position_sizing.size_position(
            directional_confidence_pct, risk_level, price, open_exposure, portfolio.cash_inr,
            symbol_cap_inr=plan.symbol_cap_inr, sector_cap_inr=plan.sector_cap_inr,
            current_sector_exposure=sector_exposure, allow_fractional=(exchange != "NSE"),
        )
        if sizing["quantity"] <= 0:
            return {"executed": False, "reason": sizing.get("reason", "Position sizing returned 0 shares."), "sizing": sizing, "advice": advice}

        scenario = scenario_analysis.stress_test(price, sizing["quantity"], "LONG", volatility)
        trade = execution_engine.open_position(
            db, portfolio, symbol, "LONG", sizing["quantity"], price, decision_id,
            exchange=exchange, currency=exchanges.get_exchange(exchange).currency, price_local=price_local, fx_rate_to_inr=fx_rate_to_inr,
        )
        action = "OPEN_LONG" if verdict == "BUY" else "OPEN_LONG_FROM_SWITCH"
        return {"executed": True, "action": action, "trade_id": trade.id, "sizing": sizing, "scenario": scenario, "advice": advice}

    if verdict in ("SELL", "SWITCH"):
        if existing is None:
            return {"executed": False, "reason": f"No open {symbol} position to exit; short-selling not enabled in this build.", "advice": advice}

        scenario = scenario_analysis.stress_test(existing.avg_price, existing.quantity, existing.side, volatility)
        trade = execution_engine.close_position(db, portfolio, existing, price, decision_id, price_local=price_local, fx_rate_to_inr=fx_rate_to_inr)
        return {"executed": True, "action": "CLOSE_LONG", "trade_id": trade.id, "realized_pnl": existing.realized_pnl, "scenario": scenario, "advice": advice}

    return {"executed": False, "reason": f"Unrecognized verdict {verdict}.", "advice": advice}
