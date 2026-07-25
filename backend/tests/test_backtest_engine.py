"""Smoke test for the backtest engine (app/backtest/engine.py) - proves it
runs the real committee pipeline end-to-end on synthetic OHLCV data without
crashing and returns internally-consistent results. This does NOT assert
anything about real trading accuracy (synthetic zero-drift random walk data
has no genuine signal to find) - see run_backtest.py for that, run against
real historical data. No network/DB required (LLM narration degrades to
templated fallback text with no API key configured, same as every other
agent test in this suite)."""

import numpy as np
import pandas as pd

from app.backtest.engine import BacktestConfig, run_backtest


def _synthetic_bars(n=400, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start_price = 5_000_000.0
    returns = rng.normal(0, 0.002, n)
    closes = start_price * np.cumprod(1 + returns)
    idx = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame(
        {
            "Open": closes * 0.9998, "High": closes * 1.0015, "Low": closes * 0.9985,
            "Close": closes, "Volume": rng.integers(1, 50, n).astype(float),
        },
        index=idx,
    )


def test_backtest_runs_without_crashing_and_produces_consistent_report():
    bars = _synthetic_bars(n=400)
    config = BacktestConfig(symbol="BTCINR", starting_capital_inr=100_000.0, warmup_bars=100, decision_every_n_bars=15)

    run = run_backtest(bars, config)

    assert run.metrics.starting_capital_inr == 100_000.0
    assert run.metrics.ending_equity_inr > 0
    assert len(run.equity_curve) == len(bars) - config.warmup_bars
    assert len(run.benchmark_equity_curve) == len(run.equity_curve)
    # Every decision bar should have produced a logged decision (or a caught error), never silently nothing.
    assert len(run.decisions) > 0
    for d in run.decisions:
        assert "timestamp" in d


def test_backtest_requires_more_than_warmup_bars():
    bars = _synthetic_bars(n=50)
    config = BacktestConfig(warmup_bars=100)
    try:
        run_backtest(bars, config)
        assert False, "expected ValueError for too-short history"
    except ValueError:
        pass


def test_trades_have_consistent_pnl_sign_with_price_direction():
    bars = _synthetic_bars(n=400, seed=11)
    config = BacktestConfig(warmup_bars=100, decision_every_n_bars=10)
    run = run_backtest(bars, config)

    for t in run.trades:
        implied_pnl_before_costs = (t.exit_price - t.entry_price) * t.quantity
        # after-cost pnl should never exceed the raw price-move pnl (costs only ever subtract)
        assert t.pnl_after_costs <= implied_pnl_before_costs + 1e-6
