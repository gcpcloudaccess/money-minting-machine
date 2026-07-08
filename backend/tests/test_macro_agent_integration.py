"""Tests for the vendored team macroeconomist_agent and its integration into
our MacroAnalyst - no network, no LLM key required."""

import datetime as dt

from app.agents.analysts.macro import MacroAnalyst, _regime_signal
from app.agents.base import AnalysisContext
from app.config import get_settings
from macroeconomist_agent import MacroeconomistAgent, MacroObservation


def test_vendored_agent_runs_standalone():
    result = MacroeconomistAgent().analyze([
        MacroObservation(name="gdp_growth", value=6.5, unit="pct", period="Q1", source="MOSPI", as_of="2026-06-01", recency_days=30, source_quality=0.85, revision_risk=0.3),
        MacroObservation(name="inflation", value=4.8, unit="pct", period="latest_month", source="MOSPI", as_of="2026-06-01", recency_days=20, source_quality=0.85, revision_risk=0.2),
        MacroObservation(name="policy_rate", value=6.5, unit="pct", period="current", source="RBI", as_of="2026-06-01", recency_days=20, source_quality=0.95, revision_risk=0.05),
    ])
    assert result.overall_confidence.score >= 0
    assert len(result.signals) == 3


def test_regime_signal_none_when_unconfigured(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.delenv("MACRO_GDP_GROWTH_PCT", raising=False)
    monkeypatch.delenv("MACRO_INFLATION_PCT", raising=False)
    monkeypatch.delenv("MACRO_POLICY_RATE_PCT", raising=False)
    assert _regime_signal() is None
    get_settings.cache_clear()


def test_regime_signal_active_when_configured(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("MACRO_GDP_GROWTH_PCT", "6.5")
    monkeypatch.setenv("MACRO_INFLATION_PCT", "4.8")
    monkeypatch.setenv("MACRO_POLICY_RATE_PCT", "6.5")
    monkeypatch.setenv("MACRO_DATA_AS_OF", dt.date.today().isoformat())

    signal = _regime_signal()
    assert signal is not None
    assert signal["action"] in ("BUY", "SELL", "HOLD")
    assert "regime_mix" in signal["metrics"]
    get_settings.cache_clear()


def test_macro_analyst_falls_back_without_config(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.delenv("MACRO_GDP_GROWTH_PCT", raising=False)
    monkeypatch.delenv("MACRO_INFLATION_PCT", raising=False)
    monkeypatch.delenv("MACRO_POLICY_RATE_PCT", raising=False)

    ctx = AnalysisContext(symbol="TCS.NS", bars=None, fundamentals={}, symbol_news=[], market_news=[])
    vote = MacroAnalyst().vote(ctx)
    assert vote.agent_name == "Macroeconomic Analyst"
    assert "regime_mix" not in vote.metrics
    get_settings.cache_clear()
