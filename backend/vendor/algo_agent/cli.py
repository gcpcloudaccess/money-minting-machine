from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .agent import recommend
from .backtest import backtest
from .data import PriceBar, generate_demo_prices, load_csv, load_stooq
from .policy import TradePolicy


def main() -> None:
    parser = argparse.ArgumentParser(description="ML trade recommendation research agent.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("recommend", "backtest"):
        command = subparsers.add_parser(name)
        command.add_argument("--symbol", default="DEMO", help="Ticker label, or Stooq symbol with --source stooq.")
        command.add_argument("--csv", help="Path to OHLCV CSV.")
        command.add_argument("--source", choices=["csv", "stooq", "demo"], default="demo")
        command.add_argument("--demo", action="store_true", help="Use generated demo prices.")
        command.add_argument("--horizon", type=int, default=5, help="Forecast horizon in bars.")
        command.add_argument("--capital", type=float, default=100_000.0, help="Account capital for sizing.")
        command.add_argument("--risk-pct", type=float, default=0.5, help="Account risk percent per trade.")
        command.add_argument("--max-position-pct", type=float, default=8.0, help="Maximum notional position percent.")
        command.add_argument("--min-accuracy-edge", type=float, default=0.03, help="Required validation edge over baseline.")
        command.add_argument("--min-dollar-volume", type=float, default=2_000_000.0, help="Required average dollar volume.")

    args = parser.parse_args()
    bars = _load_bars(args)

    if args.command == "recommend":
        policy = TradePolicy(
            capital=args.capital,
            account_risk_pct=args.risk_pct,
            max_position_pct=args.max_position_pct,
            min_accuracy_edge=args.min_accuracy_edge,
            min_avg_dollar_volume=args.min_dollar_volume,
        )
        result = recommend(bars, symbol=args.symbol, horizon=args.horizon, policy=policy)
        print(json.dumps(result.to_dict(), indent=2))
    elif args.command == "backtest":
        result = backtest(bars, horizon=args.horizon)
        print(json.dumps(asdict(result), indent=2))


def _load_bars(args: argparse.Namespace) -> list[PriceBar]:
    if args.demo or args.source == "demo":
        return generate_demo_prices()
    if args.csv or args.source == "csv":
        if not args.csv:
            raise SystemExit("--csv is required when --source csv is used.")
        return load_csv(args.csv)
    if args.source == "stooq":
        return load_stooq(args.symbol)
    raise SystemExit("Unknown data source.")


if __name__ == "__main__":
    main()
