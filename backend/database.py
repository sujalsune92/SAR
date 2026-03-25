from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import os

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json, RealDictCursor


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/sar_audit",
    )


@contextmanager
def get_connection() -> Iterator[Any]:
    connection = psycopg2.connect(get_database_url())
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS cases (
        case_id UUID PRIMARY KEY,
        alert_id TEXT NOT NULL,
        status TEXT NOT NULL,
        risk_score DOUBLE PRECISION,
        risk_level TEXT,
        alert_payload JSONB NOT NULL,
        masked_alert_payload JSONB NOT NULL,
        evidence_pack JSONB,
        retrieval_payload JSONB,
        prompt_payload JSONB,
        validation_payload JSONB,
        final_sar JSONB,
        analyst_review JSONB,
        replay_payload JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
    CREATE INDEX IF NOT EXISTS idx_cases_risk_score ON cases(risk_score DESC NULLS LAST);
    CREATE INDEX IF NOT EXISTS idx_cases_updated_at ON cases(updated_at DESC);

    CREATE TABLE IF NOT EXISTS audit_events (
        event_id BIGSERIAL PRIMARY KEY,
        case_id UUID NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
        event_type TEXT NOT NULL,
        event_payload JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_audit_case_id ON audit_events(case_id, created_at);
    """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(ddl)


def create_case(case_id: str, alert_payload: dict[str, Any], masked_alert_payload: dict[str, Any]) -> None:
    query = """
    INSERT INTO cases (
        case_id,
        alert_id,
        status,
        alert_payload,
        masked_alert_payload,
        created_at,
        updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    now = utc_now()
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    case_id,
                    alert_payload["alert_id"],
                    "INGESTED",
                    Json(alert_payload),
                    Json(masked_alert_payload),
                    now,
                    now,
                ),
            )


def update_case(case_id: str, **fields: Any) -> None:
    if not fields:
        return

    assignments = []
    values = []
    fields["updated_at"] = utc_now()
    for key, value in fields.items():
        assignments.append(sql.SQL("{} = %s").format(sql.Identifier(key)))
        if isinstance(value, (dict, list)):
            values.append(Json(value))
        else:
            values.append(value)

    statement = sql.SQL("UPDATE cases SET {} WHERE case_id = %s").format(sql.SQL(", ").join(assignments))
    values.append(case_id)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(statement, values)


def append_audit_event(case_id: str, event_type: str, event_payload: dict[str, Any]) -> None:
    query = """
    INSERT INTO audit_events (case_id, event_type, event_payload)
    VALUES (%s, %s, %s)
    """
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (case_id, event_type, Json(event_payload)))


def get_case(case_id: str) -> dict[str, Any] | None:
    query = "SELECT * FROM cases WHERE case_id = %s"
    with get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (case_id,))
            return cursor.fetchone()


def list_cases() -> list[dict[str, Any]]:
    query = """
    SELECT case_id, alert_id, status, risk_score, risk_level, final_sar, analyst_review, created_at, updated_at
    FROM cases
    ORDER BY risk_score DESC NULLS LAST, updated_at DESC
    """
    with get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query)
            return cursor.fetchall()


def get_audit_events(case_id: str) -> list[dict[str, Any]]:
    query = """
    SELECT event_id, case_id, event_type, event_payload, created_at
    FROM audit_events
    WHERE case_id = %s
    ORDER BY created_at, event_id
    """
    with get_connection() as connection:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (case_id,))
            return cursor.fetchall()