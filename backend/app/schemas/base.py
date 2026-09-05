"""Pydantic request/response schemas for RecoverOS API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Webhook / Ingestion ──────────────────────────────────────────────────────


class PaymentFailedWebhook(BaseModel):
    """Incoming payment failure event (Razorpay-style webhook payload)."""
    payment_id: str = Field(..., description="External payment / transaction ID")
    merchant_id: int = Field(default=1)
    customer_id: str = Field(..., description="External customer ID")
    amount: float = Field(..., description="Payment amount in INR")
    payment_method: str = Field(default="card")
    failure_code: str = Field(default="UNKNOWN")
    failure_reason: str = Field(default="")
    subscription_type: Optional[str] = None
    timestamp: Optional[datetime] = None


# ── Dashboard ────────────────────────────────────────────────────────────────


class DashboardSummary(BaseModel):
    total_at_risk: float = Field(description="Total revenue at risk (INR)")
    total_recoverable: float = Field(description="Revenue deemed recoverable")
    total_recovered: float = Field(description="Revenue actually recovered")
    recovery_rate: float = Field(description="Recovery rate as percentage")
    total_transactions: int = 0
    failed_transactions: int = 0
    recovered_transactions: int = 0
    in_progress_transactions: int = 0
    top_failure_causes: list[FailureCauseCount] = []
    recent_actions: list[RecentAction] = []
    daily_trends: list[DailyTrend] = []


class FailureCauseCount(BaseModel):
    cause: str
    count: int
    amount: float = 0.0


class RecentAction(BaseModel):
    transaction_id: int
    external_id: str = ""
    amount: float
    action_type: str
    status: str
    explanation: str = ""
    created_at: Optional[datetime] = None


class DailyTrend(BaseModel):
    date: str
    failed_amount: float = 0.0
    recovered_amount: float = 0.0
    recovery_rate: float = 0.0


# ── What-If / Decision Explainer ─────────────────────────────────────────────


class ActionCandidate(BaseModel):
    """One candidate action in a what-if comparison."""
    action_type: str
    recovery_probability: float
    expected_revenue: float
    communication_cost: float
    discount_cost: float
    fatigue_cost: float
    risk_cost: float
    net_expected_revenue: float
    is_recommended: bool = False
    explanation: str = ""


class WhatIfResponse(BaseModel):
    transaction_id: int
    external_id: str = ""
    amount: float
    root_cause: str
    customer_segment: str = ""
    candidates: list[ActionCandidate]
    chosen_action: Optional[ActionCandidate] = None
    decision_explanation: str = ""
    confidence: float = 0.0


# ── Transaction Detail ───────────────────────────────────────────────────────


class TransactionDetail(BaseModel):
    id: int
    external_id: str
    merchant_id: int
    customer_id: int
    customer_name: str = ""
    customer_segment: str = ""
    amount: float
    payment_method: str
    status: str
    failure_code: Optional[str] = None
    failure_reason: Optional[str] = None
    root_cause: Optional[str] = None
    subscription_type: Optional[str] = None
    retry_count: int = 0
    timestamp: Optional[datetime] = None
    actions: list[RecoveryActionResponse] = []


class TransactionListItem(BaseModel):
    id: int
    external_id: str
    amount: float
    payment_method: str
    status: str
    root_cause: Optional[str] = None
    customer_segment: str = ""
    timestamp: Optional[datetime] = None
    action_count: int = 0


# ── Recovery Action ──────────────────────────────────────────────────────────


class RecoveryActionResponse(BaseModel):
    id: int
    action_type: str
    utility_score: float = 0.0
    recovery_probability: float = 0.0
    expected_revenue: float = 0.0
    cost: float = 0.0
    explanation: Optional[str] = None
    confidence: float = 0.0
    status: str = "pending"
    requires_approval: bool = False
    executed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    outcome: Optional[OutcomeResponse] = None


class ExecuteActionRequest(BaseModel):
    action_type: Optional[str] = None  # If None, use the recommended action
    force: bool = False  # Skip guardrail checks (admin override)


class ExecuteActionResponse(BaseModel):
    action_id: int
    action_type: str
    status: str
    explanation: str
    requires_approval: bool = False
    approval_id: Optional[int] = None
    guardrail_result: Optional[GuardrailResult] = None


# ── Outcome ──────────────────────────────────────────────────────────────────


class OutcomeResponse(BaseModel):
    recovered: bool = False
    revenue_recovered: float = 0.0
    cost: float = 0.0
    time_to_recovery_hours: Optional[float] = None


# ── Approvals ────────────────────────────────────────────────────────────────


class ApprovalRequestResponse(BaseModel):
    id: int
    action_id: int
    merchant_id: int
    transaction_id: int
    transaction_amount: float
    action_type: str = ""
    reason: str
    status: str
    explanation: str = ""
    customer_segment: str = ""
    recovery_probability: float = 0.0
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ApprovalDecision(BaseModel):
    approved: bool
    decided_by: str = "merchant_admin"
    reason: str = ""


# ── Policy / Guardrails ─────────────────────────────────────────────────────


class PolicyRuleResponse(BaseModel):
    id: int
    rule_type: str
    value: Any
    active: bool


class PolicyConfig(BaseModel):
    """Merchant guardrail configuration — all fields optional for partial updates."""
    max_retries: Optional[int] = None
    max_discount_percent: Optional[float] = None
    max_touchpoints_72h: Optional[int] = None
    quiet_hour_start: Optional[int] = None
    quiet_hour_end: Optional[int] = None
    approval_threshold_amount: Optional[float] = None
    allowed_channels: Optional[list[str]] = None
    auto_retry_enabled: Optional[bool] = None


class PolicyResponse(BaseModel):
    merchant_id: int
    rules: list[PolicyRuleResponse]
    config: PolicyConfig


class GuardrailResult(BaseModel):
    allowed: bool
    checks: list[GuardrailCheck] = []


class GuardrailCheck(BaseModel):
    rule: str
    passed: bool
    reason: str = ""


# ── Batch Evaluation ─────────────────────────────────────────────────────────


class BatchEvaluationRequest(BaseModel):
    transaction_count: int = Field(default=2000, ge=100, le=100000)
    seed: int = 42


class BatchEvaluationReport(BaseModel):
    """Side-by-side comparison: RecoverOS vs fixed-retry baseline."""
    transaction_count: int

    # RecoverOS results
    ros_recovery_rate: float
    ros_net_revenue: float
    ros_total_recovered: float
    ros_avg_attempts: float
    ros_message_count: int
    ros_duplicate_charges: int

    # Baseline results
    baseline_recovery_rate: float
    baseline_net_revenue: float
    baseline_total_recovered: float
    baseline_avg_attempts: float
    baseline_message_count: int
    baseline_duplicate_charges: int

    # Improvement
    recovery_rate_improvement: float
    net_revenue_improvement: float
    message_reduction: float

    # Per-cause breakdown
    per_cause_comparison: list[CauseComparison] = []


class CauseComparison(BaseModel):
    cause: str
    ros_recovery_rate: float
    baseline_recovery_rate: float
    ros_net_revenue: float
    baseline_net_revenue: float


# ── PTP ──────────────────────────────────────────────────────────────────────


class PTPRequest(BaseModel):
    promised_date: datetime
    milestones: list[PTPMilestone] = []


class PTPMilestone(BaseModel):
    amount: float
    due_date: datetime


class PTPResponse(BaseModel):
    id: int
    transaction_id: int
    customer_id: int
    promised_date: datetime
    milestones: list[PTPMilestone] = []
    status: str
    broken_count: int = 0


# Update forward references
DashboardSummary.model_rebuild()
WhatIfResponse.model_rebuild()
ExecuteActionResponse.model_rebuild()
RecoveryActionResponse.model_rebuild()
