"""
Circuit Breaker — Guardrail enforcement for RecoverOS.

Enforces:
- Max touchpoints per 72h window (default: 5)
- Quiet hours (default: 10 PM – 8 AM)
- Max discount cap (default: 15%)
- Fraud-flagged transaction blocking on auto-retry
- Max retry count enforcement

Every blocked action is logged with the specific reason.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from app.core.config import get_settings


class GuardrailCheck:
    """Result of a single guardrail check."""

    def __init__(self, rule: str, passed: bool, reason: str = ""):
        self.rule = rule
        self.passed = passed
        self.reason = reason

    def to_dict(self) -> dict:
        return {"rule": self.rule, "passed": self.passed, "reason": self.reason}


class GuardrailResult:
    """Aggregate result of all guardrail checks."""

    def __init__(self):
        self.checks: list[GuardrailCheck] = []

    @property
    def allowed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def blocked_reasons(self) -> list[str]:
        return [c.reason for c in self.checks if not c.passed]

    def add(self, check: GuardrailCheck) -> None:
        self.checks.append(check)

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "checks": [c.to_dict() for c in self.checks],
        }


class CircuitBreaker:
    """
    Merchant-configurable guardrail system.

    All parameters can be overridden per-merchant via PolicyRules.
    """

    def __init__(
        self,
        max_touchpoints_72h: Optional[int] = None,
        quiet_hour_start: Optional[int] = None,
        quiet_hour_end: Optional[int] = None,
        max_discount_percent: Optional[float] = None,
        max_retries: Optional[int] = None,
        approval_threshold_amount: Optional[float] = None,
        allowed_channels: Optional[list[str]] = None,
    ):
        settings = get_settings()
        self.max_touchpoints_72h = max_touchpoints_72h or settings.max_touchpoints_72h
        self.quiet_hour_start = quiet_hour_start if quiet_hour_start is not None else settings.quiet_hour_start
        self.quiet_hour_end = quiet_hour_end if quiet_hour_end is not None else settings.quiet_hour_end
        self.max_discount_percent = max_discount_percent or settings.max_discount_percent
        self.max_retries = max_retries or settings.max_retries
        self.approval_threshold_amount = approval_threshold_amount or settings.approval_threshold_amount
        self.allowed_channels = allowed_channels or [
            "retry_now", "retry_delayed", "switch_to_upi", "send_payment_link",
            "whatsapp_nudge", "email_reminder", "sms_reminder",
            "offer_discount", "escalate_human", "ptp_negotiation", "stop",
        ]

    def check(
        self,
        action_type: str,
        transaction_amount: float = 0.0,
        retry_count: int = 0,
        touchpoints_last_72h: int = 0,
        discount_percent: float = 0.0,
        root_cause: str = "UNKNOWN",
        current_time: Optional[datetime] = None,
    ) -> GuardrailResult:
        """
        Run all guardrail checks for a proposed action.

        Returns a GuardrailResult with pass/fail for each rule.
        """
        result = GuardrailResult()
        now = current_time or datetime.now()

        # 1. Allowed channel check
        result.add(self._check_allowed_channel(action_type))

        # 2. Quiet hours check (only for contact actions)
        if action_type in ("whatsapp_nudge", "email_reminder", "sms_reminder", "send_payment_link"):
            result.add(self._check_quiet_hours(now))

        # 3. Max touchpoints (circuit breaker)
        if action_type in ("whatsapp_nudge", "email_reminder", "sms_reminder", "send_payment_link"):
            result.add(self._check_max_touchpoints(touchpoints_last_72h))

        # 4. Max retries
        if action_type in ("retry_now", "retry_delayed"):
            result.add(self._check_max_retries(retry_count))

        # 5. Max discount
        if action_type == "offer_discount":
            result.add(self._check_max_discount(discount_percent))

        # 6. Fraud block on auto-retry
        if root_cause == "SUSPECTED_FRAUD" and action_type in ("retry_now", "retry_delayed"):
            result.add(GuardrailCheck(
                rule="fraud_block",
                passed=False,
                reason=f"Auto-retry blocked: transaction flagged as SUSPECTED_FRAUD. "
                       f"Only human escalation is allowed.",
            ))
        else:
            result.add(GuardrailCheck(rule="fraud_block", passed=True, reason="No fraud flag"))

        # 7. High-value approval requirement
        needs_approval = self._check_approval_threshold(transaction_amount, action_type)
        result.add(needs_approval)

        return result

    def needs_approval(self, transaction_amount: float, action_type: str) -> bool:
        """Quick check: does this action require human approval?"""
        if action_type in ("escalate_human", "stop"):
            return False
        return transaction_amount >= self.approval_threshold_amount

    def _check_allowed_channel(self, action_type: str) -> GuardrailCheck:
        if action_type in self.allowed_channels or action_type == "stop":
            return GuardrailCheck(
                rule="allowed_channel",
                passed=True,
                reason=f"Action '{action_type}' is in allowed channels",
            )
        return GuardrailCheck(
            rule="allowed_channel",
            passed=False,
            reason=f"Action '{action_type}' is not in merchant's allowed channels: {self.allowed_channels}",
        )

    def _check_quiet_hours(self, now: datetime) -> GuardrailCheck:
        hour = now.hour
        # Handle overnight quiet hours (e.g., 22:00 - 08:00)
        if self.quiet_hour_start > self.quiet_hour_end:
            in_quiet = hour >= self.quiet_hour_start or hour < self.quiet_hour_end
        else:
            in_quiet = self.quiet_hour_start <= hour < self.quiet_hour_end

        if in_quiet:
            return GuardrailCheck(
                rule="quiet_hours",
                passed=False,
                reason=f"Current time {now.strftime('%H:%M')} is within quiet hours "
                       f"({self.quiet_hour_start}:00 - {self.quiet_hour_end}:00). "
                       f"Contact actions are blocked.",
            )
        return GuardrailCheck(
            rule="quiet_hours",
            passed=True,
            reason=f"Current time {now.strftime('%H:%M')} is outside quiet hours",
        )

    def _check_max_touchpoints(self, touchpoints_last_72h: int) -> GuardrailCheck:
        if touchpoints_last_72h >= self.max_touchpoints_72h:
            return GuardrailCheck(
                rule="max_touchpoints_72h",
                passed=False,
                reason=f"Customer has been contacted {touchpoints_last_72h} times in the last 72h "
                       f"(limit: {self.max_touchpoints_72h}). Circuit breaker triggered.",
            )
        return GuardrailCheck(
            rule="max_touchpoints_72h",
            passed=True,
            reason=f"Touchpoints ({touchpoints_last_72h}) within limit ({self.max_touchpoints_72h})",
        )

    def _check_max_retries(self, retry_count: int) -> GuardrailCheck:
        if retry_count >= self.max_retries:
            return GuardrailCheck(
                rule="max_retries",
                passed=False,
                reason=f"Transaction has been retried {retry_count} times "
                       f"(limit: {self.max_retries}). No more auto-retries allowed.",
            )
        return GuardrailCheck(
            rule="max_retries",
            passed=True,
            reason=f"Retry count ({retry_count}) within limit ({self.max_retries})",
        )

    def _check_max_discount(self, discount_percent: float) -> GuardrailCheck:
        if discount_percent > self.max_discount_percent:
            return GuardrailCheck(
                rule="max_discount",
                passed=False,
                reason=f"Proposed discount ({discount_percent}%) exceeds maximum "
                       f"({self.max_discount_percent}%). Reduce discount or escalate.",
            )
        return GuardrailCheck(
            rule="max_discount",
            passed=True,
            reason=f"Discount ({discount_percent}%) within limit ({self.max_discount_percent}%)",
        )

    def _check_approval_threshold(self, amount: float, action_type: str) -> GuardrailCheck:
        if action_type in ("escalate_human", "stop"):
            return GuardrailCheck(
                rule="approval_threshold",
                passed=True,
                reason="Escalation/stop does not require approval check",
            )
        if amount >= self.approval_threshold_amount:
            return GuardrailCheck(
                rule="approval_threshold",
                passed=True,  # Still passes but flags for approval
                reason=f"Transaction amount ₹{amount:,.0f} exceeds approval threshold "
                       f"₹{self.approval_threshold_amount:,.0f} — human approval required.",
            )
        return GuardrailCheck(
            rule="approval_threshold",
            passed=True,
            reason=f"Amount ₹{amount:,.0f} below approval threshold",
        )


# Default instance
circuit_breaker = CircuitBreaker()
