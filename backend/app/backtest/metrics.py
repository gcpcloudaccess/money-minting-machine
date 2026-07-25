"""Performance metrics for a backtest equity curve - real formulas (Sharpe,
max drawdown, CAGR, profit factor), not placeholders. Pure Python/pandas, no
I/O, so these are independently unit-testable with synthetic curves."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Trade:
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl_after_costs: float
    total_costs: float


@dataclass
class BacktestMetrics:
    total_return_pct: float
    cagr_pct: float
    benchmark_return_pct: float
    alpha_pct: float  # strategy return minus buy-and-hold return over the same window
    num_trades: int
    win_rate_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float | None  # None when there are no losing trades to divide by
    sharpe_ratio: float | None  # None when there's too little history to estimate variance
    max_drawdown_pct: float
    total_costs_inr: float
    starting_capital_inr: float
    ending_equity_inr: float


def _drawdown_series(equity: list[float]) -> list[float]:
    peak = equity[0] if equity else 0.0
    out = []
    for v in equity:
        peak = max(peak, v)
        out.append((v - peak) / peak if peak else 0.0)
    return out


def max_drawdown_pct(equity: list[float]) -> float:
    if not equity:
        return 0.0
    return round(min(_drawdown_series(equity)) * 100, 2)


def sharpe_ratio(equity: list[float], periods_per_year: float) -> float | None:
    """Annualized Sharpe from per-bar equity returns, 0% risk-free rate (a
    reasonable simplification for a short-horizon intraday/crypto strategy -
    real Indian T-bill rates would shave a small, roughly constant amount off
    every strategy's Sharpe, not change the ranking between them)."""
    if len(equity) < 3:
        return None
    returns = [(equity[i] - equity[i - 1]) / equity[i - 1] for i in range(1, len(equity)) if equity[i - 1] != 0]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return None
    return round((mean / std) * math.sqrt(periods_per_year), 3)


def compute_metrics(
    equity_curve: list[float],
    trades: list[Trade],
    benchmark_equity_curve: list[float],
    periods_per_year: float,
    elapsed_days: float,
) -> BacktestMetrics:
    starting_capital = equity_curve[0] if equity_curve else 0.0
    ending_equity = equity_curve[-1] if equity_curve else 0.0
    total_return_pct = round((ending_equity - starting_capital) / starting_capital * 100, 2) if starting_capital else 0.0

    benchmark_start = benchmark_equity_curve[0] if benchmark_equity_curve else 0.0
    benchmark_end = benchmark_equity_curve[-1] if benchmark_equity_curve else 0.0
    benchmark_return_pct = round((benchmark_end - benchmark_start) / benchmark_start * 100, 2) if benchmark_start else 0.0

    years = max(elapsed_days / 365.25, 1e-6)
    cagr_pct = round((((ending_equity / starting_capital) ** (1 / years)) - 1) * 100, 2) if starting_capital > 0 and ending_equity > 0 else 0.0

    wins = [t for t in trades if t.pnl_after_costs > 0]
    losses = [t for t in trades if t.pnl_after_costs <= 0]
    win_rate_pct = round(len(wins) / len(trades) * 100, 1) if trades else 0.0
    avg_win_pct = round(sum(t.pnl_after_costs / (t.entry_price * t.quantity) for t in wins) / len(wins) * 100, 2) if wins else 0.0
    avg_loss_pct = round(sum(t.pnl_after_costs / (t.entry_price * t.quantity) for t in losses) / len(losses) * 100, 2) if losses else 0.0

    gross_win = sum(t.pnl_after_costs for t in wins)
    gross_loss = abs(sum(t.pnl_after_costs for t in losses))
    profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else None

    total_costs = round(sum(t.total_costs for t in trades), 2)

    return BacktestMetrics(
        total_return_pct=total_return_pct,
        cagr_pct=cagr_pct,
        benchmark_return_pct=benchmark_return_pct,
        alpha_pct=round(total_return_pct - benchmark_return_pct, 2),
        num_trades=len(trades),
        win_rate_pct=win_rate_pct,
        avg_win_pct=avg_win_pct,
        avg_loss_pct=avg_loss_pct,
        profit_factor=profit_factor,
        sharpe_ratio=sharpe_ratio(equity_curve, periods_per_year),
        max_drawdown_pct=max_drawdown_pct(equity_curve),
        total_costs_inr=total_costs,
        starting_capital_inr=starting_capital,
        ending_equity_inr=ending_equity,
    )
