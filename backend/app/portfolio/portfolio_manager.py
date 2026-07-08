"""Portfolio Manager Agent: turns a consensus verdict for one symbol into a
concrete portfolio action (open / close / switch / no-op), coordinating
position sizing, scenario analysis, execution advice, and the execution engine.
Long-only for this build (no margin shorting) - keeps the paper-trading model
simple and safe to reason about within a hackathon timeframe."""

from __future__ import annotations

from sqlalchemy.orm import Session

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
) -> dict:
    existing = execution_engine.get_open_position(db, portfolio, symbol)
    advice = execution_advisor.advise(verdict, directional_confidence_pct, risk_level)

    if verdict in ("HOLD", "WAIT"):
        return {"executed": False, "reason": f"Consensus verdict is {verdict}; no action taken.", "advice": advice}

    if verdict == "BUY":
        if existing is not None:
            return {"executed": False, "reason": f"Already long {symbol}; no additional entry this tick.", "advice": advice}

        open_exposure = execution_engine.get_open_exposure(db, portfolio)
        sizing = position_sizing.size_position(directional_confidence_pct, risk_level, price, open_exposure, portfolio.cash_inr)
        if sizing["quantity"] <= 0:
            return {"executed": False, "reason": "Position sizing returned 0 shares (exposure/cash cap reached).", "sizing": sizing, "advice": advice}

        scenario = scenario_analysis.stress_test(price, sizing["quantity"], "LONG", volatility)
        trade = execution_engine.open_position(db, portfolio, symbol, "LONG", sizing["quantity"], price, decision_id)
        return {"executed": True, "action": "OPEN_LONG", "trade_id": trade.id, "sizing": sizing, "scenario": scenario, "advice": advice}

    if verdict in ("SELL", "SWITCH"):
        if existing is None:
            return {"executed": False, "reason": f"No open {symbol} position to exit; short-selling not enabled in this build.", "advice": advice}

        scenario = scenario_analysis.stress_test(existing.avg_price, existing.quantity, existing.side, volatility)
        trade = execution_engine.close_position(db, portfolio, existing, price, decision_id)
        return {"executed": True, "action": "CLOSE_LONG", "trade_id": trade.id, "realized_pnl": existing.realized_pnl, "scenario": scenario, "advice": advice}

    return {"executed": False, "reason": f"Unrecognized verdict {verdict}.", "advice": advice}
