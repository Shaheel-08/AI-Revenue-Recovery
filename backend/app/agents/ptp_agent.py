"""
Promise-to-Pay (PTP) Agent for RecoverOS.

Handles high-value/B2B unpaid invoices:
- Negotiates a payment date
- Supports splitting into milestones
- Sets automated follow-up triggers for PTP date
- Escalates to human if broken twice
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import (
    PTPCommitment, PTPStatus, Transaction, Customer, AuditLog,
)


class PTPResult:
    """Result of PTP negotiation."""

    def __init__(
        self,
        ptp_id: int,
        status: str,
        promised_date: datetime,
        milestones: list[dict],
        explanation: str,
        escalated: bool = False,
    ):
        self.ptp_id = ptp_id
        self.status = status
        self.promised_date = promised_date
        self.milestones = milestones
        self.explanation = explanation
        self.escalated = escalated

    def to_dict(self) -> dict:
        return {
            "ptp_id": self.ptp_id,
            "status": self.status,
            "promised_date": self.promised_date.isoformat(),
            "milestones": self.milestones,
            "explanation": self.explanation,
            "escalated": self.escalated,
        }


class PTPAgent:
    """
    Promise-to-Pay agent for B2B and high-value transaction recovery.

    Flow:
    1. Propose a payment date based on amount and customer history
    2. Split into milestones if amount > threshold
    3. Track PTP status
    4. On broken PTP: increment broken_count, re-negotiate
    5. If broken twice: escalate to human
    """

    def __init__(
        self,
        milestone_threshold: float = 100000.0,
        max_broken_count: int = 2,
        default_ptp_days: int = 7,
    ):
        self.milestone_threshold = milestone_threshold
        self.max_broken_count = max_broken_count
        self.default_ptp_days = default_ptp_days

    async def negotiate(
        self,
        db: AsyncSession,
        transaction: Transaction,
        promised_date: Optional[datetime] = None,
        milestones: Optional[list[dict]] = None,
    ) -> PTPResult:
        """
        Create or update a Promise-to-Pay commitment.
        """
        # Check for existing PTP
        stmt = select(PTPCommitment).where(
            PTPCommitment.transaction_id == transaction.id,
            PTPCommitment.status.in_([PTPStatus.ACTIVE.value, PTPStatus.BROKEN.value]),
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing and existing.broken_count >= self.max_broken_count:
            # Escalate — PTP has been broken too many times
            existing.status = PTPStatus.ESCALATED.value

            # Log escalation
            audit = AuditLog(
                payment_id=transaction.external_id,
                transaction_id=transaction.id,
                root_cause=transaction.root_cause,
                intervention="ptp_escalation",
                action_type="escalate_human",
                compliance_passed=True,
                reason_blocked=f"PTP broken {existing.broken_count} times — auto-escalating to human",
            )
            db.add(audit)

            return PTPResult(
                ptp_id=existing.id,
                status="escalated",
                promised_date=existing.promised_date,
                milestones=json.loads(existing.milestones_json) if existing.milestones_json else [],
                explanation=(
                    f"Promise-to-Pay has been broken {existing.broken_count} times. "
                    f"Automatically escalating to human support for direct negotiation."
                ),
                escalated=True,
            )

        # Default promised date: N days from now
        if promised_date is None:
            promised_date = datetime.utcnow() + timedelta(days=self.default_ptp_days)

        # Generate milestones for large amounts
        if milestones is None and transaction.amount >= self.milestone_threshold:
            milestones = self._generate_milestones(transaction.amount, promised_date)

        milestone_json = json.dumps(milestones or [])

        if existing:
            # Re-negotiation
            existing.promised_date = promised_date
            existing.milestones_json = milestone_json
            existing.status = PTPStatus.ACTIVE.value
            ptp = existing
            explanation = (
                f"PTP re-negotiated: new payment date {promised_date.strftime('%d %b %Y')}. "
                f"Previous PTP was broken {existing.broken_count} time(s)."
            )
        else:
            # New PTP
            ptp = PTPCommitment(
                transaction_id=transaction.id,
                customer_id=transaction.customer_id,
                promised_date=promised_date,
                milestones_json=milestone_json,
                status=PTPStatus.ACTIVE.value,
                broken_count=0,
            )
            db.add(ptp)
            if milestones:
                explanation = (
                    f"Promise-to-Pay created: payment date {promised_date.strftime('%d %b %Y')} "
                    f"with {len(milestones)} milestone(s) totaling ₹{transaction.amount:,.0f}."
                )
            else:
                explanation = (
                    f"Promise-to-Pay created: full payment of ₹{transaction.amount:,.0f} "
                    f"by {promised_date.strftime('%d %b %Y')}."
                )

        await db.flush()

        return PTPResult(
            ptp_id=ptp.id,
            status=ptp.status,
            promised_date=promised_date,
            milestones=milestones or [],
            explanation=explanation,
        )

    async def mark_broken(
        self,
        db: AsyncSession,
        ptp_id: int,
    ) -> PTPResult:
        """Mark a PTP as broken (payment not received by promised date)."""
        stmt = select(PTPCommitment).where(PTPCommitment.id == ptp_id)
        result = await db.execute(stmt)
        ptp = result.scalar_one_or_none()

        if ptp is None:
            raise ValueError(f"PTP {ptp_id} not found")

        ptp.broken_count += 1
        ptp.status = PTPStatus.BROKEN.value

        milestones = json.loads(ptp.milestones_json) if ptp.milestones_json else []

        if ptp.broken_count >= self.max_broken_count:
            ptp.status = PTPStatus.ESCALATED.value
            explanation = (
                f"PTP broken {ptp.broken_count} times — escalating to human support."
            )
            escalated = True
        else:
            explanation = (
                f"PTP broken (count: {ptp.broken_count}). "
                f"Re-negotiation recommended."
            )
            escalated = False

        return PTPResult(
            ptp_id=ptp.id,
            status=ptp.status,
            promised_date=ptp.promised_date,
            milestones=milestones,
            explanation=explanation,
            escalated=escalated,
        )

    async def mark_fulfilled(
        self,
        db: AsyncSession,
        ptp_id: int,
    ) -> PTPResult:
        """Mark a PTP as fulfilled (payment received)."""
        stmt = select(PTPCommitment).where(PTPCommitment.id == ptp_id)
        result = await db.execute(stmt)
        ptp = result.scalar_one_or_none()

        if ptp is None:
            raise ValueError(f"PTP {ptp_id} not found")

        ptp.status = PTPStatus.FULFILLED.value
        milestones = json.loads(ptp.milestones_json) if ptp.milestones_json else []

        return PTPResult(
            ptp_id=ptp.id,
            status="fulfilled",
            promised_date=ptp.promised_date,
            milestones=milestones,
            explanation=f"Promise-to-Pay fulfilled — payment received.",
        )

    def _generate_milestones(
        self,
        total_amount: float,
        final_date: datetime,
    ) -> list[dict]:
        """Auto-generate payment milestones for large amounts."""
        now = datetime.utcnow()
        total_days = max((final_date - now).days, 1)

        if total_amount >= 500000:
            # 3 milestones: 40% / 30% / 30%
            splits = [0.40, 0.30, 0.30]
        elif total_amount >= 200000:
            # 2 milestones: 50% / 50%
            splits = [0.50, 0.50]
        else:
            # Single milestone
            splits = [1.0]

        milestones = []
        for i, split in enumerate(splits):
            days_offset = int(total_days * (i + 1) / len(splits))
            due_date = now + timedelta(days=days_offset)
            milestones.append({
                "amount": round(total_amount * split, 2),
                "due_date": due_date.isoformat(),
                "status": "pending",
            })

        return milestones


# Module-level singleton
ptp_agent = PTPAgent()
