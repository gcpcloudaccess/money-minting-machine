"""Command line entry point for the geopolitical analyst agent."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .agent import GeopoliticalAnalyst
from .models import Observation, Signal


def main() -> None:
    parser = argparse.ArgumentParser(description="Score geopolitical risk observations.")
    parser.add_argument("input", type=Path, help="JSON file containing an observations array.")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    observations = [_observation(item) for item in payload["observations"]]
    assessment = GeopoliticalAnalyst().assess(observations)
    print(json.dumps(_to_json(assessment), indent=2))


def _observation(item: dict[str, Any]) -> Observation:
    return Observation(
        region=item["region"],
        countries=list(item.get("countries", [])),
        signal=Signal(item["signal"]),
        source_reliability=float(item["source_reliability"]),
        intensity=float(item["intensity"]),
        market_relevance=float(item["market_relevance"]),
        recency_hours=float(item["recency_hours"]),
        evidence=item["evidence"],
        asset_classes=list(item.get("asset_classes", [])),
        corroboration_count=int(item.get("corroboration_count", 1)),
        novelty=float(item.get("novelty", 0.5)),
        escalation_velocity=float(item.get("escalation_velocity", 0.5)),
        policy_specificity=float(item.get("policy_specificity", 0.5)),
        metadata=dict(item.get("metadata", {})),
    )


def _to_json(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_json(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(_to_json(key)): _to_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_json(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


if __name__ == "__main__":
    main()

