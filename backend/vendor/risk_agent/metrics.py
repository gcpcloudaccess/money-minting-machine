"""Financial risk metric calculations.

The functions in this module intentionally use plain Python sequences instead
of dataframe-specific APIs. That keeps the agent portable and makes every
calculation explicit for audit and consensus logs.
"""

from __future__ import annotations

import math
from statistics import mean, pstdev

from risk_agent.models import OHLCVBar, PortfolioPosition, RiskMetrics

TRADING_DAYS_PER_YEAR = 252


def closes(bars: list[OHLCVBar]) -> list[float]:
    return [bar.close for bar in bars if bar.close > 0]


def volumes(bars: list[OHLCVBar]) -> list[float]:
    return [bar.volume for bar in bars if bar.volume >= 0]


def returns_from_prices(prices: list[float]) -> list[float]:
    """Convert prices to simple percentage returns."""

    return [(prices[i] / prices[i - 1]) - 1.0 for i in range(1, len(prices)) if prices[i - 1] > 0]


def annualized_volatility(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    return pstdev(returns) * math.sqrt(TRADING_DAYS_PER_YEAR)


def beta(asset_returns: list[float], benchmark_returns: list[float]) -> float:
    n = min(len(asset_returns), len(benchmark_returns))
    if n < 2:
        return 1.0
    asset = asset_returns[-n:]
    benchmark = benchmark_returns[-n:]
    benchmark_mean = mean(benchmark)
    asset_mean = mean(asset)
    variance = sum((value - benchmark_mean) ** 2 for value in benchmark) / n
    if variance == 0:
        return 1.0
    covariance = sum((asset[i] - asset_mean) * (benchmark[i] - benchmark_mean) for i in range(n)) / n
    return covariance / variance


def max_drawdown(prices: list[float]) -> float:
    """Return the worst peak-to-trough loss as a negative number."""

    if not prices:
        return 0.0
    peak = prices[0]
    worst = 0.0
    for price in prices:
        peak = max(peak, price)
        drawdown = (price / peak) - 1.0 if peak else 0.0
        worst = min(worst, drawdown)
    return worst


def percentile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = probability * (len(sorted_values) - 1)
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return sorted_values[int(index)]
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def value_at_risk(returns: list[float], confidence: float = 0.95) -> float:
    """Historical VaR at the loss tail, represented as a return."""

    if not returns:
        return 0.0
    return percentile(sorted(returns), 1.0 - confidence)


def conditional_value_at_risk(returns: list[float], confidence: float = 0.95) -> float:
    if not returns:
        return 0.0
    var = value_at_risk(returns, confidence)
    tail = [value for value in returns if value <= var]
    return mean(tail) if tail else var


def sharpe_ratio(returns: list[float], risk_free_rate: float) -> float:
    if len(returns) < 2:
        return 0.0
    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    excess = [value - daily_rf for value in returns]
    vol = pstdev(excess)
    if vol == 0:
        return 0.0
    return (mean(excess) / vol) * math.sqrt(TRADING_DAYS_PER_YEAR)


def downside_deviation(returns: list[float], risk_free_rate: float) -> float:
    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    downside = [min(0.0, value - daily_rf) for value in returns]
    if not downside:
        return 0.0
    return math.sqrt(mean([value * value for value in downside])) * math.sqrt(TRADING_DAYS_PER_YEAR)


def sortino_ratio(returns: list[float], risk_free_rate: float) -> float:
    if not returns:
        return 0.0
    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    downside = downside_deviation(returns, risk_free_rate) / math.sqrt(TRADING_DAYS_PER_YEAR)
    if downside == 0:
        return 0.0
    return ((mean(returns) - daily_rf) / downside) * math.sqrt(TRADING_DAYS_PER_YEAR)


def liquidity_risk(price_data: list[OHLCVBar]) -> float:
    """Estimate liquidity risk from trading volume stability and absolute volume.

    The output is normalized to 0..1, where 1 means high liquidity risk.
    """

    values = volumes(price_data)
    if not values:
        return 1.0
    avg_volume = mean(values)
    volume_cv = pstdev(values) / avg_volume if avg_volume > 0 and len(values) > 1 else 0.0
    low_volume_penalty = max(0.0, min(1.0, (100_000 - avg_volume) / 100_000))
    instability_penalty = max(0.0, min(1.0, volume_cv / 2.0))
    return round((0.65 * low_volume_penalty) + (0.35 * instability_penalty), 4)


def concentration_risk(portfolio: list[PortfolioPosition]) -> float:
    """Herfindahl-Hirschman style concentration score normalized to 0..1."""

    if not portfolio:
        return 0.5
    total_weight = sum(abs(position.weight) for position in portfolio)
    if total_weight == 0:
        return 0.5
    normalized = [abs(position.weight) / total_weight for position in portfolio]
    return min(1.0, sum(weight * weight for weight in normalized))


def sector_exposure_risk(portfolio: list[PortfolioPosition]) -> float:
    if not portfolio:
        return 0.5
    sector_weights: dict[str, float] = {}
    total_weight = sum(abs(position.weight) for position in portfolio)
    if total_weight == 0:
        return 0.5
    for position in portfolio:
        sector = position.sector or "UNKNOWN"
        sector_weights[sector] = sector_weights.get(sector, 0.0) + abs(position.weight) / total_weight
    return min(1.0, max(sector_weights.values()))


def correlation_risk(asset_returns: list[float], benchmark_returns: list[float]) -> float:
    n = min(len(asset_returns), len(benchmark_returns))
    if n < 2:
        return 0.5
    asset = asset_returns[-n:]
    benchmark = benchmark_returns[-n:]
    asset_std = pstdev(asset)
    benchmark_std = pstdev(benchmark)
    if asset_std == 0 or benchmark_std == 0:
        return 0.5
    covariance = sum((asset[i] - mean(asset)) * (benchmark[i] - mean(benchmark)) for i in range(n)) / n
    correlation = covariance / (asset_std * benchmark_std)
    return max(0.0, min(1.0, abs(correlation)))


def market_regime_risk(asset_returns: list[float], benchmark_returns: list[float]) -> float:
    """Estimate stress risk from benchmark trend and volatility."""

    if len(benchmark_returns) < 20:
        return 0.5
    recent = benchmark_returns[-20:]
    recent_return = sum(recent)
    recent_vol = annualized_volatility(recent)
    trend_penalty = max(0.0, min(1.0, -recent_return / 0.08))
    volatility_penalty = max(0.0, min(1.0, (recent_vol - 0.18) / 0.35))
    asset_stress = max(0.0, min(1.0, -sum(asset_returns[-20:]) / 0.12)) if len(asset_returns) >= 20 else 0.0
    return round((0.45 * trend_penalty) + (0.35 * volatility_penalty) + (0.20 * asset_stress), 4)


def sentiment_risk(news_sentiment: dict[str, float]) -> float:
    if not news_sentiment:
        return 0.0
    values = list(news_sentiment.values())
    avg = mean(values)
    return max(0.0, min(1.0, (0.2 - avg) / 1.2))


def macro_risk(macro_indicators: dict[str, float]) -> float:
    """Normalize optional macro stress indicators.

    Expected keys can include inflation, interest_rate_change, gdp_growth,
    currency_volatility, and policy_uncertainty. Missing values do not add risk.
    """

    if not macro_indicators:
        return 0.0
    inflation = max(0.0, min(1.0, (macro_indicators.get("inflation", 0.0) - 0.04) / 0.08))
    rates = max(0.0, min(1.0, macro_indicators.get("interest_rate_change", 0.0) / 0.03))
    gdp = max(0.0, min(1.0, (0.03 - macro_indicators.get("gdp_growth", 0.03)) / 0.05))
    currency = max(0.0, min(1.0, macro_indicators.get("currency_volatility", 0.0) / 0.12))
    policy = max(0.0, min(1.0, macro_indicators.get("policy_uncertainty", 0.0)))
    return round(mean([inflation, rates, gdp, currency, policy]), 4)


def calculate_metrics(
    price_data: list[OHLCVBar],
    benchmark_data: list[OHLCVBar],
    portfolio: list[PortfolioPosition],
    risk_free_rate: float,
    news_sentiment: dict[str, float],
    macro_indicators: dict[str, float],
) -> RiskMetrics:
    asset_prices = closes(price_data)
    benchmark_prices = closes(benchmark_data)
    asset_returns = returns_from_prices(asset_prices)
    benchmark_returns = returns_from_prices(benchmark_prices)

    sharpe = sharpe_ratio(asset_returns, risk_free_rate)
    sortino = sortino_ratio(asset_returns, risk_free_rate)
    downside = downside_deviation(asset_returns, risk_free_rate)

    return RiskMetrics(
        volatility=round(annualized_volatility(asset_returns), 4),
        beta=round(beta(asset_returns, benchmark_returns), 4),
        max_drawdown=round(max_drawdown(asset_prices), 4),
        var_95=round(value_at_risk(asset_returns), 4),
        cvar_95=round(conditional_value_at_risk(asset_returns), 4),
        sharpe_ratio=round(sharpe, 4),
        sortino_ratio=round(sortino, 4),
        downside_deviation=round(downside, 4),
        liquidity_risk=liquidity_risk(price_data),
        concentration_risk=round(concentration_risk(portfolio), 4),
        correlation_risk=round(correlation_risk(asset_returns, benchmark_returns), 4),
        sector_exposure_risk=round(sector_exposure_risk(portfolio), 4),
        risk_adjusted_return=round(sharpe, 4),
        market_regime_risk=market_regime_risk(asset_returns, benchmark_returns),
        sentiment_risk=round(sentiment_risk(news_sentiment), 4),
        macro_risk=macro_risk(macro_indicators),
    )
