"""Webhook API — Ingest payment failure events."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.base import Customer, Transaction, TransactionStatus
from app.schemas.base import PaymentFailedWebhook
from app.agents.diagnostic_agent import diagnostic_agent
from app.agents.strategy_agent import strategy_agent
from app.agents.executor_agent import executor_agent

router = APIRouter()


@router.post("/payment-failed")
async def handle_payment_failed(
    payload: PaymentFailedWebhook,
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest a payment failure event. Triggers the full recovery pipeline:
    1. Create/find transaction record
    2. Diagnose root cause
    3. Select best recovery action
    4. Execute or route to approval queue
    """
    # Find or create customer
    stmt = select(Customer).where(Customer.external_id == payload.customer_id)
    result = await db.execute(stmt)
    customer = result.scalar_one_or_none()

    if customer is None:
        customer = Customer(
            external_id=payload.customer_id,
            merchant_id=payload.merchant_id,
            segment="regular",
        )
        db.add(customer)
        await db.flush()

    # Check for existing transaction (idempotent webhook handling)
    stmt = select(Transaction).where(Transaction.external_id == payload.payment_id)
    result = await db.execute(stmt)
    existing_txn = result.scalar_one_or_none()

    if existing_txn:
        return {
            "status": "already_processed",
            "transaction_id": existing_txn.id,
            "message": f"Transaction {payload.payment_id} already ingested",
        }

    # Create transaction
    txn = Transaction(
        external_id=payload.payment_id,
        merchant_id=payload.merchant_id,
        customer_id=customer.id,
        amount=payload.amount,
        payment_method=payload.payment_method,
        status=TransactionStatus.FAILED.value,
        failure_code=payload.failure_code,
        failure_reason=payload.failure_reason,
        subscription_type=payload.subscription_type,
        timestamp=payload.timestamp or datetime.utcnow(),
    )
    db.add(txn)
    await db.flush()

    # 1. Diagnose
    diagnosis = await diagnostic_agent.diagnose(db, txn)
    txn.root_cause = diagnosis.classification.root_cause.value

    # 2. Select strategy
    strategy = strategy_agent.select_action(
        diagnosis=diagnosis,
        transaction_amount=txn.amount,
        payment_method=txn.payment_method,
    )

    # 3. Execute
    exec_result = await executor_agent.execute(
        db=db,
        transaction=txn,
        action_type=strategy.recommended_action,
        utility_score=strategy.all_scores[0].net_expected_revenue if strategy.all_scores else 0,
        recovery_probability=strategy.all_scores[0].recovery_probability if strategy.all_scores else 0,
        expected_revenue=strategy.all_scores[0].expected_gross_revenue if strategy.all_scores else 0,
        cost=strategy.all_scores[0].communication_cost if strategy.all_scores else 0,
        explanation=strategy.explanation,
        confidence=strategy.confidence,
        requires_approval=strategy.requires_approval,
    )

    return {
        "status": "processed",
        "transaction_id": txn.id,
        "root_cause": diagnosis.classification.root_cause.value,
        "root_cause_confidence": diagnosis.classification.confidence,
        "recommended_action": strategy.recommended_action,
        "execution_status": exec_result.status,
        "explanation": strategy.explanation,
        "confidence": strategy.confidence,
        "requires_approval": exec_result.requires_approval,
        "approval_id": exec_result.approval_id,
    }
