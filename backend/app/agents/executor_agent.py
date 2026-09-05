"""
Executor Agent — Action execution orchestrator for RecoverOS.

Receives a chosen action → checks guardrails → executes via service mocks
→ records outcome → logs communication for fatigue tracking.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import CircuitBreaker
from app.core.idempotency import IdempotencyGuard
from app.core.policy_engine import policy_engine
from app.models.base import (
    ActionStatus, ActionType, ApprovalRequest, ApprovalStatus,
    AuditLog, CommunicationLog, Outcome, RecoveryAction,
    Transaction, TransactionStatus,
)


class ExecutionResult:
    """Result of executing a recovery action."""

    def __init__(
        self,
        action_id: int,
        action_type: str,
        status: str,
        explanation: str,
        requires_approval: bool = False,
        approval_id: Optional[int] = None,
        guardrail_result: Optional[dict] = None,
        idempotency_hit: bool = False,
    ):
        self.action_id = action_id
        self.action_type = action_type
        self.status = status
        self.explanation = explanation
        self.requires_approval = requires_approval
        self.approval_id = approval_id
        self.guardrail_result = guardrail_result
        self.idempotency_hit = idempotency_hit

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "status": self.status,
            "explanation": self.explanation,
            "requires_approval": self.requires_approval,
            "approval_id": self.approval_id,
            "guardrail_result": self.guardrail_result,
            "idempotency_hit": self.idempotency_hit,
        }


class ExecutorAgent:
    """
    Executes recovery actions with full guardrail checking:
    1. Generate idempotency key — prevent duplicate execution
    2. Check guardrails via policy engine
    3. If blocked → log reason, return blocked status
    4. If needs approval → create ApprovalRequest, return pending
    5. If allowed → execute via mock services, record outcome
    6. Log communication for fatigue tracking
    7. Write audit log entry
    """

    async def execute(
        self,
        db: AsyncSession,
        transaction: Transaction,
        action_type: str,
        utility_score: float = 0.0,
        recovery_probability: float = 0.0,
        expected_revenue: float = 0.0,
        cost: float = 0.0,
        explanation: str = "",
        confidence: float = 0.0,
        requires_approval: bool = False,
        params: Optional[dict] = None,
    ) -> ExecutionResult:
        """Execute a recovery action with full guardrail pipeline."""

        params = params or {}

        # 1. Idempotency check
        guard = IdempotencyGuard(db)
        idem_key = guard.generate_key(transaction.id, action_type)
        previous = await guard.check(idem_key)
        if previous:
            return ExecutionResult(
                action_id=previous.get("action_id", 0),
                action_type=action_type,
                status="duplicate_blocked",
                explanation=f"Idempotency guard: this exact action was already executed "
                           f"at {previous.get('executed_at', 'unknown')}. Duplicate blocked.",
                idempotency_hit=True,
            )

        # 2. Create RecoveryAction record
        action = RecoveryAction(
            transaction_id=transaction.id,
            action_type=action_type,
            params_json=json.dumps(params),
            utility_score=utility_score,
            recovery_probability=recovery_probability,
            expected_revenue=expected_revenue,
            cost=cost,
            explanation=explanation,
            confidence=confidence,
            requires_approval=requires_approval,
            idempotency_key=idem_key,
            status=ActionStatus.PENDING.value,
        )
        db.add(action)
        await db.flush()

        # 3. Check guardrails
        guardrail_result = await policy_engine.evaluate_action(
            db=db,
            merchant_id=transaction.merchant_id,
            action_type=action_type,
            transaction_amount=transaction.amount,
            retry_count=transaction.retry_count,
            touchpoints_last_72h=0,  # already checked in diagnosis
            root_cause=transaction.root_cause or "UNKNOWN",
        )

        if not guardrail_result.allowed:
            # Blocked by guardrails
            action.status = ActionStatus.BLOCKED.value
            blocked_reasons = "; ".join(
                c.reason for c in guardrail_result.checks if not c.passed
            )
            action.explanation = f"BLOCKED: {blocked_reasons}"

            # Audit log
            await self._write_audit_log(
                db, transaction, action_type,
                compliance_passed=False,
                reason_blocked=blocked_reasons,
            )

            return ExecutionResult(
                action_id=action.id,
                action_type=action_type,
                status="blocked",
                explanation=f"Action blocked by guardrails: {blocked_reasons}",
                guardrail_result=guardrail_result.to_dict(),
            )

        # 4. Check if approval required
        if requires_approval or (
            transaction.amount >= 50000 and action_type not in ("escalate_human", "stop")
        ):
            action.requires_approval = True
            action.status = ActionStatus.PENDING.value

            approval = ApprovalRequest(
                action_id=action.id,
                merchant_id=transaction.merchant_id,
                transaction_id=transaction.id,
                transaction_amount=transaction.amount,
                reason=f"High-value transaction (₹{transaction.amount:,.0f}) requires "
                       f"human approval for {action_type}",
                status=ApprovalStatus.PENDING.value,
            )
            db.add(approval)
            await db.flush()

            await self._write_audit_log(
                db, transaction, action_type,
                compliance_passed=True,
                reason_blocked=f"Requires approval (amount ₹{transaction.amount:,.0f})",
            )

            return ExecutionResult(
                action_id=action.id,
                action_type=action_type,
                status="pending_approval",
                explanation=f"Action requires human approval — transaction amount "
                           f"₹{transaction.amount:,.0f} exceeds threshold",
                requires_approval=True,
                approval_id=approval.id,
                guardrail_result=guardrail_result.to_dict(),
            )

        # 5. Execute the action
        exec_result = await self._execute_action(db, transaction, action, params)

        # 6. Record idempotency
        await guard.record(idem_key, transaction.id, action_type, {"action_id": action.id})

        # 7. Audit log
        await self._write_audit_log(
            db, transaction, action_type,
            compliance_passed=True,
        )

        # 8. Update transaction status
        transaction.status = TransactionStatus.RECOVERY_IN_PROGRESS.value
        if action_type in ("retry_now", "retry_delayed"):
            transaction.retry_count += 1

        return exec_result

    async def execute_approved(
        self,
        db: AsyncSession,
        action: RecoveryAction,
        transaction: Transaction,
    ) -> ExecutionResult:
        """Execute a previously approved action."""
        action.status = ActionStatus.APPROVED.value
        params = json.loads(action.params_json) if action.params_json else {}
        return await self._execute_action(db, transaction, action, params)

    async def _execute_action(
        self,
        db: AsyncSession,
        transaction: Transaction,
        action: RecoveryAction,
        params: dict,
    ) -> ExecutionResult:
        """Execute the actual action via mock services."""
        from app.services.razorpay_client import mock_razorpay
        from app.services.whatsapp_service import mock_whatsapp
        from app.services.email_service import mock_email
        from app.services.sms_service import mock_sms
        from app.services.payment_link_service import mock_payment_link

        action_type = action.action_type
        result_detail = ""

        if action_type == ActionType.RETRY_NOW.value:
            result_detail = mock_razorpay.retry_payment(transaction.external_id)
        elif action_type == ActionType.RETRY_DELAYED.value:
            delay_hours = params.get("delay_hours", 6)
            result_detail = mock_razorpay.schedule_retry(transaction.external_id, delay_hours)
        elif action_type == ActionType.SWITCH_TO_UPI.value:
            result_detail = mock_razorpay.switch_payment_method(transaction.external_id, "upi")
        elif action_type == ActionType.SEND_PAYMENT_LINK.value:
            link = mock_payment_link.create_link(transaction.external_id, transaction.amount)
            result_detail = f"Payment link created: {link}"
        elif action_type == ActionType.WHATSAPP_NUDGE.value:
            result_detail = mock_whatsapp.send_message(
                phone=f"+91{9000000000 + transaction.customer_id}",
                template="payment_reminder",
                transaction_id=transaction.external_id,
                amount=transaction.amount,
            )
        elif action_type == ActionType.EMAIL_REMINDER.value:
            result_detail = mock_email.send_email(
                to=f"customer_{transaction.customer_id}@example.com",
                subject="Payment Reminder",
                transaction_id=transaction.external_id,
                amount=transaction.amount,
            )
        elif action_type == ActionType.SMS_REMINDER.value:
            result_detail = mock_sms.send_sms(
                phone=f"+91{9000000000 + transaction.customer_id}",
                transaction_id=transaction.external_id,
                amount=transaction.amount,
            )
        elif action_type == ActionType.OFFER_DISCOUNT.value:
            discount_pct = params.get("discount_percent", 10)
            result_detail = f"Discount of {discount_pct}% offered via payment link"
            link = mock_payment_link.create_link(
                transaction.external_id,
                transaction.amount * (1 - discount_pct / 100),
            )
            result_detail += f": {link}"
        elif action_type == ActionType.ESCALATE_HUMAN.value:
            result_detail = f"Support ticket created for transaction {transaction.external_id}"
        elif action_type == ActionType.PTP_NEGOTIATION.value:
            result_detail = f"PTP negotiation initiated for transaction {transaction.external_id}"
        else:
            result_detail = f"Action {action_type} executed (mock)"

        # Mark as executed
        action.status = ActionStatus.EXECUTED.value
        action.executed_at = datetime.utcnow()

        # Log communication for fatigue tracking
        contact_actions = {
            ActionType.WHATSAPP_NUDGE.value,
            ActionType.EMAIL_REMINDER.value,
            ActionType.SMS_REMINDER.value,
            ActionType.SEND_PAYMENT_LINK.value,
        }
        if action_type in contact_actions:
            comm_log = CommunicationLog(
                customer_id=transaction.customer_id,
                transaction_id=transaction.id,
                channel=action_type,
                message_type="recovery",
            )
            db.add(comm_log)

        return ExecutionResult(
            action_id=action.id,
            action_type=action_type,
            status="executed",
            explanation=result_detail,
        )

    async def _write_audit_log(
        self,
        db: AsyncSession,
        transaction: Transaction,
        action_type: str,
        compliance_passed: bool,
        reason_blocked: str = "",
    ):
        """Write a structured audit log entry."""
        log = AuditLog(
            payment_id=transaction.external_id,
            transaction_id=transaction.id,
            root_cause=transaction.root_cause,
            intervention=action_type,
            action_type=action_type,
            compliance_passed=compliance_passed,
            reason_blocked=reason_blocked or None,
            max_retries_remaining=max(0, 3 - transaction.retry_count),
        )
        db.add(log)


# Module-level singleton
executor_agent = ExecutorAgent()
