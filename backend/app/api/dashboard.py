"""Dashboard API — Revenue radar and summary stats."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.base import (
    Transaction, TransactionStatus, RecoveryAction, Outcome, ActionStatus,
)
from app.schemas.base import (
    DashboardSummary, FailureCauseCount, RecentAction, DailyTrend,
    TransactionListItem,
)

router = APIRouter()


@router.get("/summary")
async def get_dashboard_summary(
    merchant_id: int = Query(default=1),
    db: AsyncSession = Depends(get_db),
) -> DashboardSummary:
    """Revenue radar: at-risk, recoverable, recovered, top causes."""

    # Total at risk (all failed transactions)
    stmt = select(func.sum(Transaction.amount), func.count()).where(
        Transaction.merchant_id == merchant_id,
        Transaction.status == TransactionStatus.FAILED.value,
    )
    result = await db.execute(stmt)
    row = result.one()
    failed_amount = row[0] or 0.0
    failed_count = row[1] or 0

    # In progress
    stmt = select(func.sum(Transaction.amount), func.count()).where(
        Transaction.merchant_id == merchant_id,
        Transaction.status == TransactionStatus.RECOVERY_IN_PROGRESS.value,
    )
    result = await db.execute(stmt)
    row = result.one()
    in_progress_amount = row[0] or 0.0
    in_progress_count = row[1] or 0

    # Recovered
    stmt = select(func.sum(Transaction.amount), func.count()).where(
        Transaction.merchant_id == merchant_id,
        Transaction.status == TransactionStatus.RECOVERED.value,
    )
    result = await db.execute(stmt)
    row = result.one()
    recovered_amount = row[0] or 0.0
    recovered_count = row[1] or 0

    total_at_risk = failed_amount + in_progress_amount + recovered_amount
    total_count = failed_count + in_progress_count + recovered_count
    recovery_rate = (recovered_count / total_count * 100) if total_count > 0 else 0

    # Top failure causes
    stmt = (
        select(Transaction.root_cause, func.count(), func.sum(Transaction.amount))
        .where(Transaction.merchant_id == merchant_id, Transaction.root_cause.isnot(None))
        .group_by(Transaction.root_cause)
        .order_by(func.count().desc())
        .limit(10)
    )
    result = await db.execute(stmt)
    top_causes = [
        FailureCauseCount(cause=row[0] or "UNKNOWN", count=row[1], amount=row[2] or 0)
        for row in result.all()
    ]

    # Recent actions
    stmt = (
        select(RecoveryAction, Transaction)
        .join(Transaction, RecoveryAction.transaction_id == Transaction.id)
        .where(Transaction.merchant_id == merchant_id)
        .order_by(RecoveryAction.created_at.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    recent = [
        RecentAction(
            transaction_id=action.transaction_id,
            external_id=txn.external_id,
            amount=txn.amount,
            action_type=action.action_type,
            status=action.status,
            explanation=action.explanation or "",
            created_at=action.created_at,
        )
        for action, txn in result.all()
    ]

    # Daily trends (last 30 days)
    trends = await _get_daily_trends(db, merchant_id)

    return DashboardSummary(
        total_at_risk=total_at_risk,
        total_recoverable=failed_amount + in_progress_amount,
        total_recovered=recovered_amount,
        recovery_rate=round(recovery_rate, 1),
        total_transactions=total_count,
        failed_transactions=failed_count,
        recovered_transactions=recovered_count,
        in_progress_transactions=in_progress_count,
        top_failure_causes=top_causes,
        recent_actions=recent,
        daily_trends=trends,
    )


@router.get("/transactions")
async def list_transactions(
    merchant_id: int = Query(default=1),
    status: str = Query(default=None),
    root_cause: str = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    db: AsyncSession = Depends(get_db),
) -> list[TransactionListItem]:
    """List transactions with optional filtering."""
    stmt = select(Transaction).where(Transaction.merchant_id == merchant_id)

    if status:
        stmt = stmt.where(Transaction.status == status)
    if root_cause:
        stmt = stmt.where(Transaction.root_cause == root_cause)

    stmt = stmt.order_by(Transaction.timestamp.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    transactions = result.scalars().all()

    items = []
    for txn in transactions:
        # Count actions
        action_stmt = select(func.count()).select_from(RecoveryAction).where(
            RecoveryAction.transaction_id == txn.id
        )
        action_result = await db.execute(action_stmt)
        action_count = action_result.scalar() or 0

        items.append(TransactionListItem(
            id=txn.id,
            external_id=txn.external_id,
            amount=txn.amount,
            payment_method=txn.payment_method,
            status=txn.status,
            root_cause=txn.root_cause,
            timestamp=txn.timestamp,
            action_count=action_count,
        ))

    return items


async def _get_daily_trends(db: AsyncSession, merchant_id: int) -> list[DailyTrend]:
    """Compute daily failed/recovered amounts for trend chart."""
    # Simplified: aggregate by date from transactions
    stmt = (
        select(
            func.date(Transaction.timestamp).label("date"),
            func.sum(case(
                (Transaction.status == TransactionStatus.FAILED.value, Transaction.amount),
                else_=0,
            )).label("failed_amount"),
            func.sum(case(
                (Transaction.status == TransactionStatus.RECOVERED.value, Transaction.amount),
                else_=0,
            )).label("recovered_amount"),
            func.count().label("total"),
            func.sum(case(
                (Transaction.status == TransactionStatus.RECOVERED.value, 1),
                else_=0,
            )).label("recovered_count"),
        )
        .where(Transaction.merchant_id == merchant_id)
        .group_by(func.date(Transaction.timestamp))
        .order_by(func.date(Transaction.timestamp))
    )

    result = await db.execute(stmt)
    trends = []
    for row in result.all():
        total = row[3] or 1
        rec_count = row[4] or 0
        trends.append(DailyTrend(
            date=str(row[0]),
            failed_amount=float(row[1] or 0),
            recovered_amount=float(row[2] or 0),
            recovery_rate=round(rec_count / total * 100, 1) if total > 0 else 0,
        ))

    return trends


@router.get("/opportunities")
async def get_recovery_opportunities(
    merchant_id: int = Query(default=1),
    limit: int = Query(default=10, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Top recovery opportunities — highest expected net recovery transactions."""
    from app.models.base import Customer
    from app.ml.recovery_predictor import recovery_predictor
    from app.ml.utility_engine import utility_engine

    stmt = (
        select(Transaction, Customer)
        .join(Customer, Transaction.customer_id == Customer.id)
        .where(
            Transaction.merchant_id == merchant_id,
            Transaction.status == TransactionStatus.FAILED.value,
        )
        .order_by(Transaction.amount.desc())
        .limit(limit * 2)
    )
    result = await db.execute(stmt)
    rows = result.all()

    opportunities = []
    for txn, customer in rows:
        # Quick predict for the best action
        probs = recovery_predictor.predict(
            failure_reason=txn.root_cause or "UNKNOWN",
            customer_segment=customer.segment,
            payment_method=txn.payment_method,
            amount=txn.amount,
            retry_count=txn.retry_count,
            previous_transactions=customer.previous_transactions,
            previous_success_rate=customer.previous_success_rate,
            avg_payment_amount=customer.avg_payment_amount,
            customer_lifetime_value=customer.ltv,
            days_since_last_payment=customer.days_since_last_payment,
        )

        # Find best action
        best_action = max(probs, key=probs.get) if probs else "retry_now"
        best_prob = probs.get(best_action, 0.1)
        expected_net = best_prob * txn.amount

        opportunities.append({
            "transaction_id": txn.id,
            "external_id": txn.external_id,
            "customer_name": customer.name or f"Customer #{customer.external_id}",
            "customer_segment": customer.segment,
            "amount": txn.amount,
            "root_cause": txn.root_cause,
            "recovery_probability": round(best_prob, 4),
            "expected_net_recovery": round(expected_net, 2),
            "recommended_action": best_action,
            "payment_method": txn.payment_method,
        })

    # Sort by expected net recovery
    opportunities.sort(key=lambda x: x["expected_net_recovery"], reverse=True)
    return opportunities[:limit]


@router.get("/audit")
async def get_audit_trail(
    merchant_id: int = Query(default=1),
    limit: int = Query(default=30, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Recent audit trail entries."""
    from app.models.base import AuditLog

    stmt = (
        select(AuditLog)
        .where(AuditLog.transaction_id.isnot(None))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()

    return [
        {
            "id": log.id,
            "payment_id": log.payment_id,
            "transaction_id": log.transaction_id,
            "root_cause": log.root_cause,
            "action_type": log.action_type,
            "compliance_passed": log.compliance_passed,
            "reason_blocked": log.reason_blocked,
            "max_retries_remaining": log.max_retries_remaining,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]

