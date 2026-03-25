from __future__ import annotations

import json
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RULES_PATH = ROOT_DIR / "rules.yaml"

def _get_by_path(payload: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    return current


def _render_template(template: str, context: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        value = _get_by_path(context, key, "")
        return str(value)

    return re.sub(r"\{([^{}]+)\}", replace, template)


@lru_cache(maxsize=1)
def load_rule_config(rules_path: str | Path = DEFAULT_RULES_PATH) -> dict[str, Any]:
    path = Path(rules_path)
    if not path.exists():
        raise FileNotFoundError(f"Rule config not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _build_context(alert: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    txn = alert.get("transactions", {})
    thresholds = config.get("thresholds", {})
    profile_max_amounts = config.get("profile_max_amounts", {})
    defaults = config.get("defaults", {})

    transaction_count = txn.get("transaction_count", 0)
    total_amount = txn.get("total_amount", 0)
    time_window_days = max(txn.get("time_window_days", 1), 1)
    avg_amount = round(_safe_divide(total_amount, transaction_count), 2)

    reporting_threshold = thresholds.get("reporting_threshold", 0)
    lower_band = reporting_threshold * 0.7
    upper_band = reporting_threshold

    customer_profile = alert.get("customer_profile", "")
    expected_max = profile_max_amounts.get(customer_profile, defaults.get("expected_profile_max", 1000000))

    destination = str(txn.get("destination_country", "") or "").upper()
    pattern = str(alert.get("pattern", "") or "")

    return {
        "alert": alert,
        "customer": alert,
        "txn": txn,
        "thresholds": thresholds,
        "high_risk_countries": config.get("high_risk_countries", []),
        "derived": {
            "txn_per_day": round(_safe_divide(transaction_count, time_window_days), 2),
            "avg_amount": avg_amount,
            "lower_band": lower_band,
            "upper_band": upper_band,
            "expected_max": expected_max,
            "destination": destination,
            "pattern": pattern,
            "pattern_lower": pattern.lower(),
        },
    }


def _resolve_condition_value(condition: dict[str, Any], context: dict[str, Any], value_key: str, ref_key: str) -> Any:
    if value_key in condition:
        return condition[value_key]
    return _get_by_path(context, condition.get(ref_key, ""))


def _evaluate_condition(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    condition_type = condition.get("type")

    if condition_type in {"gt", "ge", "lt", "le", "eq", "ne"}:
        left = _get_by_path(context, condition["path"])
        right = _resolve_condition_value(condition, context, "value", "value_ref")
        if condition_type == "gt":
            return left > right
        if condition_type == "ge":
            return left >= right
        if condition_type == "lt":
            return left < right
        if condition_type == "le":
            return left <= right
        if condition_type == "eq":
            return left == right
        return left != right

    if condition_type == "between_exclusive":
        value = _get_by_path(context, condition["path"])
        lower = _resolve_condition_value(condition, context, "lower", "lower_ref")
        upper = _resolve_condition_value(condition, context, "upper", "upper_ref")
        return lower < value < upper

    if condition_type == "in_list":
        item = _get_by_path(context, condition["item_path"])
        values = _resolve_condition_value(condition, context, "values", "list_ref") or []
        return item in values

    if condition_type == "contains_substring":
        haystack = str(_get_by_path(context, condition["path"], ""))
        needle = str(_resolve_condition_value(condition, context, "substring", "substring_ref") or "")
        return needle in haystack

    if condition_type == "non_empty":
        value = _get_by_path(context, condition["path"], "")
        return bool(value)

    raise ValueError(f"Unsupported condition type: {condition_type}")


def _rule_matches(rule: dict[str, Any], context: dict[str, Any]) -> bool:
    all_conditions = rule.get("conditions", [])
    any_conditions = rule.get("any_conditions", [])

    if all_conditions and not all(_evaluate_condition(condition, context) for condition in all_conditions):
        return False
    if any_conditions and not any(_evaluate_condition(condition, context) for condition in any_conditions):
        return False
    return True


def _calculate_confidence(rule: dict[str, Any], context: dict[str, Any]) -> float:
    confidence = rule.get("confidence", 0.0)

    if isinstance(confidence, (int, float)):
        return round(float(confidence), 2)

    mode = confidence.get("mode", "fixed")
    if mode == "fixed":
        return round(float(confidence.get("value", 0.0)), 2)

    if mode == "scaled_cap":
        numerator = float(_get_by_path(context, confidence["numerator_path"], 0))
        denominator = float(_resolve_condition_value(confidence, context, "denominator", "denominator_ref") or 0)
        multiplier = float(confidence.get("multiplier", 1.0))
        cap = float(confidence.get("cap", 0.95))
        raw_confidence = _safe_divide(numerator, denominator) * multiplier
        return round(min(raw_confidence, cap), 2)

    raise ValueError(f"Unsupported confidence mode: {mode}")


def _build_evidence_block(rule: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    confidence = _calculate_confidence(rule, context)
    audit_reason = rule.get("audit_reason", {})

    threshold = _resolve_condition_value(audit_reason, context, "threshold", "threshold_ref")
    actual_value = _resolve_condition_value(audit_reason, context, "actual_value", "actual_value_ref")

    return {
        "rule_id": rule["id"],
        "rule_name": rule["name"],
        "confidence": confidence,
        "observation": _render_template(rule["observation_template"], context),
        "audit_reason": {
            "why_flagged": _render_template(audit_reason["why_flagged_template"], context),
            "regulation": audit_reason["regulation"],
            "threshold": threshold,
            "actual_value": actual_value,
        },
    }


# ════════════════════════════════════════════════════════
# RULE ENGINE
# ════════════════════════════════════════════════════════

def evaluate_rules(alert: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Evaluate alert payload against YAML-configured AML rules.
    Returns one evidence block per triggered rule.
    """
    config = load_rule_config()
    context = _build_context(alert, config)
    evidence_blocks: list[dict[str, Any]] = []

    for rule in config.get("rules", []):
        if _rule_matches(rule, context):
            evidence_blocks.append(_build_evidence_block(rule, context))

    return evidence_blocks


# ════════════════════════════════════════════════════════
# RISK SCORE CALCULATOR
# ════════════════════════════════════════════════════════

def calculate_risk_score(evidence_blocks: list[dict[str, Any]]) -> tuple[float, str]:
    if not evidence_blocks:
        return 0.0, "LOW"

    avg_score = round(sum(block["confidence"] for block in evidence_blocks) / len(evidence_blocks), 2)

    if avg_score >= 0.80:
        risk_level = "HIGH"
    elif avg_score >= 0.60:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return avg_score, risk_level


# ════════════════════════════════════════════════════════
# AUDIT TRAIL GENERATOR
# ════════════════════════════════════════════════════════

def generate_audit_trail(
    alert: dict[str, Any],
    evidence_blocks: list[dict[str, Any]],
    rag_query: str,
    retrieved_docs: list[dict[str, Any]],
    narrative_paragraphs: list[str],
) -> dict[str, Any]:
    risk_score, risk_level = calculate_risk_score(evidence_blocks)
    total_rules_evaluated = len(load_rule_config().get("rules", []))

    audit = {
        "step_1_input_received": {
            "alert_id": alert["alert_id"],
            "customer_id": alert["customer_id"],
            "alert_type": alert["alert_type"],
            "account_type": alert["account_type"],
            "customer_profile": alert["customer_profile"],
            "pattern": alert["pattern"],
            "timestamp": datetime.now().isoformat(),
            "transactions": {
                "count": alert["transactions"]["transaction_count"],
                "total_inr": alert["transactions"]["total_amount"],
                "days": alert["transactions"]["time_window_days"],
                "destination": alert["transactions"].get("destination_country"),
            },
        },
        "step_2_rules_fired": {
            "total_rules_evaluated": total_rules_evaluated,
            "total_rules_triggered": len(evidence_blocks),
            "rules": [
                {
                    "rule_id": block["rule_id"],
                    "rule_name": block["rule_name"],
                    "confidence": block["confidence"],
                    "observation": block["observation"],
                    "why_flagged": block["audit_reason"]["why_flagged"],
                    "threshold": block["audit_reason"]["threshold"],
                    "actual_value": block["audit_reason"]["actual_value"],
                    "regulation": block["audit_reason"]["regulation"],
                }
                for block in evidence_blocks
            ],
        },
        "step_3_rag_retrieval": {
            "query_used": rag_query,
            "documents_retrieved": retrieved_docs,
            "retrieval_timestamp": datetime.now().isoformat(),
        },
        "step_4_llm_generation": {
            "model_used": "mistral:7b",
            "temperature": 0.3,
            "prompt_version": "v1.0",
            "section_to_rule_mapping": {
                "paragraph_1_subject": ["AML-005", "AML-013"],
                "paragraph_2_transactions": ["AML-001", "AML-002", "AML-003", "AML-004"],
                "paragraph_3_suspicious": ["AML-006", "AML-007", "AML-008"],
                "paragraph_4_risk": "ALL_RULES",
            },
            "generated_narrative": {
                "paragraph_1_subject": narrative_paragraphs[0] if len(narrative_paragraphs) > 0 else "",
                "paragraph_2_transactions": narrative_paragraphs[1] if len(narrative_paragraphs) > 1 else "",
                "paragraph_3_suspicious": narrative_paragraphs[2] if len(narrative_paragraphs) > 2 else "",
                "paragraph_4_risk": narrative_paragraphs[3] if len(narrative_paragraphs) > 3 else "",
            },
        },
        "step_5_risk_assessment": {
            "overall_risk_score": risk_score,
            "risk_level": risk_level,
            "total_rules_fired": len(evidence_blocks),
            "highest_confidence_rule": max(evidence_blocks, key=lambda item: item["confidence"])["rule_name"]
            if evidence_blocks
            else "NONE",
        },
        "step_6_analyst_review": {
            "status": "PENDING",
            "analyst_id": None,
            "approved_at": None,
            "comments": None,
            "edits_made": None,
        },
    }

    filename = f"audit_{alert['alert_id']}.json"
    with open(filename, "w", encoding="utf-8") as handle:
        json.dump(audit, handle, indent=2)

    print(f"Audit trail saved -> {filename}")
    return audit


# ════════════════════════════════════════════════════════
# RAG QUERY BUILDER
# ════════════════════════════════════════════════════════

def build_rag_query(evidence_blocks: list[dict[str, Any]], alert: dict[str, Any]) -> str:
    rule_names = [block["rule_name"] for block in evidence_blocks]
    observations = [block["observation"] for block in evidence_blocks]

    return (
        f"SAR narrative for {', '.join(rule_names)} suspicious activity. "
        f"Pattern: {alert['pattern']}. "
        f"Observations: {'. '.join(observations)}. "
        f"Regulatory writing guideline and example SAR narrative for {alert['alert_type']}."
    )


if __name__ == "__main__":
    with open("../data/alert_case.json", "r", encoding="utf-8") as handle:
        test_alert = json.load(handle)

    fired_rules = evaluate_rules(test_alert)
    print(f"\n{'=' * 50}")
    print(f"Rules Fired: {len(fired_rules)}")
    for block in fired_rules:
        print(f"  - {block['rule_id']} | {block['rule_name']} | confidence: {block['confidence']}")

    query = build_rag_query(fired_rules, test_alert)
    print(f"\nRAG Query Built:\n{query}")

    score, level = calculate_risk_score(fired_rules)
    print(f"\nRisk Score: {score} -> {level}")

    result = generate_audit_trail(
        alert=test_alert,
        evidence_blocks=fired_rules,
        rag_query=query,
        retrieved_docs=[],
        narrative_paragraphs=[],
    )
    print("\nAudit Trail Generated")
    print(json.dumps(result["step_5_risk_assessment"], indent=2))
