"""SQLAlchemy ORM models for RecoverOS."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


# ── Enums ─────────────────────────────────────────────────────────────────────


class RootCause(str, enum.Enum):
    BANK_DOWNTIME = "BANK_DOWNTIME"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    EXPIRED_CARD = "EXPIRED_CARD"
    AUTH_OTP_FAILURE = "AUTH_OTP_FAILURE"
    INVALID_DETAILS = "INVALID_DETAILS"
    USER_ABANDONED = "USER_ABANDONED"
    MERCHANT_INTEGRATION_ERROR = "MERCHANT_INTEGRATION_ERROR"
    SUBSCRIPTION_MANDATE_FAILURE = "SUBSCRIPTION_MANDATE_FAILURE"
    SUSPECTED_FRAUD = "SUSPECTED_FRAUD"
    UNKNOWN = "UNKNOWN"


class ActionType(str, enum.Enum):
    RETRY_NOW = "retry_now"
    RETRY_DELAYED = "retry_delayed"
    SWITCH_TO_UPI = "switch_to_upi"
    SEND_PAYMENT_LINK = "send_payment_link"
    WHATSAPP_NUDGE = "whatsapp_nudge"
    EMAIL_REMINDER = "email_reminder"
    SMS_REMINDER = "sms_reminder"
    OFFER_DISCOUNT = "offer_discount"
    ESCALATE_HUMAN = "escalate_human"
    PTP_NEGOTIATION = "ptp_negotiation"
    STOP = "stop"


class TransactionStatus(str, enum.Enum):
    FAILED = "failed"
    RECOVERY_IN_PROGRESS = "recovery_in_progress"
    RECOVERED = "recovered"
    ABANDONED = "abandoned"
    FRAUD_BLOCKED = "fraud_blocked"


class CustomerSegment(str, enum.Enum):
    NEW = "new"
    REGULAR = "regular"
    VIP = "vip"
    AT_RISK = "at_risk"
    B2B = "b2b"


class PaymentMethod(str, enum.Enum):
    UPI = "upi"
    CARD = "card"
    NETBANKING = "netbanking"
    WALLET = "wallet"
    EMI = "emi"
    NACH = "nach"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PTPStatus(str, enum.Enum):
    ACTIVE = "active"
    FULFILLED = "fulfilled"
    BROKEN = "broken"
    ESCALATED = "escalated"


class ActionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    EXECUTED = "executed"
    BLOCKED = "blocked"
    FAILED = "failed"


# ── Models ────────────────────────────────────────────────────────────────────


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_type: Mapped[str] = mapped_column(String(100), default="retail")
    config_json: Mapped[Optional[str]] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    customers: Mapped[list["Customer"]] = relationship(back_populates="merchant")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="merchant")
    policy_rules: Mapped[list["PolicyRule"]] = relationship(back_populates="merchant")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    merchant_id: Mapped[int] = mapped_column(Integer, ForeignKey("merchants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    segment: Mapped[str] = mapped_column(String(50), default=CustomerSegment.REGULAR.value)
    ltv: Mapped[float] = mapped_column(Float, default=0.0)
    preferred_channel: Mapped[str] = mapped_column(String(50), default="email")
    previous_transactions: Mapped[int] = mapped_column(Integer, default=0)
    previous_success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_payment_amount: Mapped[float] = mapped_column(Float, default=0.0)
    days_since_last_payment: Mapped[int] = mapped_column(Integer, default=0)
    payment_history_json: Mapped[Optional[str]] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    merchant: Mapped["Merchant"] = relationship(back_populates="customers")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="customer")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    merchant_id: Mapped[int] = mapped_column(Integer, ForeignKey("merchants.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), default=TransactionStatus.FAILED.value, index=True
    )
    failure_code: Mapped[Optional[str]] = mapped_column(String(100))
    failure_reason: Mapped[Optional[str]] = mapped_column(String(255))
    root_cause: Mapped[Optional[str]] = mapped_column(String(100))
    subscription_type: Mapped[Optional[str]] = mapped_column(String(50))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    merchant: Mapped["Merchant"] = relationship(back_populates="transactions")
    customer: Mapped["Customer"] = relationship(back_populates="transactions")
    recovery_actions: Mapped[list["RecoveryAction"]] = relationship(back_populates="transaction")


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[int] = mapped_column(Integer, ForeignKey("transactions.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    params_json: Mapped[Optional[str]] = mapped_column(Text, default="{}")
    utility_score: Mapped[float] = mapped_column(Float, default=0.0)
    recovery_probability: Mapped[float] = mapped_column(Float, default=0.0)
    expected_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(50), default=ActionStatus.PENDING.value)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String(255))
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    transaction: Mapped["Transaction"] = relationship(back_populates="recovery_actions")
    outcome: Mapped[Optional["Outcome"]] = relationship(back_populates="action", uselist=False)
    approval_request: Mapped[Optional["ApprovalRequest"]] = relationship(
        back_populates="action", uselist=False
    )


class Outcome(Base):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_id: Mapped[int] = mapped_column(Integer, ForeignKey("recovery_actions.id"), unique=True)
    recovered: Mapped[bool] = mapped_column(Boolean, default=False)
    revenue_recovered: Mapped[float] = mapped_column(Float, default=0.0)
    cost: Mapped[float] = mapped_column(Float, default=0.0)
    time_to_recovery_hours: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    action: Mapped["RecoveryAction"] = relationship(back_populates="outcome")


class PolicyRule(Base):
    __tablename__ = "policy_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[int] = mapped_column(Integer, ForeignKey("merchants.id"), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, default="{}")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    merchant: Mapped["Merchant"] = relationship(back_populates="policy_rules")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    transaction_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("transactions.id"))
    root_cause: Mapped[Optional[str]] = mapped_column(String(100))
    intervention: Mapped[Optional[str]] = mapped_column(String(100))
    action_type: Mapped[Optional[str]] = mapped_column(String(50))
    scheduled_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime)
    compliance_passed: Mapped[bool] = mapped_column(Boolean, default=True)
    reason_blocked: Mapped[Optional[str]] = mapped_column(Text)
    max_retries_remaining: Mapped[Optional[int]] = mapped_column(Integer)
    detail_json: Mapped[Optional[str]] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_id: Mapped[int] = mapped_column(Integer, ForeignKey("recovery_actions.id"), unique=True)
    merchant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_id: Mapped[int] = mapped_column(Integer, ForeignKey("transactions.id"))
    transaction_amount: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default=ApprovalStatus.PENDING.value, index=True)
    decided_by: Mapped[Optional[str]] = mapped_column(String(255))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    action: Mapped["RecoveryAction"] = relationship(back_populates="approval_request")


class PTPCommitment(Base):
    __tablename__ = "ptp_commitments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[int] = mapped_column(Integer, ForeignKey("transactions.id"))
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"))
    promised_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    milestones_json: Mapped[Optional[str]] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(50), default=PTPStatus.ACTIVE.value)
    broken_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class BanditState(Base):
    """Persisted Thompson Sampling state for the contextual bandit."""
    __tablename__ = "bandit_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    segment: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    alpha: Mapped[float] = mapped_column(Float, default=1.0)
    beta_param: Mapped[float] = mapped_column(Float, default=1.0)
    total_reward: Mapped[float] = mapped_column(Float, default=0.0)
    count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class CommunicationLog(Base):
    """Tracks all communications sent to customers for fatigue calculation."""
    __tablename__ = "communication_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), index=True)
    transaction_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("transactions.id"))
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    message_type: Mapped[str] = mapped_column(String(100), default="recovery")
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class IdempotencyRecord(Base):
    """Idempotency lock table to prevent duplicate charges."""
    __tablename__ = "idempotency_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    transaction_id: Mapped[int] = mapped_column(Integer, ForeignKey("transactions.id"))
    action_type: Mapped[str] = mapped_column(String(50))
    result_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
