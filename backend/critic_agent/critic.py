from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .schema import validate_recommendation_shape


@dataclass(frozen=True)
class Finding:
    severity: str
    category: str
    message: str


@dataclass(frozen=True)
class Critique:
    symbol: str
    verdict: str
    score: int
    findings: list[Finding]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "verdict": self.verdict,
            "score": self.score,
            "findings": [asdict(finding) for finding in self.findings],
            "summary": self.summary,
        }


def review_recommendation(payload: dict[str, Any]) -> Critique:
    findings: list[Finding] = []
    for issue in validate_recommendation_shape(payload):
        findings.append(Finding(issue.severity, "schema", issue.message))

    if any(finding.severity == "critical" for finding in findings):
        return _build_result(payload, findings)

    _review_policy(payload, findings)
    _review_model_evidence(payload, findings)
    _review_trade_geometry(payload, findings)
    _review_consistency(payload, findings)
    _review_explainability(payload, findings)
    return _build_result(payload, findings)


def _review_policy(payload: dict[str, Any], findings: list[Finding]) -> None:
    policy = payload["policy_check"]
    if payload["review_status"] != "APPROVED_FOR_REVIEW":
        findings.append(
            Finding(
                "critical",
                "policy",
                "Recommendation is not approved by the upstream policy gate.",
            )
        )
    if not policy.get("passed", False):
        reasons = policy.get("reasons", [])
        detail = "; ".join(str(reason) for reason in reasons) or "No reason supplied."
        findings.append(Finding("critical", "policy", f"Policy gate failed: {detail}"))


def _review_model_evidence(payload: dict[str, Any], findings: list[Finding]) -> None:
    metrics = payload["model_metrics"]
    accuracy = float(metrics["accuracy"])
    baseline = float(metrics["baseline_accuracy"])
    edge = accuracy - baseline
    samples = int(metrics["samples"])
    confidence = float(payload["confidence"])

    if samples < 60:
        findings.append(Finding("high", "model", f"Validation sample is thin: {samples} rows."))
    if edge < 0.02:
        findings.append(Finding("critical", "model", f"Model edge over baseline is weak: {edge:.2%}."))
    elif edge < 0.05:
        findings.append(Finding("medium", "model", f"Model edge is modest: {edge:.2%}."))
    if confidence < 0.58 and payload["action"] != "HOLD":
        findings.append(Finding("high", "model", f"Directional confidence is low: {confidence:.2f}."))


def _review_trade_geometry(payload: dict[str, Any], findings: list[Finding]) -> None:
    action = payload["action"]
    entry = float(payload["entry"])
    stop = float(payload["stop_loss"])
    target = float(payload["take_profit"])
    risk_reward = float(payload["risk_reward"])
    position_pct = float(payload["position_size_pct"])
    capital_at_risk = float(payload["capital_at_risk"])

    if action == "BUY" and not (stop < entry < target):
        findings.append(Finding("critical", "risk", "BUY trade levels must satisfy stop < entry < target."))
    if action == "SELL" and not (target < entry < stop):
        findings.append(Finding("critical", "risk", "SELL trade levels must satisfy target < entry < stop."))
    if action == "HOLD" and (position_pct > 0 or int(payload["shares"]) > 0):
        findings.append(Finding("critical", "risk", "HOLD recommendation should not allocate a position."))
    if action != "HOLD" and risk_reward < 1.5:
        findings.append(Finding("high", "risk", f"Risk/reward is too low: {risk_reward:.2f}."))
    if position_pct > 10.0:
        findings.append(Finding("high", "risk", f"Position size is aggressive: {position_pct:.2f}% of capital."))
    if capital_at_risk <= 0 and action != "HOLD":
        findings.append(Finding("critical", "risk", "Directional trade has no capital-at-risk estimate."))


def _review_consistency(payload: dict[str, Any], findings: list[Finding]) -> None:
    probability = float(payload["model_probability_up"])
    action = payload["action"]
    if action == "BUY" and probability < 0.55:
        findings.append(Finding("critical", "consistency", "BUY conflicts with low probability of an up move."))
    if action == "SELL" and probability > 0.45:
        findings.append(Finding("critical", "consistency", "SELL conflicts with high probability of an up move."))
    if action == "HOLD" and abs(probability - 0.5) > 0.2:
        findings.append(Finding("medium", "consistency", "HOLD has a strong model probability; check trend or policy blockers."))


def _review_explainability(payload: dict[str, Any], findings: list[Finding]) -> None:
    rationale = payload.get("rationale", [])
    top_features = payload.get("top_features", [])
    if not isinstance(rationale, list) or len(rationale) < 2:
        findings.append(Finding("medium", "explainability", "Rationale is too thin for review."))
    if not isinstance(top_features, list) or len(top_features) < 3:
        findings.append(Finding("medium", "explainability", "Top feature contributions are missing or sparse."))


def _build_result(payload: dict[str, Any], findings: list[Finding]) -> Critique:
    score = 100
    for finding in findings:
        if finding.severity == "critical":
            score -= 35
        elif finding.severity == "high":
            score -= 20
        elif finding.severity == "medium":
            score -= 10
        else:
            score -= 4
    score = max(0, score)

    if any(finding.severity == "critical" for finding in findings):
        verdict = "REJECT"
    elif any(finding.severity == "high" for finding in findings) or score < 75:
        verdict = "CAUTION"
    else:
        verdict = "PASS"

    if verdict == "PASS":
        summary = "Recommendation passed critic review for human consideration."
    elif verdict == "CAUTION":
        summary = "Recommendation has concerns that should be resolved before trading."
    else:
        summary = "Recommendation should not be traded without addressing critical issues."

    return Critique(
        symbol=str(payload.get("symbol", "UNKNOWN")),
        verdict=verdict,
        score=score,
        findings=findings,
        summary=summary,
    )
