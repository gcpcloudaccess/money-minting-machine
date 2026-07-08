from __future__ import annotations

import argparse
import json

from .agent import TechnicalAnalystAgent
from .data import generate_demo_prices, load_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="TechnicalAnalyst agent for RSI, EMA, MACD, and volume confidence scoring.")
    parser.add_argument("--symbol", default="DEMO", help="Ticker label for the analysis output.")
    parser.add_argument("--csv", help="Path to OHLCV CSV with date, open, high, low, close, volume columns.")
    parser.add_argument("--demo", action="store_true", help="Use generated demo OHLCV data.")
    args = parser.parse_args()

    bars = generate_demo_prices() if args.demo or not args.csv else load_csv(args.csv)
    result = TechnicalAnalystAgent().analyze(bars, symbol=args.symbol)
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
