#!/usr/bin/env python3
"""
Fundamental Analyst Agent

Dependency-free CLI that scores a company from structured financial statement
data. It emphasizes revenue quality, revenue growth, balance sheet strength, and
high-resolution confidence scoring.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


QUALITY_WEIGHTS = {
    "Revenue Growth": 0.20,
    "Revenue Quality": 0.20,
    "Balance Sheet Strength": 0.25,
    "Profitability Support": 0.15,
    "Cash Conversion": 0.15,
    "Dilution And Capital Allocation": 0.05,
}

CONFIDENCE_WEIGHTS = {
    "Data Freshness": 0.25,
    "Statement Coverage": 0.25,
    "Audit And Reliability": 0.20,
    "Consistency": 0.20,
    "Disclosure Depth": 0.10,
}


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def get(data: Dict[str, Any], path: str, default: Optional[float] = None) -> Optional[float]:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous)


def rounded(value: Optional[float], digits: int = 1) -> Optional[float]:
    if value is None:
        return None
    return round(value, digits)


def score_revenue_growth(data: Dict[str, Any]) -> Dict[str, Any]:
    revenue = get(data, "income_statement.revenue")
    prior = get(data, "income_statement.revenue_prior_year")
    two_years_ago = get(data, "income_statement.revenue_two_years_ago")
    yoy = pct_change(revenue, prior)
    two_year = pct_change(prior, two_years_ago)

    if yoy is None:
        return score_item("Revenue Growth", 45, 45, "Revenue history is incomplete.", True)

    score = 55 + yoy * 140
    if two_year is not None:
        if yoy > 0 and two_year > 0:
            score += 8
        if abs(yoy - two_year) <= 0.08:
            score += 7
        if yoy < 0 or two_year < 0:
            score -= 15

    evidence = f"Revenue changed {yoy * 100:.1f}% year over year"
    if two_year is not None:
        evidence += f"; prior-year growth was {two_year * 100:.1f}%."
    else:
        evidence += "."

    return score_item("Revenue Growth", clamp(score), 82 if two_year is not None else 68, evidence, two_year is None)


def score_revenue_quality(data: Dict[str, Any]) -> Dict[str, Any]:
    recurring = get(data, "revenue_quality.recurring_revenue_percent")
    concentration = get(data, "revenue_quality.largest_customer_percent")
    deferred = get(data, "revenue_quality.deferred_revenue")
    deferred_prior = get(data, "revenue_quality.deferred_revenue_prior_year")
    segment_count = get(data, "revenue_quality.segment_count")
    retention = get(data, "revenue_quality.gross_retention_percent")
    gross_profit = get(data, "income_statement.gross_profit")
    revenue = get(data, "income_statement.revenue")

    score = 50
    signals = 0
    notes: List[str] = []

    if recurring is not None:
        signals += 1
        score += (recurring - 50) * 0.45
        notes.append(f"{recurring:.0f}% recurring revenue")
    if concentration is not None:
        signals += 1
        score += 12 if concentration <= 10 else -min(25, (concentration - 10) * 0.8)
        notes.append(f"largest customer is {concentration:.0f}% of revenue")
    if deferred is not None and deferred_prior is not None:
        signals += 1
        d_growth = pct_change(deferred, deferred_prior)
        if d_growth is not None:
            score += clamp(d_growth * 70, -12, 14)
            notes.append(f"deferred revenue changed {d_growth * 100:.1f}%")
    if segment_count is not None:
        signals += 1
        score += min(10, segment_count * 2)
        notes.append(f"{segment_count:.0f} reported segments")
    if retention is not None:
        signals += 1
        score += (retention - 85) * 0.55
        notes.append(f"{retention:.0f}% gross retention")
    margin = safe_div(gross_profit, revenue)
    if margin is not None:
        signals += 1
        score += (margin - 0.40) * 35
        notes.append(f"{margin * 100:.1f}% gross margin")

    missing = signals < 4
    confidence = 88 if signals >= 5 else 72 if signals >= 3 else 52
    evidence = "; ".join(notes) + "." if notes else "Revenue quality disclosures are limited."
    return score_item("Revenue Quality", clamp(score), confidence, evidence, missing)


def score_balance_sheet(data: Dict[str, Any]) -> Dict[str, Any]:
    cash = get(data, "balance_sheet.cash_and_equivalents")
    current_assets = get(data, "balance_sheet.current_assets")
    current_liabilities = get(data, "balance_sheet.current_liabilities")
    total_debt = get(data, "balance_sheet.total_debt")
    short_debt = get(data, "balance_sheet.short_term_debt")
    equity = get(data, "balance_sheet.shareholders_equity")
    goodwill = get(data, "balance_sheet.goodwill_and_intangibles")
    operating_income = get(data, "income_statement.operating_income")

    signals = 0
    score = 50
    notes: List[str] = []

    current_ratio = safe_div(current_assets, current_liabilities)
    net_debt = None if cash is None or total_debt is None else total_debt - cash
    debt_to_equity = safe_div(total_debt, equity)
    goodwill_to_equity = safe_div(goodwill, equity)
    interest_proxy = safe_div(operating_income, total_debt)
    short_debt_to_cash = safe_div(short_debt, cash)

    if current_ratio is not None:
        signals += 1
        score += clamp((current_ratio - 1.0) * 18, -18, 22)
        notes.append(f"{current_ratio:.2f} current ratio")
    if net_debt is not None:
        signals += 1
        score += 18 if net_debt <= 0 else -min(24, net_debt / max(cash or 1, 1) * 12)
        notes.append(f"net debt is {net_debt:.0f}")
    if debt_to_equity is not None:
        signals += 1
        score += 12 if debt_to_equity <= 0.35 else -min(22, (debt_to_equity - 0.35) * 35)
        notes.append(f"{debt_to_equity:.2f} debt-to-equity")
    if goodwill_to_equity is not None:
        signals += 1
        score += 6 if goodwill_to_equity <= 0.25 else -min(16, (goodwill_to_equity - 0.25) * 35)
        notes.append(f"{goodwill_to_equity:.2f} goodwill/intangibles-to-equity")
    if interest_proxy is not None:
        signals += 1
        score += clamp(interest_proxy * 12, -8, 14)
        notes.append(f"{interest_proxy:.2f} operating-income-to-debt proxy")
    if short_debt_to_cash is not None:
        signals += 1
        score += 8 if short_debt_to_cash <= 0.25 else -min(18, short_debt_to_cash * 15)
        notes.append(f"{short_debt_to_cash:.2f} short-term-debt-to-cash")

    missing = signals < 5
    confidence = 90 if signals >= 5 else 72 if signals >= 3 else 48
    evidence = "; ".join(notes) + "." if notes else "Balance sheet data is incomplete."
    return score_item("Balance Sheet Strength", clamp(score), confidence, evidence, missing)


def score_profitability(data: Dict[str, Any]) -> Dict[str, Any]:
    revenue = get(data, "income_statement.revenue")
    gross_profit = get(data, "income_statement.gross_profit")
    operating_income = get(data, "income_statement.operating_income")
    net_income = get(data, "income_statement.net_income")
    free_cash_flow = get(data, "cash_flow_statement.free_cash_flow")

    gross_margin = safe_div(gross_profit, revenue)
    operating_margin = safe_div(operating_income, revenue)
    net_margin = safe_div(net_income, revenue)
    fcf_margin = safe_div(free_cash_flow, revenue)

    margins = [m for m in [gross_margin, operating_margin, net_margin, fcf_margin] if m is not None]
    if not margins:
        return score_item("Profitability Support", 42, 40, "Profitability data is missing.", True)

    score = 45
    if gross_margin is not None:
        score += (gross_margin - 0.35) * 45
    if operating_margin is not None:
        score += operating_margin * 80
    if net_margin is not None:
        score += net_margin * 45
    if fcf_margin is not None:
        score += fcf_margin * 40

    notes = []
    if gross_margin is not None:
        notes.append(f"{gross_margin * 100:.1f}% gross margin")
    if operating_margin is not None:
        notes.append(f"{operating_margin * 100:.1f}% operating margin")
    if net_margin is not None:
        notes.append(f"{net_margin * 100:.1f}% net margin")
    if fcf_margin is not None:
        notes.append(f"{fcf_margin * 100:.1f}% free cash flow margin")

    return score_item("Profitability Support", clamp(score), 78 if len(margins) >= 3 else 60, "; ".join(notes) + ".", len(margins) < 3)


def score_cash_conversion(data: Dict[str, Any]) -> Dict[str, Any]:
    net_income = get(data, "income_statement.net_income")
    operating_cash_flow = get(data, "cash_flow_statement.operating_cash_flow")
    free_cash_flow = get(data, "cash_flow_statement.free_cash_flow")
    revenue = get(data, "income_statement.revenue")
    revenue_prior = get(data, "income_statement.revenue_prior_year")
    receivables = get(data, "balance_sheet.accounts_receivable")
    receivables_prior = get(data, "balance_sheet.accounts_receivable_prior_year")
    inventory = get(data, "balance_sheet.inventory")
    inventory_prior = get(data, "balance_sheet.inventory_prior_year")

    ocf_to_income = safe_div(operating_cash_flow, net_income)
    fcf_margin = safe_div(free_cash_flow, revenue)
    rev_growth = pct_change(revenue, revenue_prior)
    ar_growth = pct_change(receivables, receivables_prior)
    inv_growth = pct_change(inventory, inventory_prior)

    signals = 0
    score = 50
    notes: List[str] = []

    if ocf_to_income is not None:
        signals += 1
        score += clamp((ocf_to_income - 0.8) * 22, -18, 20)
        notes.append(f"{ocf_to_income:.2f} operating-cash-flow-to-net-income")
    if fcf_margin is not None:
        signals += 1
        score += fcf_margin * 90
        notes.append(f"{fcf_margin * 100:.1f}% free cash flow margin")
    if rev_growth is not None and ar_growth is not None:
        signals += 1
        score += 10 if ar_growth <= rev_growth + 0.05 else -min(22, (ar_growth - rev_growth) * 55)
        notes.append(f"receivables growth {ar_growth * 100:.1f}% versus revenue growth {rev_growth * 100:.1f}%")
    if rev_growth is not None and inv_growth is not None:
        signals += 1
        score += 8 if inv_growth <= rev_growth + 0.08 else -min(18, (inv_growth - rev_growth) * 45)
        notes.append(f"inventory growth {inv_growth * 100:.1f}%")

    return score_item("Cash Conversion", clamp(score), 82 if signals >= 3 else 58, "; ".join(notes) + "." if notes else "Cash conversion data is incomplete.", signals < 3)


def score_capital_allocation(data: Dict[str, Any]) -> Dict[str, Any]:
    shares = get(data, "capital_allocation.shares_outstanding")
    shares_prior = get(data, "capital_allocation.shares_outstanding_prior_year")
    buybacks = get(data, "capital_allocation.buybacks")
    acquisition_spend = get(data, "capital_allocation.acquisition_spend")
    free_cash_flow = get(data, "cash_flow_statement.free_cash_flow")
    debt = get(data, "balance_sheet.total_debt")
    equity = get(data, "balance_sheet.shareholders_equity")

    dilution = pct_change(shares, shares_prior)
    debt_to_equity = safe_div(debt, equity)
    acquisition_to_fcf = safe_div(acquisition_spend, free_cash_flow)

    score = 60
    signals = 0
    notes: List[str] = []

    if dilution is not None:
        signals += 1
        score += 10 if dilution <= 0 else -min(25, dilution * 250)
        notes.append(f"share count changed {dilution * 100:.1f}%")
    if buybacks is not None and free_cash_flow not in (None, 0):
        signals += 1
        score += 5 if buybacks <= free_cash_flow * 0.5 else -8
        notes.append(f"buybacks were {buybacks:.0f}")
    if debt_to_equity is not None:
        signals += 1
        score += 8 if debt_to_equity <= 0.4 else -10
        notes.append(f"{debt_to_equity:.2f} debt-to-equity")
    if acquisition_to_fcf is not None:
        signals += 1
        score += 4 if acquisition_to_fcf <= 0.5 else -10
        notes.append(f"acquisition spend was {acquisition_to_fcf:.2f}x free cash flow")

    return score_item("Dilution And Capital Allocation", clamp(score), 76 if signals >= 3 else 55, "; ".join(notes) + "." if notes else "Capital allocation data is limited.", signals < 3)


def score_item(category: str, score: float, confidence: float, evidence: str, missing_data_penalty: bool) -> Dict[str, Any]:
    return {
        "category": category,
        "score": round(clamp(score), 1),
        "confidence": round(clamp(confidence), 1),
        "evidence": evidence,
        "missing_data_penalty": bool(missing_data_penalty),
    }


def confidence_components(data: Dict[str, Any]) -> Dict[str, float]:
    filing_date = parse_date(str(data.get("filing_date", "")))
    if filing_date is None:
        freshness = 45
    else:
        age_days = (date.today() - filing_date).days
        if age_days <= 120:
            freshness = 96
        elif age_days <= 240:
            freshness = 86
        elif age_days <= 420:
            freshness = 68
        elif age_days <= 730:
            freshness = 48
        else:
            freshness = 30

    coverage_label = str(get(data, "data_notes.statement_coverage", "")).lower()
    if coverage_label == "three_primary_statements":
        coverage = 88
    elif coverage_label == "income_and_balance_sheet":
        coverage = 62
    elif coverage_label == "partial":
        coverage = 38
    else:
        has_income = isinstance(data.get("income_statement"), dict)
        has_balance = isinstance(data.get("balance_sheet"), dict)
        has_cash = isinstance(data.get("cash_flow_statement"), dict)
        coverage = 88 if has_income and has_balance and has_cash else 62 if has_income and has_balance else 35

    audited = bool(data.get("audited"))
    warning = bool(data.get("restatement_or_going_concern_warning"))
    reliability = 94 if audited and not warning else 62 if not warning else 35

    consistency_label = str(get(data, "data_notes.consistency", "")).lower()
    consistency_map = {
        "figures_reconcile": 94,
        "minor_rounding_differences": 84,
        "unexplained_inconsistencies": 52,
        "material_conflicts": 28,
    }
    consistency = consistency_map.get(consistency_label, 70)

    disclosure_label = str(get(data, "data_notes.disclosure_depth", "")).lower()
    disclosure_map = {
        "full": 94,
        "useful_but_incomplete": 78,
        "limited": 52,
        "opaque": 30,
    }
    disclosure = disclosure_map.get(disclosure_label, 62)

    return {
        "Data Freshness": freshness,
        "Statement Coverage": coverage,
        "Audit And Reliability": reliability,
        "Consistency": consistency,
        "Disclosure Depth": disclosure,
    }


def parse_date(value: str) -> Optional[date]:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def weighted_average(values: Dict[str, float], weights: Dict[str, float]) -> float:
    return sum(values[key] * weights[key] for key in weights)


def confidence_cap(data: Dict[str, Any]) -> Tuple[float, List[str]]:
    caps = [100.0]
    reasons: List[str] = []
    if not isinstance(data.get("balance_sheet"), dict):
        caps.append(75)
        reasons.append("balance sheet missing")
    if get(data, "income_statement.revenue") is None:
        caps.append(65)
        reasons.append("revenue missing")
    if str(get(data, "data_notes.statement_coverage", "")).lower() == "summary_only":
        caps.append(60)
        reasons.append("only summary metrics available")
    if str(get(data, "data_notes.consistency", "")).lower() == "material_conflicts":
        caps.append(55)
        reasons.append("material statement inconsistency")
    if bool(data.get("restatement_or_going_concern_warning")):
        caps.append(50)
        reasons.append("restatement or going-concern warning")
    return min(caps), reasons


def final_view(score: float, confidence: float) -> str:
    if confidence < 45:
        return "Insufficient Data"
    if score >= 85:
        return "Fundamentally Excellent"
    if score >= 72:
        return "Fundamentally Strong"
    if score >= 55:
        return "Fundamentally Mixed"
    if score >= 35:
        return "Fundamentally Weak"
    return "Financially Distressed"


def risk_flags(data: Dict[str, Any]) -> List[Dict[str, str]]:
    risks: List[Dict[str, str]] = []
    revenue = get(data, "income_statement.revenue")
    revenue_prior = get(data, "income_statement.revenue_prior_year")
    rev_growth = pct_change(revenue, revenue_prior)
    ar_growth = pct_change(get(data, "balance_sheet.accounts_receivable"), get(data, "balance_sheet.accounts_receivable_prior_year"))
    inv_growth = pct_change(get(data, "balance_sheet.inventory"), get(data, "balance_sheet.inventory_prior_year"))
    debt = get(data, "balance_sheet.total_debt")
    cash = get(data, "balance_sheet.cash_and_equivalents")
    current_assets = get(data, "balance_sheet.current_assets")
    current_liabilities = get(data, "balance_sheet.current_liabilities")
    goodwill = get(data, "balance_sheet.goodwill_and_intangibles")
    equity = get(data, "balance_sheet.shareholders_equity")
    fcf = get(data, "cash_flow_statement.free_cash_flow")
    concentration = get(data, "revenue_quality.largest_customer_percent")
    shares = get(data, "capital_allocation.shares_outstanding")
    shares_prior = get(data, "capital_allocation.shares_outstanding_prior_year")

    if rev_growth is not None and ar_growth is not None and ar_growth > rev_growth + 0.10:
        risks.append({"risk": "Receivables outpacing revenue", "severity": "High" if ar_growth > rev_growth + 0.25 else "Medium", "evidence": f"Receivables grew {ar_growth * 100:.1f}% while revenue grew {rev_growth * 100:.1f}%."})
    if rev_growth is not None and inv_growth is not None and inv_growth > rev_growth + 0.15:
        risks.append({"risk": "Inventory growth above revenue growth", "severity": "Medium", "evidence": f"Inventory grew {inv_growth * 100:.1f}% versus revenue growth of {rev_growth * 100:.1f}%."})
    if debt is not None and cash is not None and debt > cash * 2:
        risks.append({"risk": "Elevated debt versus cash", "severity": "Medium", "evidence": f"Debt of {debt:.0f} is more than 2x cash of {cash:.0f}."})
    if current_assets is not None and current_liabilities is not None and current_assets < current_liabilities:
        risks.append({"risk": "Negative working capital", "severity": "High", "evidence": "Current liabilities exceed current assets."})
    goodwill_to_equity = safe_div(goodwill, equity)
    if goodwill_to_equity is not None and goodwill_to_equity > 0.50:
        risks.append({"risk": "Large goodwill and intangibles", "severity": "Medium", "evidence": f"Goodwill and intangibles are {goodwill_to_equity:.2f}x equity."})
    if fcf is not None and fcf < 0:
        risks.append({"risk": "Negative free cash flow", "severity": "High", "evidence": f"Free cash flow is {fcf:.0f}."})
    if concentration is not None and concentration > 20:
        risks.append({"risk": "High customer concentration", "severity": "High", "evidence": f"Largest customer represents {concentration:.0f}% of revenue."})
    dilution = pct_change(shares, shares_prior)
    if dilution is not None and dilution > 0.05:
        risks.append({"risk": "Shareholder dilution", "severity": "Medium", "evidence": f"Share count increased {dilution * 100:.1f}%."})
    if bool(data.get("restatement_or_going_concern_warning")):
        risks.append({"risk": "Accounting or solvency warning", "severity": "Critical", "evidence": "Input data marks a restatement or going-concern warning."})

    return risks


def analyze(data: Dict[str, Any]) -> Dict[str, Any]:
    category_scores = [
        score_revenue_growth(data),
        score_revenue_quality(data),
        score_balance_sheet(data),
        score_profitability(data),
        score_cash_conversion(data),
        score_capital_allocation(data),
    ]
    score_map = {item["category"]: item["score"] for item in category_scores}
    composite = weighted_average(score_map, QUALITY_WEIGHTS)

    components = confidence_components(data)
    raw_confidence = weighted_average(components, CONFIDENCE_WEIGHTS)
    cap, cap_reasons = confidence_cap(data)
    overall_confidence = min(raw_confidence, cap)

    sorted_strengths = sorted(category_scores, key=lambda item: item["score"], reverse=True)[:3]
    sorted_concerns = sorted(category_scores, key=lambda item: item["score"])[:3]

    return {
        "company_name": data.get("company_name", "Unknown Company"),
        "ticker": data.get("ticker", "N/A"),
        "reporting_period": data.get("reporting_period", "Unknown Period"),
        "filing_date": data.get("filing_date", "Unknown Filing Date"),
        "final_view": final_view(composite, overall_confidence),
        "composite_fundamental_quality_score": round(composite, 1),
        "overall_confidence_score": round(overall_confidence, 1),
        "confidence_components": {key: round(value, 1) for key, value in components.items()},
        "confidence_cap_reasons": cap_reasons,
        "category_scores": category_scores,
        "risk_flags": risk_flags(data),
        "top_strengths": [f"{item['category']}: {item['score']}/100" for item in sorted_strengths],
        "top_concerns": [f"{item['category']}: {item['score']}/100" for item in sorted_concerns],
        "data_needed_to_improve_confidence": data_needed(data),
    }


def data_needed(data: Dict[str, Any]) -> List[str]:
    needed = []
    if not isinstance(data.get("cash_flow_statement"), dict):
        needed.append("Cash flow statement")
    if not isinstance(data.get("revenue_quality"), dict):
        needed.append("Recurring revenue, customer concentration, and segment revenue disclosures")
    if get(data, "balance_sheet.short_term_debt") is None:
        needed.append("Debt maturity schedule and short-term debt details")
    if get(data, "balance_sheet.accounts_receivable_prior_year") is None:
        needed.append("Prior-year working capital balances")
    if get(data, "capital_allocation.shares_outstanding_prior_year") is None:
        needed.append("Share count history")
    if not needed:
        needed.append("More granular segment revenue and debt maturity disclosures")
    return needed


def render_markdown(result: Dict[str, Any]) -> str:
    risks = result["risk_flags"]
    risk_rows = "\n".join(
        f"| {risk['risk']} | {risk['severity']} | {risk['evidence']} |" for risk in risks
    ) or "| None flagged | Low | No major rule-based risk flags triggered. |"
    score_rows = "\n".join(
        f"| {item['category']} | {item['score']:.1f} | {item['confidence']:.1f} | {'Yes' if item['missing_data_penalty'] else 'No'} | {item['evidence']} |"
        for item in result["category_scores"]
    )
    confidence_rows = "\n".join(
        f"| {key} | {value:.1f} |" for key, value in result["confidence_components"].items()
    )
    caps = ", ".join(result["confidence_cap_reasons"]) or "None"
    strengths = "\n".join(f"- {item}" for item in result["top_strengths"])
    concerns = "\n".join(f"- {item}" for item in result["top_concerns"])
    data_needed_lines = "\n".join(f"- {item}" for item in result["data_needed_to_improve_confidence"])

    return f"""# Fundamental Analyst Report: {result['company_name']} ({result['ticker']})

## Executive View

Final View: **{result['final_view']}**

Composite Fundamental Quality Score: **{result['composite_fundamental_quality_score']:.1f}/100**

Overall Confidence Score: **{result['overall_confidence_score']:.1f}/100**

Reporting Period: **{result['reporting_period']}**

Filing Date: **{result['filing_date']}**

## Financial Quality Scorecard

| Category | Score | Confidence | Missing Data Penalty | Evidence |
|---|---:|---:|---|---|
{score_rows}

## Confidence Breakdown

| Component | Score |
|---|---:|
{confidence_rows}

Confidence caps applied: {caps}

## Risk Flags

| Risk | Severity | Evidence |
|---|---|---|
{risk_rows}

## Top Strengths

{strengths}

## Top Concerns

{concerns}

## Data That Would Improve Confidence

{data_needed_lines}

## Analyst View

The company receives a {result['final_view']} rating based on the weighted quality score and the confidence-adjusted reliability of the input data. The model separates business quality from confidence, so strong fundamentals can still be marked down when disclosures are incomplete or stale.
"""


def render_html(markdown: str, result: Dict[str, Any]) -> str:
    body = markdown_to_simple_html(markdown)
    accent = "#1f7a5a"
    score = result["composite_fundamental_quality_score"]
    confidence = result["overall_confidence_score"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fundamental Analyst Report</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17201c;
      --muted: #5d6b65;
      --line: #d9e0dc;
      --surface: #ffffff;
      --band: #f4f7f5;
      --accent: {accent};
      --warn: #9c5b10;
    }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: var(--band);
      line-height: 1.5;
    }}
    .shell {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 28px 18px 56px;
    }}
    .topbar {{
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 12px;
      align-items: center;
      margin-bottom: 16px;
    }}
    .brand {{
      font-size: 14px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0;
      font-weight: 700;
    }}
    .metric {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 14px;
      min-width: 150px;
    }}
    .metric strong {{
      display: block;
      font-size: 22px;
      color: var(--accent);
    }}
    main {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 28px;
      overflow-x: auto;
    }}
    h1 {{
      margin: 0 0 18px;
      font-size: 30px;
      line-height: 1.2;
    }}
    h2 {{
      margin-top: 30px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
      font-size: 19px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 14px 0;
      font-size: 14px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      text-align: left;
      padding: 10px 8px;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-weight: 700;
      background: #f9fbfa;
    }}
    p, li {{
      color: var(--ink);
    }}
    strong {{
      color: var(--accent);
    }}
    @media (max-width: 720px) {{
      .topbar {{
        grid-template-columns: 1fr;
      }}
      main {{
        padding: 18px;
      }}
      h1 {{
        font-size: 24px;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="topbar">
      <div class="brand">Fundamental Analyst Agent</div>
      <div class="metric">Quality Score<strong>{score:.1f}</strong></div>
      <div class="metric">Confidence<strong>{confidence:.1f}</strong></div>
    </div>
    <main>{body}</main>
  </div>
</body>
</html>
"""


def markdown_to_simple_html(markdown: str) -> str:
    html: List[str] = []
    in_ul = False
    in_table = False
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            if in_ul:
                html.append("</ul>")
                in_ul = False
            continue
        if line.startswith("# "):
            html.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_ul:
                html.append("</ul>")
                in_ul = False
            if in_table:
                html.append("</tbody></table>")
                in_table = False
            html.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("|") and line.endswith("|"):
            cells = [inline(cell.strip()) for cell in line.strip("|").split("|")]
            if all(set(cell.replace(":", "").replace("-", "")) == set() for cell in cells):
                continue
            if not in_table:
                html.append("<table><tbody>")
                in_table = True
                tag = "th"
            else:
                tag = "td"
            row = "".join(f"<{tag}>{cell}</{tag}>" for cell in cells)
            html.append(f"<tr>{row}</tr>")
        elif line.startswith("- "):
            if in_table:
                html.append("</tbody></table>")
                in_table = False
            if not in_ul:
                html.append("<ul>")
                in_ul = True
            html.append(f"<li>{inline(line[2:])}</li>")
        else:
            if in_ul:
                html.append("</ul>")
                in_ul = False
            if in_table:
                html.append("</tbody></table>")
                in_table = False
            html.append(f"<p>{inline(line)}</p>")
    if in_ul:
        html.append("</ul>")
    if in_table:
        html.append("</tbody></table>")
    return "\n".join(html)


def inline(text: str) -> str:
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    parts = escaped.split("**")
    for index in range(1, len(parts), 2):
        parts[index] = f"<strong>{parts[index]}</strong>"
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Fundamental Analyst agent on a company financials JSON file.")
    parser.add_argument("input", type=Path, help="Path to company financials JSON")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional path for structured JSON result")
    parser.add_argument("--md-out", type=Path, default=None, help="Optional path for Markdown report")
    parser.add_argument("--html-out", type=Path, default=None, help="Optional path for HTML report")
    args = parser.parse_args()

    with args.input.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    result = analyze(data)
    markdown = render_markdown(result)

    if args.json_out:
        args.json_out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.md_out:
        args.md_out.write_text(markdown, encoding="utf-8")
    if args.html_out:
        args.html_out.write_text(render_html(markdown, result), encoding="utf-8")

    print(markdown)


if __name__ == "__main__":
    main()
