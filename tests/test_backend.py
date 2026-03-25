from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import importlib

app_module = importlib.import_module("backend.app")


def test_enrich_narrative_with_pii_replaces_case_insensitive_terms() -> None:
    narrative = (
        "The subject used a savings account. "
        "Later, THE ACCOUNT HOLDER and the customer were reviewed. "
        "A student profile was observed."
    )
    alert_payload = {
        "customer_name": "Rohit Sharma",
        "account_type": "Current",
        "customer_profile": "Retail business owner",
    }

    enriched = app_module.enrich_narrative_with_pii(narrative, alert_payload)
    assert "Rohit Sharma" in enriched
    assert "Current account" in enriched
    assert "Retail business owner profile" in enriched
    assert "the subject" not in enriched.lower()
    assert "the account holder" not in enriched.lower()
    assert "the customer" not in enriched.lower()


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # In-memory stores to avoid PostgreSQL dependency in tests.
    case_store: dict[str, dict[str, Any]] = {}
    audit_store: dict[str, list[dict[str, Any]]] = {}

    def fake_init_db() -> None:
        return None

    def fake_create_case(case_id: str, alert_payload: dict[str, Any], masked_alert_payload: dict[str, Any]) -> None:
        case_store[case_id] = {
            "case_id": case_id,
            "alert_id": alert_payload["alert_id"],
            "status": "INGESTED",
            "risk_score": None,
            "risk_level": None,
            "alert_payload": alert_payload,
            "masked_alert_payload": masked_alert_payload,
            "evidence_pack": {},
            "retrieval_payload": {},
            "prompt_payload": {},
            "validation_payload": {},
            "final_sar": {},
            "analyst_review": None,
            "replay_payload": None,
            "created_at": "2026-03-23T00:00:00+00:00",
            "updated_at": "2026-03-23T00:00:00+00:00",
        }
        audit_store.setdefault(case_id, [])

    def fake_update_case(case_id: str, **fields: Any) -> None:
        case_store[case_id].update(fields)

    def fake_get_case(case_id: str) -> dict[str, Any] | None:
        return case_store.get(case_id)

    def fake_list_cases() -> list[dict[str, Any]]:
        return list(case_store.values())

    def fake_append_audit_event(case_id: str, event_type: str, payload: dict[str, Any]) -> None:
        events = audit_store.setdefault(case_id, [])
        events.append(
            {
                "event_id": len(events) + 1,
                "case_id": case_id,
                "event_type": event_type,
                "event_payload": payload,
                "created_at": "2026-03-23T00:00:00+00:00",
            }
        )

    def fake_get_audit_events(case_id: str) -> list[dict[str, Any]]:
        return audit_store.get(case_id, [])

    def fake_process_alert(alert_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "PENDING_ANALYST_REVIEW",
            "masked_alert": {
                **alert_payload,
                "customer_name": "J*** D**",
                "customer_id": "CU******01",
            },
            "risk_score": 0.91,
            "risk_level": "HIGH",
            "evidence_pack": {
                "rule_summary": [
                    {
                        "rule_id": "AML-001",
                        "rule_name": "Structuring / Smurfing",
                        "confidence": 0.91,
                        "observation": "25 transactions in 2 days",
                        "why_flagged": "Exceeded threshold",
                        "regulation": "FIU-IND Guideline Section 3.2",
                    }
                ]
            },
            "retrieval_payload": {"documents": []},
            "prompt_payload": {"prompt_version": "test", "prompt_sha": "abc", "prompt_sha256": "abc"},
            "validation_payload": {"passed": True, "checks": [], "failed_checks": []},
            "final_sar": {
                "alert_id": alert_payload["alert_id"],
                "alert_type": alert_payload["alert_type"],
                "risk_level": "HIGH",
                "narrative": (
                    "Background section with compliance details.\n\n"
                    "Transaction summary section describing suspicious flow.\n\n"
                    "Typology section linking known AML pattern.\n\n"
                    "Evidence section referencing triggered rules.\n\n"
                    "Conclusion section with filing rationale."
                ),
            },
            "analyst_traceability": [],
            "audit_events": [
                {"event_type": "CASE_INGESTED", "payload": {"ok": True}},
                {"event_type": "RULES_EVALUATED", "payload": {"ok": True}},
            ],
        }

    def fake_replay_case(case_record: dict[str, Any]) -> dict[str, Any]:
        return {
            "replayed": True,
            "replayed_at": "2026-03-23T00:00:00+00:00",
            "replay_matches_original": True,
            "replayed_narrative": case_record.get("final_sar", {}).get("narrative", ""),
            "original_narrative": case_record.get("final_sar", {}).get("narrative", ""),
            "raw_response": {"message": {"content": "ok"}},
        }

    monkeypatch.setattr(app_module, "init_db", fake_init_db)
    monkeypatch.setattr(app_module, "create_case", fake_create_case)
    monkeypatch.setattr(app_module, "update_case", fake_update_case)
    monkeypatch.setattr(app_module, "get_case", fake_get_case)
    monkeypatch.setattr(app_module, "list_cases", fake_list_cases)
    monkeypatch.setattr(app_module, "append_audit_event", fake_append_audit_event)
    monkeypatch.setattr(app_module, "get_audit_events", fake_get_audit_events)
    monkeypatch.setattr(app_module.service, "process_alert", fake_process_alert)
    monkeypatch.setattr(app_module.service, "replay_case", fake_replay_case)

    return TestClient(app_module.app)


def auth_header(client: TestClient) -> dict[str, str]:
    login = client.post("/login", json={"username": "analyst", "password": "password123"})
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def sample_alert() -> dict[str, Any]:
    return {
        "alert_id": "ALERT_TEST_001",
        "customer_id": "CUST001",
        "customer_name": "John Doe",
        "account_type": "Savings",
        "customer_profile": "Retail business owner",
        "alert_type": "Structuring",
        "transactions": {
            "transaction_count": 25,
            "total_amount": 1800000,
            "time_window_days": 2,
            "destination_country": "UAE",
        },
        "pattern": "multiple deposits followed by international transfer",
    }


def test_login_success_returns_token(client: TestClient) -> None:
    response = client.post("/login", json={"username": "analyst", "password": "password123"})
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["role"] == "analyst"


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    response = client.post("/login", json={"username": "analyst", "password": "wrong"})
    assert response.status_code == 401


def test_get_cases_without_token_returns_401(client: TestClient) -> None:
    response = client.get("/cases")
    assert response.status_code == 401


def test_post_cases_with_valid_alert_returns_case_id_and_risk_level(client: TestClient) -> None:
    response = client.post("/cases", headers=auth_header(client), json=sample_alert())
    assert response.status_code == 200
    body = response.json()
    assert "case_id" in body
    assert body["risk_level"] in {"LOW", "MEDIUM", "HIGH"}


def test_review_without_comment_returns_422(client: TestClient) -> None:
    create = client.post("/cases", headers=auth_header(client), json=sample_alert())
    case_id = create.json()["case_id"]

    review = client.post(
        f"/cases/{case_id}/review",
        headers=auth_header(client),
        json={
            "analyst_id": "ANALYST_001",
            "decision": "APPROVE",
            "comment": "",
            "edited_narrative": "Updated",
        },
    )
    assert review.status_code == 422


def test_review_with_comment_returns_200(client: TestClient) -> None:
    create = client.post("/cases", headers=auth_header(client), json=sample_alert())
    case_id = create.json()["case_id"]

    review = client.post(
        f"/cases/{case_id}/review",
        headers=auth_header(client),
        json={
            "analyst_id": "ANALYST_001",
            "decision": "APPROVE",
            "comment": "Looks valid and complete.",
            "edited_narrative": "Updated narrative.",
        },
    )
    assert review.status_code == 200


def test_export_pdf_returns_pdf_content_type(client: TestClient) -> None:
    create = client.post("/cases", headers=auth_header(client), json=sample_alert())
    case_id = create.json()["case_id"]

    response = client.get(f"/cases/{case_id}/export/pdf", headers=auth_header(client))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
