"""Tests for the vendored team geopolitical_analyst engine and its
integration into our GeopoliticalAnalyst - no network, no LLM key required
(LLM calls are stubbed for the extraction-parsing tests)."""

import app.agents.analysts.geopolitical as geo_module
from app.agents.analysts.geopolitical import GeopoliticalAnalyst, _extract_observations
from app.agents.base import AnalysisContext
from geopolitical_analyst import GeopoliticalAnalyst as GeoEngine
from geopolitical_analyst import Observation, Signal


class _StubLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def chat(self, system, user, max_tokens=500, fallback=None):
        self.calls += 1
        return self.response


def test_vendored_engine_runs_standalone():
    obs = [Observation(region="Red Sea", countries=["YEM"], signal=Signal.CONFLICT, source_reliability=0.8, intensity=0.7, market_relevance=0.6, recency_hours=3, evidence="test")]
    result = GeoEngine().assess(obs)
    assert result.overall_score >= 0
    assert result.recommendation is not None


def test_extract_observations_parses_valid_json():
    llm = _StubLLM('[{"region": "Red Sea", "countries": ["YEM", "USA"], "signal": "conflict", '
                    '"intensity": 0.7, "market_relevance": 0.5, "source_reliability": 0.8, '
                    '"recency_hours": 4, "evidence": "missile strike"}]')
    observations = _extract_observations("RELIANCE.NS", [{"title": "Red Sea missile strike"}], llm)
    assert len(observations) == 1
    assert observations[0].signal == Signal.CONFLICT
    assert observations[0].countries == ["YEM", "USA"]


def test_extract_observations_handles_markdown_fenced_json():
    llm = _StubLLM('```json\n[{"region": "Gulf", "countries": ["IRN"], "signal": "sanctions", '
                    '"intensity": 0.5, "market_relevance": 0.3, "source_reliability": 0.6, '
                    '"recency_hours": 10, "evidence": "new sanctions"}]\n```')
    observations = _extract_observations("TCS.NS", [{"title": "New sanctions on Iran"}], llm)
    assert len(observations) == 1
    assert observations[0].signal == Signal.SANCTIONS


def test_extract_observations_degrades_gracefully_on_malformed_json():
    llm = _StubLLM("not valid json at all")
    observations = _extract_observations("TCS.NS", [{"title": "Some headline"}], llm)
    assert observations == []


def test_extract_observations_empty_news_skips_llm_call():
    llm = _StubLLM("[]")
    observations = _extract_observations("TCS.NS", [], llm)
    assert observations == []
    assert llm.calls == 0


def test_geopolitical_analyst_no_news_is_low_confidence_hold():
    ctx = AnalysisContext(symbol="TCS.NS", bars=None, fundamentals={}, symbol_news=[], market_news=[])
    vote = GeopoliticalAnalyst().vote(ctx)
    assert vote.action == "HOLD"
    assert vote.confidence <= 0.2
    assert vote.metrics["n_observations"] == 0


def test_geopolitical_analyst_full_pipeline_with_stubbed_llm(monkeypatch):
    llm = _StubLLM('[{"region": "Red Sea", "countries": ["YEM"], "signal": "conflict", '
                    '"intensity": 0.85, "market_relevance": 0.7, "source_reliability": 0.8, '
                    '"recency_hours": 2, "evidence": "escalation reported"}]')
    monkeypatch.setattr(geo_module, "get_llm_client", lambda: llm)

    ctx = AnalysisContext(
        symbol="RELIANCE.NS", bars=None, fundamentals={}, symbol_news=[],
        market_news=[{"title": "Red Sea conflict escalates", "tags": ["geopolitical"]}],
    )
    vote = GeopoliticalAnalyst().vote(ctx)
    assert vote.agent_name == "Geopolitical Analyst"
    assert vote.metrics["n_observations"] == 1
    assert vote.action in ("BUY", "SELL", "HOLD", "WAIT")
