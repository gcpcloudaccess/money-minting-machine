from __future__ import annotations

from dataclasses import dataclass

from .data import PriceBar
from .features import build_feature_rows
from .model import train_model


@dataclass(frozen=True)
class BacktestResult:
    start_date: str
    end_date: str
    trades: int
    total_return_pct: float
    buy_hold_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    final_equity: float


def backtest(
    bars: list[PriceBar],
    horizon: int = 5,
    train_window: int = 180,
    buy_threshold: float = 0.58,
    sell_threshold: float = 0.42,
    fee_bps: float = 3.0,
) -> BacktestResult:
    rows = build_feature_rows(bars, horizon=horizon)
    labeled = [row for row in rows if row.label is not None]
    if len(labeled) < train_window + horizon + 10:
        raise ValueError("Need more data for backtest. Try at least 320 daily bars.")

    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    position = 0
    trades = 0
    winning_steps = 0
    evaluated_steps = 0
    fee = fee_bps / 10_000.0

    for index in range(train_window, len(labeled) - 1):
        train_slice = labeled[index - train_window : index]
        model = train_model(
            [row.features for row in train_slice],
            [int(row.label) for row in train_slice],
            validation_fraction=0.2,
        )
        probability = model.predict_probability(labeled[index].features)
        next_return = (labeled[index + 1].close - labeled[index].close) / labeled[index].close

        desired_position = 1 if probability >= buy_threshold else -1 if probability <= sell_threshold else 0
        if desired_position != position:
            equity *= 1.0 - fee
            trades += 1
            position = desired_position

        step_return = position * next_return
        if step_return > 0:
            winning_steps += 1
        if position != 0:
            evaluated_steps += 1

        equity *= 1.0 + step_return
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1.0)

    first = labeled[train_window]
    last = labeled[-1]
    buy_hold = last.close / first.close - 1.0
    win_rate = winning_steps / evaluated_steps if evaluated_steps else 0.0
    return BacktestResult(
        start_date=first.date,
        end_date=last.date,
        trades=trades,
        total_return_pct=round((equity - 1.0) * 100.0, 2),
        buy_hold_return_pct=round(buy_hold * 100.0, 2),
        max_drawdown_pct=round(max_drawdown * 100.0, 2),
        win_rate_pct=round(win_rate * 100.0, 2),
        final_equity=round(equity, 4),
    )
