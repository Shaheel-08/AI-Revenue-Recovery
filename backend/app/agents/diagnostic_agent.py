"""
Diagnostic Agent — Root-cause diagnosis orchestrator.

Receives a transaction → classifies root cause → enriches with customer context
→ returns a structured diagnosis.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.failure_classifier import failure_classifier, FailureClassification
from app.models.base import (
    Customer, Transaction, CommunicationLog, RecoveryAction, RootCause,
)


class DiagnosisResult:
    """Full diagnosis of a failed transaction."""

    def __init__(
        self,
        transaction_id: int,
        classification: FailureClassification,
        customer_context: dict,
        touchpoints_last_72h: int = 0,
        retry_count: int = 0,
        is_high_value: bool = False,
        is_b2b: bool = False,
    ):
        self.transaction_id = transaction_id
        self.classification = classification
        self.customer_context = customer_context
        self.touchpoints_last_72h = touchpoints_last_72h
        self.retry_count = retry_count
        self.is_high_value = is_high_value
        self.is_b2b = is_b2b

    def to_dict(self) -> dict:
        return {
            "transaction_id": self.transaction_id,
            "root_cause": self.classification.root_cause.value,
            "confidence": self.classification.confidence,
            "reasoning": self.classification.reasoning,
            "is_recoverable": self.classification.is_recoverable,
            "recommended_urgency": self.classification.recommended_urgency,
            "customer_context": self.customer_context,
            "touchpoints_last_72h": self.touchpoints_last_72h,
            "retry_count": self.retry_count,
            "is_high_value": self.is_high_value,
            "is_b2b": self.is_b2b,
        }


class DiagnosticAgent:
    """
    Orchestrates the diagnosis pipeline:
    1. Classify root cause from failure code/reason
    2. Enrich with customer context (history, LTV, segment, channel prefs)
    3. Count recent touchpoints for fatigue calculation
    4. Flag high-value and B2B transactions
    """

    def __init__(self, approval_threshold: float = 50000.0):
        self.approval_threshold = approval_threshold

    async def diagnose(
        self,
        db: AsyncSession,
        transaction: Transaction,
    ) -> DiagnosisResult:
        """
        Run full diagnosis on a failed transaction.
        """
        # 1. Classify root cause
        classification = failure_classifier.classify(
            failure_code=transaction.failure_code,
            failure_reason=transaction.failure_reason,
            payment_method=transaction.payment_method,
            timestamp=transaction.timestamp,
            subscription_type=transaction.subscription_type,
            retry_count=transaction.retry_count,
            amount=transaction.amount,
        )

        # 2. Get customer context
        customer_context = await self._get_customer_context(db, transaction.customer_id)

        # 3. Count touchpoints in last 72h
        touchpoints = await self._count_touchpoints(db, transaction.customer_id)

        # 4. Flags
        is_high_value = transaction.amount >= self.approval_threshold
        is_b2b = customer_context.get("segment") == "b2b"

        return DiagnosisResult(
            transaction_id=transaction.id,
            classification=classification,
            customer_context=customer_context,
            touchpoints_last_72h=touchpoints,
            retry_count=transaction.retry_count,
            is_high_value=is_high_value,
            is_b2b=is_b2b,
        )

    async def diagnose_from_webhook(
        self,
        db: AsyncSession,
        transaction_id: int,
    ) -> Optional[DiagnosisResult]:
        """Diagnose a transaction by ID (e.g., from webhook handler)."""
        stmt = select(Transaction).where(Transaction.id == transaction_id)
        result = await db.execute(stmt)
        transaction = result.scalar_one_or_none()
        if transaction is None:
            return None
        return await self.diagnose(db, transaction)

    async def _get_customer_context(self, db: AsyncSession, customer_id: int) -> dict:
        """Fetch customer profile for context enrichment."""
        stmt = select(Customer).where(Customer.id == customer_id)
        result = await db.execute(stmt)
        customer = result.scalar_one_or_none()

        if customer is None:
            return {
                "segment": "unknown",
                "ltv": 0.0,
                "preferred_channel": "email",
                "previous_transactions": 0,
                "previous_success_rate": 0.0,
                "avg_payment_amount": 0.0,
                "days_since_last_payment": 30,
            }

        return {
            "customer_id": customer.id,
            "segment": customer.segment,
            "ltv": customer.ltv,
            "preferred_channel": customer.preferred_channel,
            "previous_transactions": customer.previous_transactions,
            "previous_success_rate": customer.previous_success_rate,
            "avg_payment_amount": customer.avg_payment_amount,
            "days_since_last_payment": customer.days_since_last_payment,
        }

    async def _count_touchpoints(self, db: AsyncSession, customer_id: int) -> int:
        """Count communication touchpoints in the last 72 hours."""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(hours=72)
        stmt = select(func.count()).select_from(CommunicationLog).where(
            CommunicationLog.customer_id == customer_id,
            CommunicationLog.sent_at >= cutoff,
        )
        result = await db.execute(stmt)
        return result.scalar() or 0


# Module-level singleton
diagnostic_agent = DiagnosticAgent()
