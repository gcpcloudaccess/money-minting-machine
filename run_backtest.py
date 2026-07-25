"""Backtest CLI: replays historical OHLCV bars (a CSV from
backend/scripts/fetch_backtest_data.py, or any CSV shaped the same way -
DatetimeIndex + Open/High/Low/Close/Volume columns) through the real
production decision pipeline and reports whether it actually has edge.

    python run_backtest.py --csv data_cache/backtest_BTCINR_5m.csv
    python run_backtest.py --csv data_cache/backtest_BTCINR_1h.csv --decision-every 2

See app/backtest/engine.py's module docstring for exactly what this does and
does not validate (which analysts are excluded and why, the neutral-trust-
score caveat) before trusting the numbers it prints.
"""

import argparse
import os
import sys

BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

import pandas as pd  # noqa: E402

from app.backtest.engine import BacktestConfig, run_backtest  # noqa: E402


def _print_report(run) -> None:
    m = run.metrics
    print()
    print("=" * 70)
    print("BACKTEST REPORT")
    print("=" * 70)
    print(f"Starting capital:      Rs {m.starting_capital_inr:,.2f}")
    print(f"Ending equity:         Rs {m.ending_equity_inr:,.2f}")
    print(f"Total return:          {m.total_return_pct:+.2f}%")
    print(f"CAGR (annualized):     {m.cagr_pct:+.2f}%")
    print(f"Buy-and-hold return:   {m.benchmark_return_pct:+.2f}%  <- same window, just holding the asset")
    print(f"Alpha vs buy-and-hold: {m.alpha_pct:+.2f}%  <- negative means the algo did WORSE than doing nothing")
    print("-" * 70)
    print(f"Trades:                {m.num_trades}")
    print(f"Win rate:              {m.win_rate_pct:.1f}%")
    print(f"Avg win / avg loss:    {m.avg_win_pct:+.2f}% / {m.avg_loss_pct:+.2f}%")
    print(f"Profit factor:         {m.profit_factor if m.profit_factor is not None else 'n/a (no losing trades)'}")
    print(f"Sharpe ratio:          {m.sharpe_ratio if m.sharpe_ratio is not None else 'n/a (too little history)'}")
    print(f"Max drawdown:          {m.max_drawdown_pct:.2f}%")
    print(f"Total costs paid:      Rs {m.total_costs_inr:,.2f}  <- CoinDCX fee + GST + Section 194S TDS")
    print("=" * 70)
    if m.alpha_pct < 0:
        print("WARNING: this run underperformed simply buying and holding the asset over the same window.")
    if m.num_trades < 20:
        print(f"WARNING: only {m.num_trades} trades - not enough for the win rate/Sharpe above to be statistically meaningful.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", required=True, help="Historical OHLCV CSV (DatetimeIndex, Open/High/Low/Close/Volume columns)")
    parser.add_argument("--symbol", default="BTCINR")
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--warmup-bars", type=int, default=100)
    parser.add_argument("--decision-every", type=int, default=1, help="Run the committee every N bars (mirrors TICK_MINUTES vs bar frequency)")
    parser.add_argument("--trades-out", default=None, help="Optional CSV path to dump every individual trade")
    args = parser.parse_args()

    bars = pd.read_csv(args.csv, index_col=0, parse_dates=True)
    bars = bars[["Open", "High", "Low", "Close", "Volume"]].dropna()

    config = BacktestConfig(
        symbol=args.symbol, starting_capital_inr=args.capital,
        warmup_bars=args.warmup_bars, decision_every_n_bars=args.decision_every,
    )
    print(f"Replaying {len(bars)} bars for {args.symbol} ({bars.index.min()} .. {bars.index.max()})...")
    run = run_backtest(bars, config)
    _print_report(run)

    if args.trades_out:
        pd.DataFrame([t.__dict__ for t in run.trades]).to_csv(args.trades_out, index=False)
        print(f"Wrote {len(run.trades)} trades to {args.trades_out}")


if __name__ == "__main__":
    main()
