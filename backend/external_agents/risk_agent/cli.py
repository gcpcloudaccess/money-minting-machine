"""CLI demo for the Risk Assessment Analyst Agent."""

from __future__ import annotations

import argparse
import json
import math
import random
from datetime import date, timedelta

from risk_agent.agent import RiskAssessmentAgent
from risk_agent.memory import DecisionMemory
from risk_agent.models import OHLCVBar, PortfolioPosition, RiskAssessmentInput


def synthetic_ohlcv(symbol_seed: int, start_price: float, days: int, drift: float, volatility: float) -> list[OHLCVBar]:
    """Create deterministic mock OHLCV data for demos and tests."""

    rng = random.Random(symbol_seed)
    bars: list[OHLCVBar] = []
    price = start_price
    start = date.today() - timedelta(days=days)
    for index in range(days):
        shock = rng.gauss(drift / 252, volatility / math.sqrt(252))
        open_price = price
        close = max(1.0, price * (1.0 + shock))
        high = max(open_price, close) * (1.0 + rng.uniform(0.0, 0.015))
        low = min(open_price, close) * (1.0 - rng.uniform(0.0, 0.015))
        volume = max(10_000, rng.gauss(450_000, 120_000))
        bars.append(
            OHLCVBar(
                date=(start + timedelta(days=index)).isoformat(),
                open=round(open_price, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close, 2),
                volume=round(volume),
            )
        )
        price = close
    return bars


def build_demo_request(symbol: str) -> RiskAssessmentInput:
    return RiskAssessmentInput(
        symbol=symbol,
        price_data=synthetic_ohlcv(symbol_seed=42, start_price=240.0, days=260, drift=0.09, volatility=0.34),
        benchmark_data=synthetic_ohlcv(symbol_seed=7, start_price=1000.0, days=260, drift=0.07, volatility=0.18),
        portfolio=[
            PortfolioPosition(symbol=symbol, weight=0.28, sector="Renewable Energy"),
            PortfolioPosition(symbol="TATA_POWER", weight=0.22, sector="Utilities"),
            PortfolioPosition(symbol="ADANI_GREEN", weight=0.18, sector="Renewable Energy"),
            PortfolioPosition(symbol="CASH", weight=0.32, sector="Cash"),
        ],
        fundamentals={"debt_to_equity": 1.2, "revenue_growth": 0.18},
        news_sentiment={"news": -0.15, "social": 0.05},
        macro_indicators={
            "inflation": 0.055,
            "interest_rate_change": 0.01,
            "gdp_growth": 0.035,
            "currency_volatility": 0.04,
            "policy_uncertainty": 0.35,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Risk Assessment Analyst Agent demo.")
    parser.add_argument("--symbol", default="NEXA", help="Symbol to assess.")
    parser.add_argument("--memory-file", default="", help="Optional JSON memory file.")
    args = parser.parse_args()

    memory = DecisionMemory(args.memory_file) if args.memory_file else DecisionMemory()
    agent = RiskAssessmentAgent(memory=memory)
    result = agent.assess(build_demo_request(args.symbol))
    print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    main()
