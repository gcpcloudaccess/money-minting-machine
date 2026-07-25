"""Backtest engine: replays historical OHLCV bars through the REAL production
decision pipeline (not a reimplementation) and simulates a portfolio against
it, so the resulting metrics (app/backtest/metrics.py) reflect what the live
system would actually have decided, not an approximation of it.

Reused as-is from app/: TechnicalAnalyst, RiskAnalyst, AlgoSignalAnalyst,
DebateAgent, all 4 critics, and trust_weighted_consensus.compute_consensus -
the exact same classes/functions app/orchestration/session_runner.py calls
live. position_sizing.size_position and trading/costs.compute_costs (the
CRYPTO_INDIA profile) are reused the same way for realistic sizing and fees.

Deliberately EXCLUDED from this backtest, with reasons (see BACKTEST_ANALYSTS
below): Macro/Sentiment/Geopolitical/Government Policy/Fundamental/
Astrological analysts. Every one of those either fetches LIVE news/company
data (fetching TODAY's headlines to "explain" a bar from 3 months ago is not
a valid historical reconstruction - it's not look-ahead bias in the strict
sense of seeing future prices, but it IS feeding unrelated, wrong-period
context into the vote) or doesn't meaningfully apply to a cryptocurrency
(Fundamental Analyst's financial-statement analysis, Astrological Analyst).
This means the backtest measures the price/risk/model-driven CORE of the
committee, not the full 9-analyst intraday roster - a narrower but honestly
answerable question, rather than a wider one silently corrupted by feeding
every network-dependent agent permanently-empty or mistimed data.

IMPORTANT CAVEAT (read before trusting any output): the reliability tracker's
trust scores are all held at the neutral 0.5 prior for this entire backtest -
there is no historical trust data to bootstrap from. Live trading trust
scores drift as trades close (see app/consensus/reliability_tracker.py), so
live behavior will diverge from this backtest as the system accumulates a
real track record - in either direction.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import pandas as pd

from app.agents.analysts.algo_signal import AlgoSignalAnalyst
from app.agents.analysts.risk import RiskAnalyst
from app.agents.analysts.technical import TechnicalAnalyst
from app.agents.base import AnalysisContext
from app.agents.critics import ALL_CRITICS
from app.agents.debate_agent import DebateAgent
from app.backtest.metrics import BacktestMetrics, Trade, compute_metrics
from app.consensus.trust_weighted_consensus import compute_consensus
from app.portfolio import position_sizing
from app.trading import costs as costs_module

# See module docstring for why this is narrower than app.agents.analysts.ALL_ANALYSTS.
BACKTEST_ANALYST_TIER = [TechnicalAnalyst, RiskAnalyst, AlgoSignalAnalyst]

NEUTRAL_TRUST_SCORES = {
    "Technical Analyst": 0.5, "Risk Assessment Analyst": 0.5, "Algo Signal Analyst": 0.5,
    "Debate Agent": 0.5, "Risk Critic": 0.5, "Profit Critic": 0.5, "Macro Critic": 0.5, "Opportunity Critic": 0.5,
}

MIN_BARS_FOR_DAILY_TREND = 80  # TechnicalAnalyst's/RiskAnalyst's vendored daily-bar models need this much history
DEFAULT_WARMUP_BARS = 100


@dataclass
class BacktestConfig:
    symbol: str = "BTCINR"
    starting_capital_inr: float = 100_000.0
    exchange_code: str = "CRYPTO_INDIA"
    warmup_bars: int = DEFAULT_WARMUP_BARS
    decision_every_n_bars: int = 1  # 1 = decide on every bar; raise to mirror TICK_MINUTES vs bar frequency
    intraday_window: int = 200  # how many trailing bars each decision's ctx.bars sees, matching get_recent_bars' default
    allow_fractional: bool = True  # crypto is fractional-quantity tradable, unlike NSE whole shares


@dataclass
class BacktestRun:
    metrics: BacktestMetrics
    trades: list[Trade]
    equity_curve: list[tuple[str, float]]
    benchmark_equity_curve: list[tuple[str, float]]
    decisions: list[dict] = field(default_factory=list)


def _daily_resample(bars: pd.DataFrame) -> pd.DataFrame:
    return bars.resample("1D").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()


def _run_committee(ctx: AnalysisContext) -> tuple[list, list]:
    """Runs BACKTEST_ANALYST_TIER -> Debate Agent -> all 4 Critics, exactly
    the vote-production part of app/agents/debate_loop.run_debate(), just
    without the excluded analyst tiers (see module docstring) and without the
    ThreadPoolExecutor concurrency (unnecessary for a single-symbol replay)."""
    analyst_votes = [cls().vote(ctx) for cls in BACKTEST_ANALYST_TIER]
    debate_vote = DebateAgent().vote(ctx, analyst_votes)
    critic_votes = [cls().vote(ctx, analyst_votes + [debate_vote]) for cls in ALL_CRITICS]
    return analyst_votes, debate_vote, critic_votes


def _infer_periods_per_year(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return 252.0
    median_gap = pd.Series(index).diff().dropna().median()
    seconds = median_gap.total_seconds() if median_gap else 86400.0
    if seconds <= 0:
        return 252.0
    return (365.25 * 24 * 3600) / seconds  # crypto trades every day of the year, not just NSE's ~252 trading days


def run_backtest(bars: pd.DataFrame, config: BacktestConfig | None = None) -> BacktestRun:
    """bars: full historical OHLCV history for `config.symbol`, ascending
    DatetimeIndex, columns Open/High/Low/Close/Volume - the same shape
    app/data/market_data.py / app/data/crypto_data.py already produce, so a
    CSV of real CoinDCX candles (see scripts/fetch_backtest_data.py) drops in
    directly with no reshaping."""
    config = config or BacktestConfig()
    if len(bars) <= config.warmup_bars + 1:
        raise ValueError(f"Need more than {config.warmup_bars} bars (warmup) to run a backtest - got {len(bars)}.")

    cash = config.starting_capital_inr
    position_qty = 0.0
    position_avg_price = 0.0
    trades: list[Trade] = []
    equity_curve: list[tuple[str, float]] = []
    decisions: list[dict] = []

    bench_qty = None  # set on the first bar we actually evaluate, so the benchmark starts at the same point the strategy does
    benchmark_equity_curve: list[tuple[str, float]] = []

    for i in range(config.warmup_bars, len(bars)):
        ts = bars.index[i]
        price = float(bars["Close"].iloc[i])

        if bench_qty is None:
            bench_qty = config.starting_capital_inr / price  # buy-and-hold benchmark, entered once, at the same starting point

        # Mark-to-market equity every bar, even on bars we don't run the committee on
        # (decision_every_n_bars), so the equity curve/Sharpe/drawdown reflect real
        # intra-period price movement, not a staircase that only moves on decision bars.
        equity_curve.append((str(ts), round(cash + position_qty * price, 2)))
        benchmark_equity_curve.append((str(ts), round(bench_qty * price, 2)))

        if (i - config.warmup_bars) % config.decision_every_n_bars != 0:
            continue

        window_start = max(0, i - config.intraday_window)
        intraday_bars = bars.iloc[window_start:i]
        daily_bars = _daily_resample(bars.iloc[: i + 1])

        open_positions = (
            [{"symbol": config.symbol, "weight": position_qty * position_avg_price, "sector": None}] if position_qty > 0 else []
        )

        ctx = AnalysisContext(
            symbol=config.symbol, bars=intraday_bars, fundamentals={}, symbol_news=[], market_news=[],
            daily_bars=daily_bars, benchmark_bars=daily_bars, open_positions=open_positions,
            financial_statements={}, historical_context=[], peer_bars={config.symbol: intraday_bars},
        )

        try:
            analyst_votes, debate_vote, critic_votes = _run_committee(ctx)
        except Exception as exc:  # a single bad bar (e.g. degenerate data) shouldn't kill the whole backtest
            decisions.append({"timestamp": str(ts), "error": str(exc)})
            continue

        all_votes = analyst_votes + [debate_vote] + critic_votes
        consensus = compute_consensus(all_votes, NEUTRAL_TRUST_SCORES, mode="intraday")

        risk_vote = next((v for v in analyst_votes if v.agent_name == "Risk Assessment Analyst"), None)
        risk_level = (risk_vote.metrics.get("risk_level") if risk_vote else None) or "MEDIUM"

        decisions.append({
            "timestamp": str(ts), "price": price, "verdict": consensus.verdict,
            "directional_confidence": consensus.directional_confidence,
        })

        verdict = consensus.verdict
        if verdict in ("BUY", "SWITCH") and position_qty == 0:
            open_exposure = 0.0
            sizing = position_sizing.size_position(
                consensus.directional_confidence, risk_level, price, open_exposure, cash,
                allow_fractional=config.allow_fractional,
            )
            qty = sizing["quantity"]
            if qty and qty > 0:
                fees = costs_module.compute_costs("BUY", qty, price, exchange=config.exchange_code)
                cash -= qty * price + fees["total"]
                position_qty = qty
                position_avg_price = price

        elif verdict in ("SELL", "SWITCH") and position_qty > 0:
            fees = costs_module.compute_costs("SELL", position_qty, price, exchange=config.exchange_code)
            gross = position_qty * price
            proceeds = gross - fees["total"]
            pnl = proceeds - (position_qty * position_avg_price)
            trades.append(Trade(
                entry_time="", exit_time=str(ts), entry_price=position_avg_price, exit_price=price,
                quantity=position_qty, pnl_after_costs=round(pnl, 2), total_costs=fees["total"],
            ))
            cash += proceeds
            position_qty = 0.0
            position_avg_price = 0.0

    # Force-close any still-open position at the final bar's price, same as
    # session_runner.py's end-of-session force_close_all - an unrealized
    # position shouldn't just vanish from the P&L calculation.
    if position_qty > 0:
        final_price = float(bars["Close"].iloc[-1])
        fees = costs_module.compute_costs("SELL", position_qty, final_price, exchange=config.exchange_code)
        proceeds = position_qty * final_price - fees["total"]
        pnl = proceeds - (position_qty * position_avg_price)
        trades.append(Trade(
            entry_time="", exit_time=str(bars.index[-1]), entry_price=position_avg_price, exit_price=final_price,
            quantity=position_qty, pnl_after_costs=round(pnl, 2), total_costs=fees["total"],
        ))
        cash += proceeds
        equity_curve[-1] = (equity_curve[-1][0], round(cash, 2))

    elapsed_days = (bars.index[-1] - bars.index[config.warmup_bars]).total_seconds() / 86400.0
    periods_per_year = _infer_periods_per_year(bars.index[config.warmup_bars:])

    metrics = compute_metrics(
        equity_curve=[v for _, v in equity_curve],
        trades=trades,
        benchmark_equity_curve=[v for _, v in benchmark_equity_curve],
        periods_per_year=periods_per_year,
        elapsed_days=max(elapsed_days, 1.0),
    )

    return BacktestRun(metrics=metrics, trades=trades, equity_curve=equity_curve, benchmark_equity_curve=benchmark_equity_curve, decisions=decisions)
