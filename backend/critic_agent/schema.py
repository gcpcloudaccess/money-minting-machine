from __future__ import annotations

from dataclasses import dataclass
from typing import Any


REQUIRED_FIELDS = {
    "symbol",
    "action",
    "confidence",
    "model_probability_up",
    "entry",
    "stop_loss",
    "take_profit",
    "position_size_pct",
    "shares",
    "notional",
    "capital_at_risk",
    "risk_reward",
    "review_status",
    "policy_check",
    "model_metrics",
    "rationale",
}


@dataclass(frozen=True)
class SchemaIssue:
    severity: str
    message: str


def validate_recommendation_shape(payload: dict[str, Any]) -> list[SchemaIssue]:
    issues: list[SchemaIssue] = []
    missing = sorted(REQUIRED_FIELDS - set(payload))
    for field in missing:
        issues.append(SchemaIssue("critical", f"Missing required field: {field}."))

    action = payload.get("action")
    if action is not None and action not in {"BUY", "SELL", "HOLD"}:
        issues.append(SchemaIssue("critical", f"Invalid action: {action}."))

    for field in ("confidence", "model_probability_up", "entry", "position_size_pct", "risk_reward"):
        if field in payload and not _is_number(payload[field]):
            issues.append(SchemaIssue("critical", f"Field must be numeric: {field}."))

    metrics = payload.get("model_metrics")
    if isinstance(metrics, dict):
        for field in ("accuracy", "baseline_accuracy", "precision", "recall", "samples"):
            if field not in metrics:
                issues.append(SchemaIssue("critical", f"Missing model metric: {field}."))
    elif "model_metrics" in payload:
        issues.append(SchemaIssue("critical", "model_metrics must be an object."))

    policy = payload.get("policy_check")
    if isinstance(policy, dict):
        if "passed" not in policy or "reasons" not in policy:
            issues.append(SchemaIssue("critical", "policy_check must include passed and reasons."))
    elif "policy_check" in payload:
        issues.append(SchemaIssue("critical", "policy_check must be an object."))

    return issues


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
