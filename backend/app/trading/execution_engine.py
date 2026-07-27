"""Simulated (paper) order execution: applies fills to the portfolio ledger
using the realistic cost model, enforces the leverage/exposure cap, and
records every trade for the audit trail."""

from __future__ import annotations

from app.config import get_settings
from app.db.session import DbSession as Session
from app.db.models import Portfolio, Position, Trade
from app.trading.costs import compute_costs


def get_active_portfolio(db: Session, exchange: str | None = None) -> Portfolio:
    """Returns the active session FOR THIS EXCHANGE (default NSE), creating a
    fresh one if none exists. Each exchange keeps its own independent active
    portfolio - since CRYPTO_INDIA trades 24/7 and NSE only during its own
    session hours (see app/data/exchanges.py), there is no longer a single
    global "the active portfolio": NSE and CRYPTO_INDIA can both be active at
    once, ticking independently (see app/orchestration/session_runner.py).
    Every existing caller that omits `exchange` keeps getting the NSE
    portfolio, unchanged."""
    scope = exchange or "NSE"
    portfolio = db.query(Portfolio).filter_by(status="active", exchange=scope).order_by(Portfolio.id.desc()).first()
    if portfolio is None:
        settings = get_settings()
        portfolio = Portfolio(
            cash_inr=settings.starting_capital_inr,
            starting_capital=settings.starting_capital_inr,
            leverage=settings.leverage,
            status="active",
            exchange=scope,
        )
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
    return portfolio


def get_open_exposure(db: Session, portfolio: Portfolio) -> float:
    positions = db.query(Position).filter_by(portfolio_id=portfolio.id, status="open").all()
    return sum(p.quantity * p.avg_price for p in positions)


def get_open_positions(db: Session, portfolio: Portfolio) -> list[Position]:
    return db.query(Position).filter_by(portfolio_id=portfolio.id, status="open").all()


def get_open_position(db: Session, portfolio: Portfolio, symbol: str) -> Position | None:
    return db.query(Position).filter_by(portfolio_id=portfolio.id, symbol=symbol, status="open").one_or_none()


def open_position(
    db: Session, portfolio: Portfolio, symbol: str, side: str, quantity: float, price: float, decision_id: int | None,
    exchange: str = "NSE", currency: str = "INR", price_local: float | None = None, fx_rate_to_inr: float = 1.0,
    stop_loss: float | None = None, target_price: float | None = None,
) -> Trade:
    """`price` is always in INR (NSE-only, INR-only build - no FX conversion
    needed). `price_local`/`currency`/`fx_rate_to_inr` are kept as fields
    purely for schema stability, always price/"INR"/1.0 in this build.
    stop_loss/target_price are optional (Stock Search's preview path and
    tests don't always set them) - see portfolio_manager.process_decision
    for how they're actually computed for a real entry."""
    action = "BUY" if side == "LONG" else "SELL"
    costs = compute_costs(action, quantity, price, exchange=exchange, fx_rate_to_inr=fx_rate_to_inr)
    gross = quantity * price
    net_cash_impact = -(gross + costs["total"]) if side == "LONG" else (gross - costs["total"])

    position = Position(
        portfolio_id=portfolio.id, symbol=symbol, side=side, quantity=quantity, avg_price=price,
        exchange=exchange, currency=currency, fx_rate_to_inr=fx_rate_to_inr,
        stop_loss=stop_loss, target_price=target_price,
    )
    db.add(position)
    db.flush()

    trade = Trade(
        portfolio_id=portfolio.id,
        decision_id=decision_id,
        position_id=position.id,
        symbol=symbol,
        action=action,
        quantity=quantity,
        price=price,
        gross_value=gross,
        total_costs=costs["total"],
        cost_breakdown_json=costs,
        net_cash_impact=net_cash_impact,
        exchange=exchange, currency=currency, price_local=price_local if price_local is not None else price, fx_rate_to_inr=fx_rate_to_inr,
    )
    db.add(trade)

    portfolio.cash_inr += net_cash_impact
    db.add(portfolio)
    db.commit()
    db.refresh(trade)
    return trade


def close_position(
    db: Session, portfolio: Portfolio, position: Position, price: float, decision_id: int | None,
    price_local: float | None = None, fx_rate_to_inr: float | None = None,
) -> Trade:
    """Closes on the position's OWN exchange (recorded at open time) so the
    cost model matches where the position actually lives, even if the active
    session has since rolled over to a different market."""
    action = "SELL" if position.side == "LONG" else "BUY"
    exchange = position.exchange
    effective_fx_rate = fx_rate_to_inr if fx_rate_to_inr is not None else position.fx_rate_to_inr
    costs = compute_costs(action, position.quantity, price, exchange=exchange, fx_rate_to_inr=effective_fx_rate)
    gross = position.quantity * price

    if position.side == "LONG":
        net_cash_impact = gross - costs["total"]
        realized_pnl = (price - position.avg_price) * position.quantity - costs["total"]
    else:
        net_cash_impact = -(gross + costs["total"])
        realized_pnl = (position.avg_price - price) * position.quantity - costs["total"]

    position.status = "closed"
    position.exit_price = price
    position.realized_pnl = realized_pnl
    db.add(position)

    trade = Trade(
        portfolio_id=portfolio.id,
        decision_id=decision_id,
        position_id=position.id,
        symbol=position.symbol,
        action=action,
        quantity=position.quantity,
        price=price,
        gross_value=gross,
        total_costs=costs["total"],
        cost_breakdown_json=costs,
        net_cash_impact=net_cash_impact,
        exchange=exchange, currency=position.currency,
        price_local=price_local if price_local is not None else price, fx_rate_to_inr=effective_fx_rate,
    )
    db.add(trade)

    portfolio.cash_inr += net_cash_impact
    db.add(portfolio)
    db.commit()
    db.refresh(trade)
    return trade


def force_close_all(db: Session, portfolio: Portfolio, price_lookup: dict[str, float]) -> list[Trade]:
    trades = []
    open_positions = db.query(Position).filter_by(portfolio_id=portfolio.id, status="open").all()
    for pos in open_positions:
        price = price_lookup.get(pos.symbol)
        if price is None:
            continue
        trades.append(close_position(db, portfolio, pos, price, decision_id=None))
    return trades


def check_stop_loss_target(db: Session, portfolio: Portfolio, price_lookup: dict[str, float]) -> list[dict]:
    """Positional-mode exit guardrail: runs every tick (see session_runner.py),
    purely on current price - no LLM/committee call, so it's cheap enough to
    check unconditionally regardless of whether this tick's committee budget
    happened to include a given symbol (see agents/planner.py). Complements
    rather than replaces the existing reversal-based exit (portfolio_manager's
    SELL/SWITCH handling): a position can still be closed by the committee
    changing its mind, this only additionally catches a stop-loss/target hit
    between committee re-evaluations. Long-only (see portfolio_manager.py),
    so a breach is simply price <= stop_loss or price >= target_price."""
    closed: list[dict] = []
    open_positions = db.query(Position).filter_by(portfolio_id=portfolio.id, status="open").all()
    for pos in open_positions:
        price = price_lookup.get(pos.symbol)
        if price is None:
            continue
        reason = None
        if pos.stop_loss is not None and price <= pos.stop_loss:
            reason = "stop_loss"
        elif pos.target_price is not None and price >= pos.target_price:
            reason = "target"
        if reason is None:
            continue
        trade = close_position(db, portfolio, pos, price, decision_id=None)
        closed.append({
            "symbol": pos.symbol, "reason": reason, "price": price,
            "stop_loss": pos.stop_loss, "target_price": pos.target_price,
            "realized_pnl": pos.realized_pnl, "trade_id": trade.id,
        })
    return closed
