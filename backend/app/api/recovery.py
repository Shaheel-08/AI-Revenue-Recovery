"""Recovery API — What-if analysis and action execution."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.base import Transaction, Customer, RecoveryAction, Outcome
from app.schemas.base import (
    WhatIfResponse, ActionCandidate, TransactionDetail,
    RecoveryActionResponse, OutcomeResponse, ExecuteActionRequest,
)
from app.agents.diagnostic_agent import diagnostic_agent
from app.agents.strategy_agent import strategy_agent
from app.agents.executor_agent import executor_agent
from app.agents.learning_agent import learning_agent

router = APIRouter()


@router.get("/{transaction_id}")
async def get_transaction_detail(
    transaction_id: int,
    db: AsyncSession = Depends(get_db),
) -> TransactionDetail:
    """Get full transaction detail with actions and outcomes."""
    stmt = select(Transaction).where(Transaction.id == transaction_id)
    result = await db.execute(stmt)
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(404, f"Transaction {transaction_id} not found")

    # Get customer info
    stmt = select(Customer).where(Customer.id == txn.customer_id)
    result = await db.execute(stmt)
    customer = result.scalar_one_or_none()

    # Get actions with outcomes
    stmt = select(RecoveryAction).where(
        RecoveryAction.transaction_id == transaction_id
    ).order_by(RecoveryAction.created_at.desc())
    result = await db.execute(stmt)
    actions = result.scalars().all()

    action_responses = []
    for action in actions:
        # Get outcome
        stmt = select(Outcome).where(Outcome.action_id == action.id)
        result = await db.execute(stmt)
        outcome = result.scalar_one_or_none()

        outcome_resp = None
        if outcome:
            outcome_resp = OutcomeResponse(
                recovered=outcome.recovered,
                revenue_recovered=outcome.revenue_recovered,
                cost=outcome.cost,
                time_to_recovery_hours=outcome.time_to_recovery_hours,
            )

        action_responses.append(RecoveryActionResponse(
            id=action.id,
            action_type=action.action_type,
            utility_score=action.utility_score,
            recovery_probability=action.recovery_probability,
            expected_revenue=action.expected_revenue,
            cost=action.cost,
            explanation=action.explanation,
            confidence=action.confidence,
            status=action.status,
            requires_approval=action.requires_approval,
            executed_at=action.executed_at,
            created_at=action.created_at,
            outcome=outcome_resp,
        ))

    return TransactionDetail(
        id=txn.id,
        external_id=txn.external_id,
        merchant_id=txn.merchant_id,
        customer_id=txn.customer_id,
        customer_name=customer.name if customer else "",
        customer_segment=customer.segment if customer else "",
        amount=txn.amount,
        payment_method=txn.payment_method,
        status=txn.status,
        failure_code=txn.failure_code,
        failure_reason=txn.failure_reason,
        root_cause=txn.root_cause,
        subscription_type=txn.subscription_type,
        retry_count=txn.retry_count,
        timestamp=txn.timestamp,
        actions=action_responses,
    )


@router.get("/{transaction_id}/whatif")
async def get_whatif_analysis(
    transaction_id: int,
    db: AsyncSession = Depends(get_db),
) -> WhatIfResponse:
    """
    Get ranked action comparison table for a transaction.
    Shows all candidate actions with recovery_probability, expected_revenue,
    cost, and net_expected_revenue.
    """
    stmt = select(Transaction).where(Transaction.id == transaction_id)
    result = await db.execute(stmt)
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(404, f"Transaction {transaction_id} not found")

    # Run diagnosis
    diagnosis = await diagnostic_agent.diagnose(db, txn)

    # Run strategy (generates all scores)
    strat = strategy_agent.select_action(
        diagnosis=diagnosis,
        transaction_amount=txn.amount,
        payment_method=txn.payment_method,
    )

    # Build candidates list
    candidates = []
    for score in strat.all_scores:
        candidates.append(ActionCandidate(
            action_type=score.action_type,
            recovery_probability=score.recovery_probability,
            expected_revenue=score.expected_gross_revenue,
            communication_cost=score.communication_cost,
            discount_cost=score.discount_cost,
            fatigue_cost=score.fatigue_cost,
            risk_cost=score.risk_cost,
            net_expected_revenue=score.net_expected_revenue,
            is_recommended=score.is_recommended,
            explanation=score.explanation,
        ))

    # Get customer segment
    stmt = select(Customer).where(Customer.id == txn.customer_id)
    result = await db.execute(stmt)
    customer = result.scalar_one_or_none()

    chosen = next((c for c in candidates if c.is_recommended), candidates[0] if candidates else None)

    return WhatIfResponse(
        transaction_id=txn.id,
        external_id=txn.external_id,
        amount=txn.amount,
        root_cause=diagnosis.classification.root_cause.value,
        customer_segment=customer.segment if customer else "",
        candidates=candidates,
        chosen_action=chosen,
        decision_explanation=strat.explanation,
        confidence=strat.confidence,
    )


@router.post("/{transaction_id}/execute")
async def execute_recovery_action(
    transaction_id: int,
    request: ExecuteActionRequest = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger the chosen recovery action for a transaction."""
    stmt = select(Transaction).where(Transaction.id == transaction_id)
    result = await db.execute(stmt)
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(404, f"Transaction {transaction_id} not found")

    # Diagnose and strategize
    diagnosis = await diagnostic_agent.diagnose(db, txn)
    strat = strategy_agent.select_action(
        diagnosis=diagnosis,
        transaction_amount=txn.amount,
        payment_method=txn.payment_method,
    )

    action_type = strat.recommended_action
    if request and request.action_type:
        action_type = request.action_type

    best_score = next(
        (s for s in strat.all_scores if s.action_type == action_type),
        strat.all_scores[0] if strat.all_scores else None,
    )

    exec_result = await executor_agent.execute(
        db=db,
        transaction=txn,
        action_type=action_type,
        utility_score=best_score.net_expected_revenue if best_score else 0,
        recovery_probability=best_score.recovery_probability if best_score else 0,
        expected_revenue=best_score.expected_gross_revenue if best_score else 0,
        cost=best_score.communication_cost if best_score else 0,
        explanation=strat.explanation,
        confidence=strat.confidence,
        requires_approval=strat.requires_approval,
    )

    return exec_result.to_dict()


@router.post("/{transaction_id}/outcome")
async def record_transaction_outcome(
    transaction_id: int,
    recovered: bool,
    revenue_recovered: float = 0.0,
    cost: float = 0.0,
    time_to_recovery_hours: float = None,
    db: AsyncSession = Depends(get_db),
):
    """Record outcome for the most recent action on a transaction."""
    stmt = (
        select(RecoveryAction)
        .where(RecoveryAction.transaction_id == transaction_id)
        .order_by(RecoveryAction.created_at.desc())
    )
    result = await db.execute(stmt)
    action = result.scalars().first()

    if not action:
        raise HTTPException(404, f"No recovery action found for transaction {transaction_id}")

    outcome = await learning_agent.record_outcome(
        db=db,
        action_id=action.id,
        recovered=recovered,
        revenue_recovered=revenue_recovered,
        cost=cost,
        time_to_recovery_hours=time_to_recovery_hours,
    )
    return outcome
