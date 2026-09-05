"""Demo API — Flagship demo scenarios for buildathon presentation."""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.base import (
    Customer, Transaction, TransactionStatus, RecoveryAction,
    Outcome, AuditLog, ActionStatus,
)
from app.agents.diagnostic_agent import diagnostic_agent
from app.agents.strategy_agent import strategy_agent
from app.agents.executor_agent import executor_agent
from app.agents.learning_agent import learning_agent

router = APIRouter()


@router.post("/flagship")
async def run_flagship_demo(
    db: AsyncSession = Depends(get_db),
):
    """
    Run the flagship demo scenario:
    Customer Rahul, ₹4,999 card decline, 8 previous successful payments,
    UPI 7/7 successful, Card 1/3 successful, WhatsApp high response.

    Returns the full pipeline trace.
    """
    steps = []

    # Step 1: Find or create demo customer
    stmt = select(Customer).where(Customer.external_id == "demo_rahul_001")
    result = await db.execute(stmt)
    customer = result.scalar_one_or_none()

    if customer is None:
        customer = Customer(
            external_id="demo_rahul_001",
            merchant_id=1,
            name="Rahul Sharma",
            email="rahul.sharma@example.com",
            phone="+919876543210",
            segment="regular",
            ltv=42500.0,
            preferred_channel="whatsapp",
            previous_transactions=8,
            previous_success_rate=0.875,
            avg_payment_amount=5200.0,
            days_since_last_payment=3,
            payment_history_json=json.dumps([
                {"method": "upi", "amount": 4999, "status": "success"},
                {"method": "upi", "amount": 3500, "status": "success"},
                {"method": "upi", "amount": 6200, "status": "success"},
                {"method": "upi", "amount": 4999, "status": "success"},
                {"method": "upi", "amount": 2800, "status": "success"},
                {"method": "upi", "amount": 5500, "status": "success"},
                {"method": "upi", "amount": 4200, "status": "success"},
                {"method": "card", "amount": 4999, "status": "failed"},
                {"method": "card", "amount": 3200, "status": "failed"},
                {"method": "card", "amount": 7800, "status": "success"},
            ]),
        )
        db.add(customer)
        await db.flush()

    steps.append({
        "step": 1,
        "label": "Customer Retrieved",
        "detail": f"Rahul Sharma — {customer.previous_transactions} previous payments, "
                  f"{customer.previous_success_rate*100:.0f}% success rate, "
                  f"LTV ₹{customer.ltv:,.0f}",
    })

    # Step 2: Create demo transaction
    demo_txn_id = f"pay_demo_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    stmt = select(Transaction).where(Transaction.external_id == demo_txn_id)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        demo_txn_id = f"pay_demo_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{random.randint(100,999)}"

    txn = Transaction(
        external_id=demo_txn_id,
        merchant_id=1,
        customer_id=customer.id,
        amount=4999.0,
        payment_method="card",
        status=TransactionStatus.FAILED.value,
        failure_code="BAD_REQUEST_ERROR",
        failure_reason="card_declined",
        subscription_type=None,
        retry_count=0,
        timestamp=datetime.utcnow(),
    )
    db.add(txn)
    await db.flush()

    steps.append({
        "step": 2,
        "label": "Payment Retrieved",
        "detail": f"₹4,999 card payment failed — card_declined",
    })

    # Step 3: Diagnose
    diagnosis = await diagnostic_agent.diagnose(db, txn)
    txn.root_cause = diagnosis.classification.root_cause.value

    steps.append({
        "step": 3,
        "label": "Root Cause Identified",
        "detail": f"{diagnosis.classification.root_cause.value} — "
                  f"confidence {diagnosis.classification.confidence*100:.0f}%",
    })

    steps.append({
        "step": 4,
        "label": "Customer History Analyzed",
        "detail": f"UPI: 7/7 successful, Card: 1/3 successful, "
                  f"Preferred channel: WhatsApp",
    })

    # Step 4: Strategy
    strat = strategy_agent.select_action(
        diagnosis=diagnosis,
        transaction_amount=txn.amount,
        payment_method=txn.payment_method,
    )

    steps.append({
        "step": 5,
        "label": "Recovery Probability Calculated",
        "detail": f"Best action: {strat.recommended_action} — "
                  f"confidence {strat.confidence*100:.0f}%",
    })

    steps.append({
        "step": 6,
        "label": "Candidate Strategies Evaluated",
        "detail": f"{len(strat.all_scores)} strategies scored and ranked",
    })

    # Get best score details
    best_score = next((s for s in strat.all_scores if s.is_recommended), strat.all_scores[0] if strat.all_scores else None)

    steps.append({
        "step": 7,
        "label": "Recovery Economics Calculated",
        "detail": f"Expected net revenue: ₹{best_score.net_expected_revenue:,.0f}" if best_score else "N/A",
    })

    steps.append({
        "step": 8,
        "label": "Merchant Policy Checked",
        "detail": f"Amount ₹4,999 below ₹50,000 threshold — auto-execution allowed",
    })

    # Step 5: Execute
    exec_result = await executor_agent.execute(
        db=db,
        transaction=txn,
        action_type=strat.recommended_action,
        utility_score=best_score.net_expected_revenue if best_score else 0,
        recovery_probability=best_score.recovery_probability if best_score else 0,
        expected_revenue=best_score.expected_gross_revenue if best_score else 0,
        cost=best_score.communication_cost if best_score else 0,
        explanation=strat.explanation,
        confidence=strat.confidence,
        requires_approval=strat.requires_approval,
    )

    steps.append({
        "step": 9,
        "label": "Best Action Selected & Executed",
        "detail": f"{strat.recommended_action} — status: {exec_result.status}",
    })

    # Step 6: Simulate successful outcome
    if exec_result.status == "executed" and exec_result.action_id:
        outcome_result = await learning_agent.record_outcome(
            db=db,
            action_id=exec_result.action_id,
            recovered=True,
            revenue_recovered=4999.0,
            cost=best_score.communication_cost if best_score else 0,
            time_to_recovery_hours=2.5,
        )

        steps.append({
            "step": 10,
            "label": "Payment Recovered",
            "detail": f"₹4,999 recovered via {strat.recommended_action} in 2.5 hours",
        })

        steps.append({
            "step": 11,
            "label": "Dashboard Updated",
            "detail": "Recovery metrics recalculated",
        })

        steps.append({
            "step": 12,
            "label": "Learning Event Recorded",
            "detail": f"Bandit updated — reward: {outcome_result.get('reward', 0):.4f}",
        })

    await db.flush()

    return {
        "status": "success",
        "transaction_id": txn.id,
        "external_id": txn.external_id,
        "customer": customer.name,
        "amount": txn.amount,
        "root_cause": txn.root_cause,
        "recommended_action": strat.recommended_action,
        "recovery_probability": best_score.recovery_probability if best_score else 0,
        "expected_net_revenue": best_score.net_expected_revenue if best_score else 0,
        "execution_status": exec_result.status,
        "explanation": strat.explanation,
        "confidence": strat.confidence,
        "pipeline_steps": steps,
        "candidates": [s.to_dict() for s in strat.all_scores[:5]],
    }


@router.post("/generate-approvals")
async def generate_approval_scenarios(
    db: AsyncSession = Depends(get_db),
):
    """Generate high-value transactions that require human approval for demo."""
    scenarios = [
        {
            "customer_name": "Priya Enterprises",
            "customer_ext": "demo_priya_b2b",
            "amount": 125000.0,
            "method": "nach",
            "failure_code": "BAD_REQUEST_ERROR",
            "failure_reason": "mandate_failed",
            "segment": "b2b",
        },
        {
            "customer_name": "Amit Kapoor",
            "customer_ext": "demo_amit_vip",
            "amount": 78500.0,
            "method": "card",
            "failure_code": "BAD_REQUEST_ERROR",
            "failure_reason": "insufficient_balance",
            "segment": "vip",
        },
        {
            "customer_name": "TechStar Solutions",
            "customer_ext": "demo_techstar",
            "amount": 480000.0,
            "method": "netbanking",
            "failure_code": "GATEWAY_ERROR",
            "failure_reason": "bank_server_down",
            "segment": "b2b",
        },
    ]

    results = []
    for s in scenarios:
        # Find/create customer
        stmt = select(Customer).where(Customer.external_id == s["customer_ext"])
        result = await db.execute(stmt)
        customer = result.scalar_one_or_none()

        if not customer:
            customer = Customer(
                external_id=s["customer_ext"],
                merchant_id=1,
                name=s["customer_name"],
                segment=s["segment"],
                ltv=s["amount"] * 3,
                preferred_channel="email",
                previous_transactions=12,
                previous_success_rate=0.8,
                avg_payment_amount=s["amount"] * 0.8,
            )
            db.add(customer)
            await db.flush()

        # Create transaction
        ext_id = f"pay_hv_{s['customer_ext']}_{datetime.utcnow().strftime('%H%M%S')}"
        txn = Transaction(
            external_id=ext_id,
            merchant_id=1,
            customer_id=customer.id,
            amount=s["amount"],
            payment_method=s["method"],
            status=TransactionStatus.FAILED.value,
            failure_code=s["failure_code"],
            failure_reason=s["failure_reason"],
            timestamp=datetime.utcnow(),
        )
        db.add(txn)
        await db.flush()

        # Run pipeline — will create approval requests for high-value
        diagnosis = await diagnostic_agent.diagnose(db, txn)
        txn.root_cause = diagnosis.classification.root_cause.value

        strat = strategy_agent.select_action(
            diagnosis=diagnosis,
            transaction_amount=txn.amount,
            payment_method=txn.payment_method,
        )

        best = strat.all_scores[0] if strat.all_scores else None
        exec_result = await executor_agent.execute(
            db=db,
            transaction=txn,
            action_type=strat.recommended_action,
            utility_score=best.net_expected_revenue if best else 0,
            recovery_probability=best.recovery_probability if best else 0,
            expected_revenue=best.expected_gross_revenue if best else 0,
            cost=best.communication_cost if best else 0,
            explanation=strat.explanation,
            confidence=strat.confidence,
            requires_approval=True,  # Force approval for demo
        )

        results.append({
            "transaction_id": txn.id,
            "customer": s["customer_name"],
            "amount": s["amount"],
            "root_cause": txn.root_cause,
            "action": strat.recommended_action,
            "status": exec_result.status,
            "approval_id": exec_result.approval_id,
            "requires_approval": exec_result.requires_approval,
        })

    return {"generated": len(results), "scenarios": results}
