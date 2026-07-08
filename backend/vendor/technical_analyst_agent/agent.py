from __future__ import annotations

from dataclasses import asdict, dataclass

from .data import PriceBar
from .indicators import clamp, ema_series, macd_series, mean, rsi_series, safe_ratio, stdev


@dataclass(frozen=True)
class IndicatorSnapshot:
    date: str
    close: float
    rsi_14: float
    ema_12: float
    ema_26: float
    ema_50: float
    ema_200: float
    macd: float
    macd_signal: float
    macd_histogram: float
    volume_ratio_20: float
    volume_trend_5_vs_20: float


@dataclass(frozen=True)
class SignalScore:
    name: str
    score: float
    confidence: float
    weight: float
    evidence: str


@dataclass(frozen=True)
class TechnicalAnalysisResult:
    agent: str
    symbol: str
    action: str
    directional_score: float
    confidence_score: float
    conviction_score: float
    label: str
    latest: IndicatorSnapshot
    signals: list[SignalScore]
    risk_flags: list[str]
    rationale: list[str]
    data_quality_notes: list[str]
    disclaimer: str = "Research output only. Not financial advice or an execution instruction."

    def to_dict(self) -> dict:
        return asdict(self)


class TechnicalAnalystAgent:
    """Rules-based technical analyst using RSI, EMA, MACD, and volume evidence."""

    SIGNAL_WEIGHTS = {
        "RSI Momentum": 0.22,
        "EMA Trend Structure": 0.30,
        "MACD Momentum": 0.28,
        "Volume Confirmation": 0.20,
    }

    def __init__(self, name: str = "Diverse Financial Agent - TechnicalAnalyst"):
        self.name = name

    def analyze(self, bars: list[PriceBar], symbol: str = "UNKNOWN") -> TechnicalAnalysisResult:
        if len(bars) < 80:
            raise ValueError("Need at least 80 price bars for technical analysis.")

        snapshot = self._snapshot(bars)
        signals = [
            self._score_rsi(snapshot),
            self._score_ema(snapshot),
            self._score_macd(bars, snapshot),
            self._score_volume(bars, snapshot),
        ]
        directional = sum(signal.score * signal.weight for signal in signals)
        confidence = self._overall_confidence(bars, signals)
        conviction = clamp((directional * 0.62) + (confidence * 0.38))
        action = self._action(directional, confidence)

        return TechnicalAnalysisResult(
            agent=self.name,
            symbol=symbol.upper(),
            action=action,
            directional_score=round(directional, 2),
            confidence_score=round(confidence, 2),
            conviction_score=round(conviction, 2),
            label=self._label(directional, confidence),
            latest=snapshot,
            signals=signals,
            risk_flags=self._risk_flags(bars, snapshot, directional, confidence),
            rationale=self._rationale(action, directional, confidence, signals),
            data_quality_notes=self._data_quality_notes(bars),
        )

    def _snapshot(self, bars: list[PriceBar]) -> IndicatorSnapshot:
        closes = [bar.close for bar in bars]
        volumes = [bar.volume for bar in bars]
        rsi = rsi_series(closes, 14)
        ema_12 = ema_series(closes, 12)
        ema_26 = ema_series(closes, 26)
        ema_50 = ema_series(closes, 50)
        ema_200 = ema_series(closes, 200)
        macd, macd_signal, macd_hist = macd_series(closes)
        latest = bars[-1]

        return IndicatorSnapshot(
            date=latest.date,
            close=round(latest.close, 4),
            rsi_14=round(float(rsi[-1] or 50.0), 4),
            ema_12=round(ema_12[-1], 4),
            ema_26=round(ema_26[-1], 4),
            ema_50=round(ema_50[-1], 4),
            ema_200=round(ema_200[-1], 4),
            macd=round(macd[-1], 6),
            macd_signal=round(macd_signal[-1], 6),
            macd_histogram=round(macd_hist[-1], 6),
            volume_ratio_20=round(safe_ratio(volumes[-1], mean(volumes[-20:])) - 1.0, 6),
            volume_trend_5_vs_20=round(safe_ratio(mean(volumes[-5:]), mean(volumes[-20:])) - 1.0, 6),
        )

    def _score_rsi(self, snapshot: IndicatorSnapshot) -> SignalScore:
        rsi = snapshot.rsi_14
        if 45 <= rsi <= 60:
            score = 62 + (rsi - 45) * 1.05
            evidence = f"RSI is balanced-to-constructive at {rsi:.1f}."
        elif 60 < rsi <= 70:
            score = 78 + (rsi - 60) * 0.9
            evidence = f"RSI confirms strong momentum at {rsi:.1f} without extreme overbought pressure."
        elif rsi > 70:
            score = 82 - min(28, (rsi - 70) * 1.8)
            evidence = f"RSI is overbought at {rsi:.1f}; momentum exists but reversal risk rises."
        elif 30 <= rsi < 45:
            score = 44 + (rsi - 30) * 1.15
            evidence = f"RSI is weak-to-recovering at {rsi:.1f}."
        else:
            score = 24 + rsi * 0.5
            evidence = f"RSI is oversold at {rsi:.1f}; falling momentum dominates until reversal confirms."

        confidence = 88 if 25 <= rsi <= 75 else 74
        return SignalScore("RSI Momentum", round(clamp(score), 2), confidence, self.SIGNAL_WEIGHTS["RSI Momentum"], evidence)

    def _score_ema(self, snapshot: IndicatorSnapshot) -> SignalScore:
        close = snapshot.close
        stacked_bull = close > snapshot.ema_12 > snapshot.ema_26 > snapshot.ema_50
        stacked_bear = close < snapshot.ema_12 < snapshot.ema_26 < snapshot.ema_50
        long_trend = safe_ratio(close - snapshot.ema_200, snapshot.ema_200)
        short_spread = safe_ratio(snapshot.ema_12 - snapshot.ema_26, snapshot.ema_26)
        medium_spread = safe_ratio(snapshot.ema_50 - snapshot.ema_200, snapshot.ema_200)

        score = 50 + clamp(short_spread * 950, -22, 22) + clamp(long_trend * 180, -18, 18) + clamp(medium_spread * 120, -12, 12)
        if stacked_bull:
            score += 12
        if stacked_bear:
            score -= 12

        evidence = (
            f"Close is {long_trend:.2%} from EMA200; EMA12/EMA26 spread is {short_spread:.2%}; "
            f"EMA50/EMA200 spread is {medium_spread:.2%}."
        )
        confidence = 92 if len(str(snapshot.ema_200)) > 0 else 70
        return SignalScore("EMA Trend Structure", round(clamp(score), 2), confidence, self.SIGNAL_WEIGHTS["EMA Trend Structure"], evidence)

    def _score_macd(self, bars: list[PriceBar], snapshot: IndicatorSnapshot) -> SignalScore:
        closes = [bar.close for bar in bars]
        _, _, hist = macd_series(closes)
        hist_slope = hist[-1] - hist[-4] if len(hist) >= 4 else 0.0
        normalized_hist = safe_ratio(snapshot.macd_histogram, snapshot.close)
        normalized_slope = safe_ratio(hist_slope, snapshot.close)

        score = 50 + clamp(normalized_hist * 7000, -24, 24) + clamp(normalized_slope * 9000, -18, 18)
        if snapshot.macd > snapshot.macd_signal:
            score += 8
        else:
            score -= 8

        evidence = (
            f"MACD is {'above' if snapshot.macd > snapshot.macd_signal else 'below'} signal; "
            f"histogram is {snapshot.macd_histogram:.4f} with 3-bar slope {hist_slope:.4f}."
        )
        confidence = 86 if abs(normalized_hist) > 0.0004 or abs(normalized_slope) > 0.0002 else 70
        return SignalScore("MACD Momentum", round(clamp(score), 2), confidence, self.SIGNAL_WEIGHTS["MACD Momentum"], evidence)

    def _score_volume(self, bars: list[PriceBar], snapshot: IndicatorSnapshot) -> SignalScore:
        close_change_5 = safe_ratio(bars[-1].close - bars[-6].close, bars[-6].close)
        volume_boost = snapshot.volume_ratio_20
        volume_trend = snapshot.volume_trend_5_vs_20
        score = 50

        if close_change_5 > 0:
            score += clamp(volume_boost * 36, -10, 18) + clamp(volume_trend * 30, -8, 14)
            evidence = f"Price rose {close_change_5:.2%} over 5 bars with volume {volume_boost:.2%} versus its 20-bar average."
        elif close_change_5 < 0:
            score -= clamp(volume_boost * 34, -10, 20)
            score += clamp(volume_trend * 18, -10, 8)
            evidence = f"Price fell {abs(close_change_5):.2%} over 5 bars; current volume is {volume_boost:.2%} versus average."
        else:
            evidence = f"Price is flat over 5 bars; current volume is {volume_boost:.2%} versus average."

        confidence = 90 if min(bar.volume for bar in bars[-20:]) > 0 else 35
        return SignalScore("Volume Confirmation", round(clamp(score), 2), confidence, self.SIGNAL_WEIGHTS["Volume Confirmation"], evidence)

    def _overall_confidence(self, bars: list[PriceBar], signals: list[SignalScore]) -> float:
        signal_confidence = sum(signal.confidence * signal.weight for signal in signals)
        history_score = clamp((len(bars) - 80) / 120 * 100)
        volume_validity = 100 if min(bar.volume for bar in bars[-50:]) > 0 else 35
        volatility_score = self._volatility_confidence(bars)
        return clamp((signal_confidence * 0.48) + (history_score * 0.22) + (volume_validity * 0.16) + (volatility_score * 0.14))

    def _volatility_confidence(self, bars: list[PriceBar]) -> float:
        closes = [bar.close for bar in bars]
        returns = [safe_ratio(closes[index] - closes[index - 1], closes[index - 1]) for index in range(len(closes) - 20, len(closes))]
        annualized = stdev(returns) * (252 ** 0.5)
        if annualized <= 0.18:
            return 88
        if annualized <= 0.35:
            return 78
        if annualized <= 0.55:
            return 62
        return 44

    def _action(self, directional: float, confidence: float) -> str:
        if confidence < 45:
            return "HOLD"
        if directional >= 66:
            return "BUY"
        if directional <= 34:
            return "SELL"
        return "HOLD"

    def _label(self, directional: float, confidence: float) -> str:
        if confidence < 45:
            return "Low Confidence"
        if directional >= 76:
            return "High-Conviction Bullish"
        if directional >= 61:
            return "Bullish"
        if directional <= 24:
            return "High-Conviction Bearish"
        if directional <= 39:
            return "Bearish"
        return "Mixed / Neutral"

    def _risk_flags(self, bars: list[PriceBar], snapshot: IndicatorSnapshot, directional: float, confidence: float) -> list[str]:
        flags: list[str] = []
        if snapshot.rsi_14 >= 72:
            flags.append("RSI overbought: upside momentum may be crowded.")
        if snapshot.rsi_14 <= 28:
            flags.append("RSI oversold: downside momentum may be stretched.")
        if abs(snapshot.volume_ratio_20) < 0.05 and directional >= 66:
            flags.append("Bullish score lacks strong volume expansion.")
        if snapshot.close < snapshot.ema_200 and directional >= 58:
            flags.append("Short-term signal conflicts with price below EMA200.")
        if confidence < 60:
            flags.append("Confidence is below preferred threshold; wait for cleaner confirmation.")
        ranges = [safe_ratio(bar.high - bar.low, bar.close) for bar in bars[-20:]]
        if mean(ranges) > 0.045:
            flags.append("Wide recent ranges suggest elevated execution and stop-loss risk.")
        return flags or ["No major technical risk flag triggered by the configured rules."]

    def _rationale(self, action: str, directional: float, confidence: float, signals: list[SignalScore]) -> list[str]:
        ordered = sorted(signals, key=lambda signal: abs(signal.score - 50), reverse=True)
        return [
            f"Action is {action} because the weighted directional score is {directional:.2f}/100 and confidence is {confidence:.2f}/100.",
            f"Strongest technical driver: {ordered[0].name} at {ordered[0].score:.2f}/100.",
            f"Weakest or most cautious driver: {ordered[-1].name} at {ordered[-1].score:.2f}/100.",
        ]

    def _data_quality_notes(self, bars: list[PriceBar]) -> list[str]:
        notes: list[str] = []
        if len(bars) < 200:
            notes.append("Less than 200 bars supplied; EMA200 is available but still warming up.")
        if any(bar.volume <= 0 for bar in bars[-50:]):
            notes.append("Recent zero or negative volume values reduce volume-signal reliability.")
        if bars[-1].date <= bars[-2].date:
            notes.append("Latest bar ordering should be checked; dates are expected to be strictly increasing.")
        return notes or ["OHLCV coverage is adequate for RSI, EMA, MACD, and volume scoring."]


def analyze(bars: list[PriceBar], symbol: str = "UNKNOWN") -> TechnicalAnalysisResult:
    return TechnicalAnalystAgent().analyze(bars, symbol=symbol)
