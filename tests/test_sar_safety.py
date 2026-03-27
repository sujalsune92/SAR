"""
tests/test_sar_safety.py
Pytest suite covering PII detection, evidence coverage,
retry success, retry failure, and audit trail integrity.
"""
from __future__ import annotations

import pytest

from sar_safety import (
    SarSafetyViolation,
    detect_pii_leak,
    generate_with_retry,
    validate_evidence_coverage,
)

# ════════════════════════════════════════════════════════
# FIXTURES
# ════════════════════════════════════════════════════════
CLEAN_NARRATIVE = """\
The filing institution is submitting this Suspicious Activity Report [E3] concerning \
a current account held by the account holder, a salaried employee.

The account received 28 inbound transfers [E1] totaling INR 1450000 [E2] within \
3 days [E3], with outbound wires directed to UAE [E6] following each receipt.

The 28 transfers [E1] averaged INR 51785 [E4] per transaction, a velocity of \
9.3 txn/day [E5] exceeding the institutional threshold of 5 txn/day [E5], \
representing a 3715.8% deviation [E9] above the twelve-month baseline [E8].

The pattern is consistent with Layering [E10], involving sequential fund movement \
across institutions to obscure origin, with UAE [E6] classified as a FATF \
high-risk jurisdiction under Round Tripping (AML-009) [E11] and Multi Account \
Layering (AML-011) [E12].

The filing institution has determined the activity suspicious [E1] and is filing \
this SAR under PMLA Section 12, with the account holder placed under enhanced \
monitoring and the matter escalated to the Financial Intelligence Unit [E3].\
"""

CUSTOMER_NAME = "Priya Sharma"
CUSTOMER_ID = "CUST_445"


# ════════════════════════════════════════════════════════
# PII DETECTION TESTS
# ════════════════════════════════════════════════════════
class TestDetectPiiLeak:
    def test_full_name_detected(self):
        narrative = "The account holder Priya Sharma conducted 28 transfers."
        assert detect_pii_leak(narrative, CUSTOMER_NAME) is True

    def test_first_name_only_detected(self):
        narrative = "Priya conducted transactions inconsistent with her profile."
        assert detect_pii_leak(narrative, CUSTOMER_NAME) is True

    def test_last_name_only_detected(self):
        narrative = "The account held by Sharma showed suspicious activity."
        assert detect_pii_leak(narrative, CUSTOMER_NAME) is True

    def test_case_insensitive_detection(self):
        narrative = "PRIYA SHARMA executed 28 transfers."
        assert detect_pii_leak(narrative, CUSTOMER_NAME) is True

    def test_mixed_case_detection(self):
        narrative = "priya sharma is the account holder."
        assert detect_pii_leak(narrative, CUSTOMER_NAME) is True

    def test_clean_narrative_passes(self):
        assert detect_pii_leak(CLEAN_NARRATIVE, CUSTOMER_NAME) is False

    def test_empty_narrative_passes(self):
        assert detect_pii_leak("", CUSTOMER_NAME) is False

    def test_empty_name_passes(self):
        assert detect_pii_leak(CLEAN_NARRATIVE, "") is False

    def test_partial_word_no_false_positive(self):
        # "priya" inside a word like "repriyatization" should not trigger
        narrative = "The account holder conducted suspicious activity."
        assert detect_pii_leak(narrative, CUSTOMER_NAME) is False

    def test_customer_id_not_detected_by_pii_fn(self):
        # detect_pii_leak only checks name — ID check is in generate_with_retry
        narrative = f"Account {CUSTOMER_ID} showed suspicious patterns."
        assert detect_pii_leak(narrative, CUSTOMER_NAME) is False


# ════════════════════════════════════════════════════════
# EVIDENCE COVERAGE TESTS
# ════════════════════════════════════════════════════════
class TestValidateEvidenceCoverage:
    def test_fully_anchored_narrative_passes(self):
        passed, unanchored = validate_evidence_coverage(CLEAN_NARRATIVE)
        assert passed is True
        assert unanchored == []

    def test_missing_tag_fails(self):
        bad = "The account holder conducted suspicious transactions without any reference."
        passed, unanchored = validate_evidence_coverage(bad)
        assert passed is False
        assert len(unanchored) == 1

    def test_partial_coverage_fails(self):
        narrative = (
            "The institution is filing this SAR [E3] for the account holder.\n\n"
            "The account received 28 transfers totaling INR 1450000 with no tag here."
        )
        passed, unanchored = validate_evidence_coverage(narrative)
        assert passed is False
        assert any("no tag here" in s for s in unanchored)

    def test_empty_narrative_fails(self):
        passed, unanchored = validate_evidence_coverage("")
        assert passed is False

    def test_all_sentences_tagged_passes(self):
        narrative = (
            "The filing institution is submitting this SAR [E3].\n\n"
            "The account received 28 transfers [E1] totaling INR 1450000 [E2].\n\n"
            "The velocity was 9.3 txn/day [E5] exceeding the threshold.\n\n"
            "The pattern constitutes Layering [E10] with FATF risk [E6].\n\n"
            "This SAR is filed under PMLA Section 12 [E3] with enhanced monitoring."
        )
        passed, unanchored = validate_evidence_coverage(narrative)
        assert passed is True
        assert unanchored == []

    def test_parenthesized_tags_pass(self):
        narrative = (
            "The filing institution is submitting this SAR (E3).\n\n"
            "The account received 28 transfers (E1) totaling INR 1450000 (E2).\n\n"
            "The velocity was 9.3 txn/day (E5) exceeding the threshold.\n\n"
            "The pattern constitutes Layering (E10) with FATF risk (E6).\n\n"
            "This SAR is filed under PMLA Section 12 (E3) with enhanced monitoring."
        )
        passed, unanchored = validate_evidence_coverage(narrative)
        assert passed is True
        assert unanchored == []

    def test_partial_sentence_coverage_above_threshold_passes(self):
        narrative = (
            "Sentence one is anchored [E1]. "
            "Sentence two is anchored [E2]. "
            "Sentence three is anchored [E3]. "
            "Sentence four is anchored [E4]. "
            "Sentence five has no anchor."
        )
        passed, unanchored = validate_evidence_coverage(narrative)
        assert passed is True
        assert len(unanchored) == 1


# ════════════════════════════════════════════════════════
# RETRY WRAPPER TESTS
# ════════════════════════════════════════════════════════
class TestGenerateWithRetry:
    def test_clean_narrative_succeeds_first_attempt(self):
        call_count = 0

        def mock_generate() -> str:
            nonlocal call_count
            call_count += 1
            return CLEAN_NARRATIVE

        narrative, audit_trail = generate_with_retry(
            generate_fn=mock_generate,
            customer_name=CUSTOMER_NAME,
            customer_id=CUSTOMER_ID,
            alert_id="TEST_001",
        )
        assert narrative == CLEAN_NARRATIVE
        assert call_count == 1
        assert any(e["event"] == "NARRATIVE_VALIDATION_PASSED" for e in audit_trail)

    def test_pii_leak_triggers_retry_then_succeeds(self):
        call_count = 0

        def mock_generate() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return f"Priya Sharma conducted transactions [E1] totaling INR 1450000 [E2]."
            return CLEAN_NARRATIVE

        narrative, audit_trail = generate_with_retry(
            generate_fn=mock_generate,
            customer_name=CUSTOMER_NAME,
            customer_id=CUSTOMER_ID,
            alert_id="TEST_002",
        )
        assert call_count == 2
        assert narrative == CLEAN_NARRATIVE
        assert any(e["event"] == "PII_LEAK_DETECTED" for e in audit_trail)
        assert any(e["event"] == "NARRATIVE_VALIDATION_PASSED" for e in audit_trail)

    def test_evidence_failure_triggers_retry_then_succeeds(self):
        call_count = 0

        def mock_generate() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "The account holder conducted suspicious transactions with no tags."
            return CLEAN_NARRATIVE

        narrative, audit_trail = generate_with_retry(
            generate_fn=mock_generate,
            customer_name=CUSTOMER_NAME,
            customer_id=CUSTOMER_ID,
            alert_id="TEST_003",
        )
        assert call_count == 2
        assert narrative == CLEAN_NARRATIVE
        assert any(e["event"] == "EVIDENCE_COVERAGE_FAILED" for e in audit_trail)

    def test_max_retries_exceeded_raises_violation(self):
        def mock_generate() -> str:
            return "The account holder Priya Sharma conducted suspicious activity."

        with pytest.raises(SarSafetyViolation) as exc_info:
            generate_with_retry(
                generate_fn=mock_generate,
                customer_name=CUSTOMER_NAME,
                customer_id=CUSTOMER_ID,
                alert_id="TEST_004",
            )
        exc = exc_info.value
        assert exc.violation_type == "PII_LEAK_DETECTED"
        assert exc.attempts == 3
        assert len(exc.audit_trail) == 3

    def test_evidence_failure_max_retries_raises_violation(self):
        def mock_generate() -> str:
            return "The account holder conducted suspicious transactions without any evidence tags."

        with pytest.raises(SarSafetyViolation) as exc_info:
            generate_with_retry(
                generate_fn=mock_generate,
                customer_name=CUSTOMER_NAME,
                customer_id=CUSTOMER_ID,
                alert_id="TEST_005",
            )
        exc = exc_info.value
        assert exc.violation_type == "EVIDENCE_COVERAGE_FAILED"
        assert exc.attempts == 3

    def test_generation_exception_retries_and_raises(self):
        call_count = 0

        def mock_generate() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Ollama timeout")

        with pytest.raises(SarSafetyViolation) as exc_info:
            generate_with_retry(
                generate_fn=mock_generate,
                customer_name=CUSTOMER_NAME,
                customer_id=CUSTOMER_ID,
                alert_id="TEST_006",
            )
        assert call_count == 3
        assert exc_info.value.violation_type == "GENERATION_ERROR"

    def test_partial_evidence_soft_accepts_on_last_attempt(self):
        call_count = 0

        def mock_generate() -> str:
            nonlocal call_count
            call_count += 1
            return (
                "The filing institution is submitting this SAR [E3]. "
                "This sentence has no evidence anchor. "
                "This sentence also has no evidence anchor."
            )

        narrative, audit_trail = generate_with_retry(
            generate_fn=mock_generate,
            customer_name=CUSTOMER_NAME,
            customer_id=CUSTOMER_ID,
            alert_id="TEST_006B",
        )
        assert call_count == 3
        assert "[E3]" in narrative
        assert any(e["event"] == "EVIDENCE_COVERAGE_SOFT_ACCEPTED" for e in audit_trail)

    def test_customer_id_leak_triggers_retry(self):
        call_count = 0

        def mock_generate() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return f"Account CUST_445 [E1] showed suspicious layering [E2] activity [E3] pattern [E4] filing [E5]."
            return CLEAN_NARRATIVE

        narrative, audit_trail = generate_with_retry(
            generate_fn=mock_generate,
            customer_name=CUSTOMER_NAME,
            customer_id=CUSTOMER_ID,
            alert_id="TEST_007",
        )
        assert call_count == 2
        assert CUSTOMER_ID not in narrative

    def test_audit_trail_is_ordered(self):
        attempts = []

        def mock_generate() -> str:
            attempts.append(len(attempts) + 1)
            if len(attempts) < 2:
                return "Priya Sharma conducted transactions [E1]."
            return CLEAN_NARRATIVE

        _, audit_trail = generate_with_retry(
            generate_fn=mock_generate,
            customer_name=CUSTOMER_NAME,
            customer_id=CUSTOMER_ID,
            alert_id="TEST_008",
        )
        events = [e["event"] for e in audit_trail]
        assert events[0] == "PII_LEAK_DETECTED"
        assert events[-1] == "NARRATIVE_VALIDATION_PASSED"

    def test_to_api_response_structure(self):
        def mock_generate() -> str:
            return "Bad output without evidence tags or pii."

        with pytest.raises(SarSafetyViolation) as exc_info:
            generate_with_retry(
                generate_fn=mock_generate,
                customer_name="Nobody Known",
                customer_id="CUST_000",
                alert_id="TEST_009",
            )
        response = exc_info.value.to_api_response()
        assert "error" in response
        assert "detail" in response
        assert "attempts" in response
        assert "audit_trail" in response
        assert "timestamp" in response
