"""Customer Intelligence API — Customer context for recovery decisions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.base import (
    Customer, Transaction, TransactionStatus, RecoveryAction,
    Outcome, CommunicationLog, ActionStatus,
)

router = APIRouter()


@router.get("/{customer_id}")
async def get_customer_intelligence(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Full customer intelligence profile for recovery decisions."""
    stmt = select(Customer).where(Customer.id == customer_id)
    result = await db.execute(stmt)
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(404, f"Customer {customer_id} not found")

    # Transaction history
    stmt = select(Transaction).where(Transaction.customer_id == customer_id).order_by(Transaction.timestamp.desc())
    result = await db.execute(stmt)
    transactions = result.scalars().all()

    total_txns = len(transactions)
    failed_txns = sum(1 for t in transactions if t.status == TransactionStatus.FAILED.value)
    recovered_txns = sum(1 for t in transactions if t.status == TransactionStatus.RECOVERED.value)
    in_progress_txns = sum(1 for t in transactions if t.status == TransactionStatus.RECOVERY_IN_PROGRESS.value)

    # Payment method breakdown
    method_stats = {}
    for txn in transactions:
        m = txn.payment_method
        if m not in method_stats:
            method_stats[m] = {"total": 0, "failed": 0, "recovered": 0}
        method_stats[m]["total"] += 1
        if txn.status == TransactionStatus.FAILED.value:
            method_stats[m]["failed"] += 1
        elif txn.status == TransactionStatus.RECOVERED.value:
            method_stats[m]["recovered"] += 1

    # Recovery actions history
    stmt = (
        select(RecoveryAction)
        .join(Transaction, RecoveryAction.transaction_id == Transaction.id)
        .where(Transaction.customer_id == customer_id)
        .order_by(RecoveryAction.created_at.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    actions = result.scalars().all()

    # Communication log count (fatigue indicator)
    from datetime import datetime, timedelta
    cutoff_72h = datetime.utcnow() - timedelta(hours=72)
    stmt = select(func.count()).select_from(CommunicationLog).where(
        CommunicationLog.customer_id == customer_id,
        CommunicationLog.sent_at >= cutoff_72h,
    )
    result = await db.execute(stmt)
    touchpoints_72h = result.scalar() or 0

    total_comms = 0
    stmt = select(func.count()).select_from(CommunicationLog).where(
        CommunicationLog.customer_id == customer_id,
    )
    result = await db.execute(stmt)
    total_comms = result.scalar() or 0

    # Calculate success rate from actual transactions
    successful_payments = total_txns - failed_txns
    success_rate = (successful_payments / total_txns * 100) if total_txns > 0 else 0

    return {
        "id": customer.id,
        "external_id": customer.external_id,
        "name": customer.name or f"Customer #{customer.external_id}",
        "email": customer.email,
        "phone": customer.phone,
        "segment": customer.segment,
        "ltv": customer.ltv,
        "preferred_channel": customer.preferred_channel,
        "previous_transactions": total_txns,
        "successful_payments": successful_payments,
        "failed_payments": failed_txns,
        "recovered_payments": recovered_txns,
        "in_progress_payments": in_progress_txns,
        "success_rate": round(success_rate, 1),
        "avg_payment_amount": customer.avg_payment_amount,
        "days_since_last_payment": customer.days_since_last_payment,
        "payment_method_breakdown": method_stats,
        "touchpoints_last_72h": touchpoints_72h,
        "total_communications": total_comms,
        "fatigue_score": min(touchpoints_72h / 5.0, 1.0),  # 0-1 scale
        "recent_actions": [
            {
                "id": a.id,
                "action_type": a.action_type,
                "status": a.status,
                "recovery_probability": a.recovery_probability,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in actions[:10]
        ],
    }
