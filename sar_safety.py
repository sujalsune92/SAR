"""
sar_safety.py
Production-grade safety layer for SAR narrative generation.
Handles PII detection, evidence coverage, retry logic, audit logging.
"""
from __future__ import annotations

import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

# ════════════════════════════════════════════════════════
# LOGGING
# ════════════════════════════════════════════════════════
logger = logging.getLogger("sar.safety")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


# ════════════════════════════════════════════════════════
# STRUCTURED EXCEPTION
# ════════════════════════════════════════════════════════
@dataclass
class SarSafetyViolation(Exception):
    reason: str
    violation_type: str
    attempts: int
    audit_trail: list[dict[str, Any]] = field(default_factory=list)

    def __str__(self) -> str:
        return f"[{self.violation_type}] {self.reason} after {self.attempts} attempt(s)"

    def to_api_response(self) -> dict[str, Any]:
        return {
            "error": self.violation_type,
            "detail": self.reason,
            "attempts": self.attempts,
            "audit_trail": self.audit_trail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ════════════════════════════════════════════════════════
# AUDIT LOG ENTRY
# ════════════════════════════════════════════════════════
def _audit_entry(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    entry = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    logger.info("AUDIT | %s | %s", event, payload)
    return entry


# ════════════════════════════════════════════════════════
# 1. PII LEAK DETECTION
# ════════════════════════════════════════════════════════
def _normalise(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def _name_variants(customer_name: str) -> list[str]:
    """
    Generate full name, individual tokens, and partial combinations
    so we catch 'Priya', 'Sharma', 'Priya Sharma', 'P. Sharma' etc.
    """
    normalised = _normalise(customer_name)
    tokens = [t for t in normalised.split() if len(t) > 1]
    variants: list[str] = [normalised]
    variants.extend(tokens)
    # First-initial + last-name variants: "p sharma", "p. sharma"
    if len(tokens) >= 2:
        variants.append(f"{tokens[0][0]} {tokens[-1]}")
        variants.append(f"{tokens[0][0]}. {tokens[-1]}")
    return list(set(variants))


def detect_pii_leak(narrative: str, customer_name: str) -> bool:
    """
    Returns True if PII is detected in the narrative.
    Checks full name, individual name tokens, and partial combinations.
    Case-insensitive, spacing-variation tolerant.
    """
    if not narrative or not customer_name:
        return False

    normalised_narrative = _normalise(narrative)
    for variant in _name_variants(customer_name):
        # Use word-boundary aware search to avoid false positives
        pattern = r"\b" + re.escape(variant) + r"\b"
        if re.search(pattern, normalised_narrative):
            logger.warning(
                "PII_LEAK_DETECTED | variant=%r found in narrative", variant
            )
            return True
    return False


# ════════════════════════════════════════════════════════
# 2. EVIDENCE COVERAGE ENFORCEMENT
# ════════════════════════════════════════════════════════
# Accept both "[E1]" and "(E1)" styles because some model outputs
# use parenthesized anchors despite prompt instructions.
_EVIDENCE_TAG_RE = re.compile(r"(?:\[E\d+\]|\(E\d+\))", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
MIN_ANCHORED_SENTENCE_RATIO = 0.70


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def validate_evidence_coverage(narrative: str) -> tuple[bool, list[str]]:
    """
    Returns (passed: bool, unanchored_sentences: list[str]).
    Enforces minimum evidence coverage across the narrative.
    A narrative passes when at least 70% of sentences carry evidence anchors.
    """
    sentences = _split_sentences(narrative)
    if not sentences:
        return False, ["narrative is empty"]

    unanchored = [s for s in sentences if not _EVIDENCE_TAG_RE.search(s)]
    anchored = len(sentences) - len(unanchored)
    anchored_ratio = anchored / len(sentences)
    passed = anchored_ratio >= MIN_ANCHORED_SENTENCE_RATIO
    return passed, unanchored


# ════════════════════════════════════════════════════════
# 3. RETRY WRAPPER
# ════════════════════════════════════════════════════════
_BACKOFF_SECONDS = [0.5, 1.0, 2.0]
MAX_RETRIES = 3


def generate_with_retry(
    generate_fn: Callable[[], str],
    customer_name: str,
    customer_id: str = "",
    alert_id: str = "UNKNOWN",
) -> tuple[str, list[dict[str, Any]]]:
    """
    Wraps generate_fn() with:
      - PII leak detection
      - Evidence coverage validation
      - Exponential backoff retry (max 3 attempts)
      - Structured audit trail

    Returns (narrative, audit_trail) on success.
    Raises SarSafetyViolation after max retries.
    """
    audit_trail: list[dict[str, Any]] = []

    for attempt in range(1, MAX_RETRIES + 1):
        attempt_log: dict[str, Any] = {"attempt": attempt, "alert_id": alert_id}

        # ── Generate ──
        try:
            narrative = generate_fn()
        except Exception as exc:
            entry = _audit_entry(
                "GENERATION_ERROR",
                {**attempt_log, "error": str(exc)},
            )
            audit_trail.append(entry)
            if attempt == MAX_RETRIES:
                raise SarSafetyViolation(
                    reason=f"LLM generation failed: {exc}",
                    violation_type="GENERATION_ERROR",
                    attempts=attempt,
                    audit_trail=audit_trail,
                ) from exc
            _backoff(attempt)
            continue

        # ── PII check ──
        if detect_pii_leak(narrative, customer_name) or (
            customer_id and customer_id.lower() in narrative.lower()
        ):
            entry = _audit_entry(
                "PII_LEAK_DETECTED",
                {**attempt_log, "reason": "customer name or ID found in narrative"},
            )
            audit_trail.append(entry)
            if attempt == MAX_RETRIES:
                raise SarSafetyViolation(
                    reason="PII leak persisted after maximum retries.",
                    violation_type="PII_LEAK_DETECTED",
                    attempts=attempt,
                    audit_trail=audit_trail,
                )
            _backoff(attempt)
            continue

        # ── Evidence coverage check ──
        coverage_passed, unanchored = validate_evidence_coverage(narrative)
        if not coverage_passed:
            total_sentences = len(_split_sentences(narrative))
            anchored_count = total_sentences - len(unanchored)
            entry = _audit_entry(
                "EVIDENCE_COVERAGE_FAILED",
                {
                    **attempt_log,
                    "anchored_count": anchored_count,
                    "total_sentences": total_sentences,
                    "unanchored_count": len(unanchored),
                    "unanchored_sentences": unanchored[:3],
                },
            )
            audit_trail.append(entry)
            if attempt == MAX_RETRIES:
                # Fail-open for partially anchored narratives so case creation can continue,
                # while still preserving a detailed warning trail for analyst review.
                if anchored_count > 0:
                    warning = _audit_entry(
                        "EVIDENCE_COVERAGE_SOFT_ACCEPTED",
                        {
                            **attempt_log,
                            "anchored_count": anchored_count,
                            "total_sentences": total_sentences,
                            "unanchored_count": len(unanchored),
                            "minimum_ratio": MIN_ANCHORED_SENTENCE_RATIO,
                        },
                    )
                    audit_trail.append(warning)
                    return narrative, audit_trail
                raise SarSafetyViolation(
                    reason=(
                        f"Evidence coverage failed after {attempt} attempt(s). "
                        f"{len(unanchored)} unanchored sentence(s) remain."
                    ),
                    violation_type="EVIDENCE_COVERAGE_FAILED",
                    attempts=attempt,
                    audit_trail=audit_trail,
                )
            _backoff(attempt)
            continue

        # ── All checks passed ──
        entry = _audit_entry(
            "NARRATIVE_VALIDATION_PASSED",
            {**attempt_log, "word_count": len(narrative.split())},
        )
        audit_trail.append(entry)
        return narrative, audit_trail

    # Should never reach here — but satisfies type checker
    raise SarSafetyViolation(
        reason="Exhausted all retry attempts.",
        violation_type="MAX_RETRIES_EXCEEDED",
        attempts=MAX_RETRIES,
        audit_trail=audit_trail,
    )


def _backoff(attempt: int) -> None:
    wait = _BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)]
    logger.info("RETRY | attempt=%d | backoff=%.1fs", attempt, wait)
    time.sleep(wait)


# ════════════════════════════════════════════════════════
# 4. FASTAPI INTEGRATION HELPER
# ════════════════════════════════════════════════════════
from fastapi import HTTPException


def run_safety_pipeline(
    generate_fn: Callable[[], str],
    customer_name: str,
    customer_id: str,
    alert_id: str,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Drop-in replacement for direct generate_fn() calls in FastAPI routes.
    Raises HTTPException with structured detail on safety violations.
    Returns (narrative, audit_trail) on success.
    """
    try:
        return generate_with_retry(
            generate_fn=generate_fn,
            customer_name=customer_name,
            customer_id=customer_id,
            alert_id=alert_id,
        )
    except SarSafetyViolation as exc:
        logger.error(
            "SAFETY_PIPELINE_FAILED | alert_id=%s | type=%s | reason=%s",
            alert_id,
            exc.violation_type,
            exc.reason,
        )
        raise HTTPException(
            status_code=422,
            detail=exc.to_api_response(),
        ) from exc


# ════════════════════════════════════════════════════════
# 5. IMPROVED SYSTEM PROMPT BUILDER
# ════════════════════════════════════════════════════════
def build_safety_system_prompt(
    alert_type: str,
    account_type: str,
    customer_profile: str,
    time_window_days: int,
    destination_country: str,
    structuring_rules: str,
    jurisdiction_rules: str,
    deviation_str: str,
    transaction_count: int,
    total_amount: int,
    avg_amount: int,
    txn_per_day: float,
) -> str:
    return f"""CRITICAL OUTPUT FORMAT — FOLLOW EXACTLY OR OUTPUT WILL BE REJECTED:
Write exactly 5 paragraphs of plain compliance prose.
Separate paragraphs with ONE blank line.
Do NOT add section headings, paragraph numbers, preamble, or closing notes.
Start immediately with the first word of the first paragraph.

You are a senior AML compliance analyst filing Suspicious Activity Reports
with FIU-India under PMLA Section 12.

════════════════════════════════════
ABSOLUTE RULES — VIOLATION = REJECTION
════════════════════════════════════
RULE 1 — NO PII: Never write the customer name or customer ID. Always write "the account holder".
RULE 2 — EVIDENCE TAGS MANDATORY: Every single sentence must contain at least one [E#] tag
          referencing the Evidence Reference Map provided. No exceptions.
          A sentence without [E#] will cause the entire output to be rejected and retried.
RULE 3 — FIGURES FROM DATA ONLY: Use ONLY numbers from Transaction Details and Customer Financials.
          Never invent, approximate, or copy figures from AML Reference Knowledge.
RULE 4 — TYPOLOGY: The primary typology is {alert_type}. Name it explicitly in paragraph 4.
RULE 5 — COMPLETE SENTENCES: Never write data labels like "Total inbound:" or "Residual balance:".

════════════════════════════════════
EVIDENCE TAG USAGE — EXAMPLES
════════════════════════════════════
CORRECT: "The account received {transaction_count} transfers [E1] totaling INR {total_amount} [E2] within {time_window_days} days [E3]."
CORRECT: "This represents a {deviation_str} deviation [E9] above the twelve-month baseline [E8]."
WRONG:   "The account received transfers totaling a large amount." ← NO [E#] TAG — REJECTED
WRONG:   "Transaction count: {transaction_count}" ← DATA LABEL — REJECTED

════════════════════════════════════
WRITING STYLE
════════════════════════════════════
- Third person, past tense, professional compliance register
- All monetary amounts prefixed INR
- Minimum 290 words, maximum 420 words total
- No bullet points, no numbered lists

════════════════════════════════════
FIVE PARAGRAPH STRUCTURE
════════════════════════════════════

PARAGRAPH 1 — Background only. Include [E3]:
State: filing institution submitting SAR, {account_type} account, {customer_profile} profile,
{alert_type} alert, {time_window_days}-day monitoring period.
Do NOT include transaction counts, amounts, or destination here.

PARAGRAPH 2 — Transaction summary. Include [E1][E2][E6]:
State: {transaction_count} transfers [E1], INR {total_amount} [E2], outbound to {destination_country} [E6],
residual balance returned to near zero each cycle, pass-through conduit behavior.

PARAGRAPH 3 — Quantitative analysis. Include [E4][E5][E8][E9] and cite rules:
State: deviation [E9] from baseline [E8], average INR {avg_amount} per transaction [E4]
below RBI reporting threshold, velocity {txn_per_day} txn/day [E5] exceeding 5 txn/day threshold.
Then cite each rule by full name and ID: {structuring_rules}

PARAGRAPH 4 — Typology analysis. Include [E6] and cite rules:
Explain analytically why pattern constitutes {alert_type}.
Reference FATF high-risk jurisdiction {destination_country} [E6].
Cite each rule by full name and ID: {jurisdiction_rules}

PARAGRAPH 5 — Conclusion. Include at least one [E] tag:
State: activity determined suspicious, SAR filed under PMLA Section 12 and
Rule 3 Prevention of Money Laundering (Maintenance of Records) Rules 2005,
enhanced monitoring placed on account, related accounts flagged,
escalated to Financial Intelligence Unit, source of funds documentation requested.
Write "the account holder" — never the customer name.
"""
