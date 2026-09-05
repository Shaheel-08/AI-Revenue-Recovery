"""Approvals API — Human-in-the-loop approval queue."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.base import (
    ApprovalRequest, ApprovalStatus, RecoveryAction, Transaction,
    ActionStatus, Customer,
)
from app.schemas.base import ApprovalRequestResponse, ApprovalDecision
from app.agents.executor_agent import executor_agent

router = APIRouter()


@router.get("/pending")
async def get_pending_approvals(
    merchant_id: int = 1,
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalRequestResponse]:
    """Get all pending approval requests for a merchant."""
    stmt = (
        select(ApprovalRequest, RecoveryAction, Transaction)
        .join(RecoveryAction, ApprovalRequest.action_id == RecoveryAction.id)
        .join(Transaction, ApprovalRequest.transaction_id == Transaction.id)
        .where(
            ApprovalRequest.merchant_id == merchant_id,
            ApprovalRequest.status == ApprovalStatus.PENDING.value,
        )
        .order_by(ApprovalRequest.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    approvals = []
    for approval, action, txn in rows:
        # Get customer segment
        stmt2 = select(Customer).where(Customer.id == txn.customer_id)
        result2 = await db.execute(stmt2)
        customer = result2.scalar_one_or_none()

        approvals.append(ApprovalRequestResponse(
            id=approval.id,
            action_id=approval.action_id,
            merchant_id=approval.merchant_id,
            transaction_id=txn.id,
            transaction_amount=txn.amount,
            action_type=action.action_type,
            reason=approval.reason,
            status=approval.status,
            explanation=action.explanation or "",
            customer_segment=customer.segment if customer else "",
            recovery_probability=action.recovery_probability,
            created_at=approval.created_at,
        ))

    return approvals


@router.post("/{approval_id}/decision")
async def decide_approval(
    approval_id: int,
    decision: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a gated action."""
    stmt = select(ApprovalRequest).where(ApprovalRequest.id == approval_id)
    result = await db.execute(stmt)
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(404, f"Approval request {approval_id} not found")

    if approval.status != ApprovalStatus.PENDING.value:
        raise HTTPException(400, f"Approval {approval_id} already decided: {approval.status}")

    # Update approval
    approval.status = ApprovalStatus.APPROVED.value if decision.approved else ApprovalStatus.REJECTED.value
    approval.decided_by = decision.decided_by
    approval.decided_at = datetime.utcnow()

    # Get the action
    stmt = select(RecoveryAction).where(RecoveryAction.id == approval.action_id)
    result = await db.execute(stmt)
    action = result.scalar_one_or_none()

    if decision.approved and action:
        # Execute the approved action
        stmt = select(Transaction).where(Transaction.id == action.transaction_id)
        result = await db.execute(stmt)
        txn = result.scalar_one_or_none()

        if txn:
            exec_result = await executor_agent.execute_approved(db, action, txn)
            return {
                "approval_id": approval_id,
                "status": "approved",
                "execution": exec_result.to_dict(),
            }
    elif action:
        action.status = ActionStatus.BLOCKED.value
        action.explanation = f"Rejected by {decision.decided_by}: {decision.reason}"

    return {
        "approval_id": approval_id,
        "status": "rejected" if not decision.approved else "approved",
        "reason": decision.reason,
    }
