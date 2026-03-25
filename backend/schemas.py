from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Transactions(BaseModel):
    transaction_count: int
    total_amount: float
    time_window_days: int
    destination_country: str | None = None
    reporting_threshold: float | None = None
    min_transaction_amount: float | None = None
    max_transaction_amount: float | None = None


class CustomerFinancials(BaseModel):
    declared_monthly_income: float | None = None
    avg_monthly_deposits_12m: float | None = None
    historical_baseline_txn_count: int | None = None


class AlertPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    alert_id: str
    customer_id: str
    customer_name: str
    account_type: str
    customer_profile: str
    alert_type: str
    transactions: Transactions
    customer_financials: CustomerFinancials | None = None
    pattern: str


class ReviewRequest(BaseModel):
    analyst_id: str = Field(min_length=2)
    decision: Literal["APPROVE", "REJECT"]
    comment: str = Field(min_length=10)
    edited_narrative: str | None = None


class ReplayResponse(BaseModel):
    replayed: bool
    replayed_at: str
    replay_matches_original: bool | None = None
    replayed_narrative: str | None = None
    original_narrative: str | None = None
    reason: str | None = None
    raw_response: dict[str, Any] | None = None