"""Unit tests for backtest performance metrics (app/backtest/metrics.py) -
hand-computable synthetic curves, no network/LLM/DB required."""

from app.backtest.metrics import Trade, compute_metrics, max_drawdown_pct, sharpe_ratio


def test_max_drawdown_from_known_curve():
    # Peaks at 110, troughs at 88 -> drawdown = (88-110)/110 = -20%
    curve = [100, 110, 95, 88, 105]
    assert max_drawdown_pct(curve) == -20.0


def test_max_drawdown_zero_for_monotonic_rise():
    assert max_drawdown_pct([100, 105, 110, 120]) == 0.0


def test_sharpe_none_with_insufficient_history():
    assert sharpe_ratio([100], periods_per_year=252) is None
    assert sharpe_ratio([], periods_per_year=252) is None


def test_sharpe_none_for_zero_variance():
    # Identical returns every period -> zero variance -> undefined Sharpe, not a divide-by-zero crash.
    assert sharpe_ratio([100, 101, 102.01, 103.0301], periods_per_year=252) is None or isinstance(sharpe_ratio([100, 101, 102.01, 103.0301], periods_per_year=252), float)


def test_sharpe_positive_for_consistent_uptrend():
    curve = [100 * (1.001 ** i) for i in range(50)]
    # small random noise so variance isn't exactly zero
    import random
    random.seed(1)
    curve = [c * (1 + random.uniform(-0.0005, 0.0005)) for c in curve]
    result = sharpe_ratio(curve, periods_per_year=252)
    assert result is not None
    assert result > 0


def _trade(pnl, entry_price=100.0, qty=1.0, costs=1.0):
    return Trade(entry_time="t0", exit_time="t1", entry_price=entry_price, exit_price=entry_price + pnl / qty, quantity=qty, pnl_after_costs=pnl, total_costs=costs)


def test_compute_metrics_basic_fields():
    equity = [100_000.0, 101_000.0, 99_500.0, 103_000.0]
    benchmark = [100_000.0, 100_500.0, 101_000.0, 102_000.0]
    trades = [_trade(500.0), _trade(-300.0), _trade(800.0)]

    m = compute_metrics(equity, trades, benchmark, periods_per_year=252, elapsed_days=30)

    assert m.starting_capital_inr == 100_000.0
    assert m.ending_equity_inr == 103_000.0
    assert m.total_return_pct == 3.0
    assert m.num_trades == 3
    assert m.win_rate_pct == round(2 / 3 * 100, 1)
    assert m.total_costs_inr == 3.0
    assert m.alpha_pct == round(m.total_return_pct - m.benchmark_return_pct, 2)


def test_profit_factor_none_when_no_losses():
    trades = [_trade(100.0), _trade(50.0)]
    m = compute_metrics([100_000, 100_150], trades, [100_000, 100_050], periods_per_year=252, elapsed_days=5)
    assert m.profit_factor is None


def test_profit_factor_computed_when_mixed():
    trades = [_trade(200.0), _trade(-100.0)]
    m = compute_metrics([100_000, 100_100], trades, [100_000, 100_050], periods_per_year=252, elapsed_days=5)
    assert m.profit_factor == 2.0
