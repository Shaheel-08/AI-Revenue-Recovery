"""
Policy Engine for RecoverOS.

Loads merchant PolicyRules from DB, evaluates proposed actions against all
active rules, and returns pass/fail with triggering details.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import CircuitBreaker, GuardrailResult
from app.models.base import PolicyRule


# Default policy values
DEFAULT_POLICY = {
    "max_retries": 3,
    "max_discount_percent": 15.0,
    "max_touchpoints_72h": 5,
    "quiet_hour_start": 22,
    "quiet_hour_end": 8,
    "approval_threshold_amount": 50000.0,
    "allowed_channels": [
        "retry_now", "retry_delayed", "switch_to_upi", "send_payment_link",
        "whatsapp_nudge", "email_reminder", "sms_reminder",
        "offer_discount", "escalate_human", "ptp_negotiation", "stop",
    ],
    "auto_retry_enabled": True,
}


class PolicyEngine:
    """
    Loads and evaluates merchant guardrail policies.

    Combines DB-stored PolicyRules with the CircuitBreaker for enforcement.
    """

    async def get_merchant_policy(
        self,
        db: AsyncSession,
        merchant_id: int,
    ) -> dict:
        """Load all active policy rules for a merchant, merged with defaults."""
        stmt = select(PolicyRule).where(
            PolicyRule.merchant_id == merchant_id,
            PolicyRule.active == True,
        )
        result = await db.execute(stmt)
        rules = result.scalars().all()

        # Start with defaults
        policy = dict(DEFAULT_POLICY)

        # Override with merchant-specific rules
        for rule in rules:
            try:
                value = json.loads(rule.value_json)
                policy[rule.rule_type] = value
            except (json.JSONDecodeError, TypeError):
                pass

        return policy

    async def evaluate_action(
        self,
        db: AsyncSession,
        merchant_id: int,
        action_type: str,
        transaction_amount: float = 0.0,
        retry_count: int = 0,
        touchpoints_last_72h: int = 0,
        discount_percent: float = 0.0,
        root_cause: str = "UNKNOWN",
    ) -> GuardrailResult:
        """
        Evaluate a proposed action against all merchant policies.

        Returns a GuardrailResult with detailed pass/fail per rule.
        """
        policy = await self.get_merchant_policy(db, merchant_id)

        # Build a CircuitBreaker with merchant-specific settings
        cb = CircuitBreaker(
            max_touchpoints_72h=policy.get("max_touchpoints_72h"),
            quiet_hour_start=policy.get("quiet_hour_start"),
            quiet_hour_end=policy.get("quiet_hour_end"),
            max_discount_percent=policy.get("max_discount_percent"),
            max_retries=policy.get("max_retries"),
            approval_threshold_amount=policy.get("approval_threshold_amount"),
            allowed_channels=policy.get("allowed_channels"),
        )

        # Check auto-retry disabled
        if not policy.get("auto_retry_enabled", True) and action_type in ("retry_now", "retry_delayed"):
            result = GuardrailResult()
            from app.core.circuit_breaker import GuardrailCheck
            result.add(GuardrailCheck(
                rule="auto_retry_disabled",
                passed=False,
                reason="Merchant has disabled automatic retries. Use alternate recovery methods.",
            ))
            return result

        return cb.check(
            action_type=action_type,
            transaction_amount=transaction_amount,
            retry_count=retry_count,
            touchpoints_last_72h=touchpoints_last_72h,
            discount_percent=discount_percent,
            root_cause=root_cause,
        )

    async def update_merchant_policy(
        self,
        db: AsyncSession,
        merchant_id: int,
        updates: dict,
    ) -> dict:
        """
        Update merchant policy rules. Creates new rules or updates existing.

        Returns the full updated policy.
        """
        for rule_type, value in updates.items():
            if value is None:
                continue

            # Check if rule exists
            stmt = select(PolicyRule).where(
                PolicyRule.merchant_id == merchant_id,
                PolicyRule.rule_type == rule_type,
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            value_json = json.dumps(value)

            if existing:
                existing.value_json = value_json
                existing.active = True
            else:
                rule = PolicyRule(
                    merchant_id=merchant_id,
                    rule_type=rule_type,
                    value_json=value_json,
                    active=True,
                )
                db.add(rule)

        await db.flush()
        return await self.get_merchant_policy(db, merchant_id)

    def needs_approval(self, policy: dict, transaction_amount: float, action_type: str) -> bool:
        """Quick check: does this action require human approval per policy?"""
        if action_type in ("escalate_human", "stop"):
            return False
        threshold = policy.get("approval_threshold_amount", 50000.0)
        return transaction_amount >= threshold


# Module-level singleton
policy_engine = PolicyEngine()
