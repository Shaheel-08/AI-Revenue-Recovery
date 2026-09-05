"""
Root-Cause Failure Classifier for RecoverOS.

Deterministic rule-based classifier that maps Razorpay-style error codes + timing
signals to one of 9 root causes. Each root cause maps to distinct default strategies.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from app.models.base import RootCause


# ── Error code → root cause mapping tables ────────────────────────────────────

# Razorpay-style internal error descriptions to root cause
_ERROR_DESCRIPTION_MAP: dict[str, RootCause] = {
    # Bank/gateway issues
    "bank_server_down": RootCause.BANK_DOWNTIME,
    "gateway_timeout": RootCause.BANK_DOWNTIME,
    "bank_unavailable": RootCause.BANK_DOWNTIME,
    "server_error": RootCause.BANK_DOWNTIME,
    "gateway_error": RootCause.BANK_DOWNTIME,
    "network_error": RootCause.BANK_DOWNTIME,

    # Insufficient funds
    "insufficient_balance": RootCause.INSUFFICIENT_FUNDS,
    "insufficient_funds": RootCause.INSUFFICIENT_FUNDS,
    "low_balance": RootCause.INSUFFICIENT_FUNDS,
    "exceeds_limit": RootCause.INSUFFICIENT_FUNDS,

    # Card issues
    "expired_card": RootCause.EXPIRED_CARD,
    "card_expired": RootCause.EXPIRED_CARD,
    "invalid_expiry": RootCause.EXPIRED_CARD,
    "card_declined": RootCause.EXPIRED_CARD,

    # OTP/Auth
    "otp_failed": RootCause.AUTH_OTP_FAILURE,
    "otp_expired": RootCause.AUTH_OTP_FAILURE,
    "authentication_failed": RootCause.AUTH_OTP_FAILURE,
    "3ds_failed": RootCause.AUTH_OTP_FAILURE,
    "otp_attempts_exceeded": RootCause.AUTH_OTP_FAILURE,

    # Invalid details
    "invalid_card_number": RootCause.INVALID_DETAILS,
    "invalid_cvv": RootCause.INVALID_DETAILS,
    "invalid_vpa": RootCause.INVALID_DETAILS,
    "invalid_account": RootCause.INVALID_DETAILS,

    # User abandoned
    "payment_cancelled": RootCause.USER_ABANDONED,
    "customer_cancelled": RootCause.USER_ABANDONED,
    "session_expired": RootCause.USER_ABANDONED,
    "checkout_abandoned": RootCause.USER_ABANDONED,

    # Merchant integration
    "api_error": RootCause.MERCHANT_INTEGRATION_ERROR,
    "invalid_request": RootCause.MERCHANT_INTEGRATION_ERROR,
    "webhook_failure": RootCause.MERCHANT_INTEGRATION_ERROR,
    "configuration_error": RootCause.MERCHANT_INTEGRATION_ERROR,

    # Subscription/mandate
    "mandate_failed": RootCause.SUBSCRIPTION_MANDATE_FAILURE,
    "mandate_expired": RootCause.SUBSCRIPTION_MANDATE_FAILURE,
    "emandate_failed": RootCause.SUBSCRIPTION_MANDATE_FAILURE,
    "auto_debit_failed": RootCause.SUBSCRIPTION_MANDATE_FAILURE,
    "recurring_failed": RootCause.SUBSCRIPTION_MANDATE_FAILURE,

    # Fraud
    "suspected_fraud": RootCause.SUSPECTED_FRAUD,
    "risk_check_failed": RootCause.SUSPECTED_FRAUD,
    "blocked_by_risk": RootCause.SUSPECTED_FRAUD,
    "velocity_check_failed": RootCause.SUSPECTED_FRAUD,
}

# Razorpay top-level error codes
_ERROR_CODE_HINTS: dict[str, RootCause] = {
    "BAD_REQUEST_ERROR": RootCause.INVALID_DETAILS,
    "GATEWAY_ERROR": RootCause.BANK_DOWNTIME,
    "SERVER_ERROR": RootCause.MERCHANT_INTEGRATION_ERROR,
}

# Timing-based heuristics
_BANK_DOWNTIME_HOURS = {0, 1, 2, 3, 4, 5, 23}  # Late night / early morning


class FailureClassification:
    """Result of root-cause classification."""

    def __init__(
        self,
        root_cause: RootCause,
        confidence: float,
        reasoning: str,
        is_recoverable: bool = True,
        recommended_urgency: str = "normal",
    ):
        self.root_cause = root_cause
        self.confidence = min(max(confidence, 0.0), 1.0)
        self.reasoning = reasoning
        self.is_recoverable = is_recoverable
        self.recommended_urgency = recommended_urgency

    def to_dict(self) -> dict:
        return {
            "root_cause": self.root_cause.value,
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
            "is_recoverable": self.is_recoverable,
            "recommended_urgency": self.recommended_urgency,
        }


class FailureClassifier:
    """
    Deterministic root-cause classifier for payment failures.

    Maps Razorpay-style error codes + timing signals to 9 root causes.
    Uses a priority cascade: exact description match → error code hint → timing heuristics.
    """

    # Recoverability per root cause
    _RECOVERABILITY: dict[RootCause, bool] = {
        RootCause.BANK_DOWNTIME: True,
        RootCause.INSUFFICIENT_FUNDS: True,
        RootCause.EXPIRED_CARD: True,
        RootCause.AUTH_OTP_FAILURE: True,
        RootCause.INVALID_DETAILS: True,
        RootCause.USER_ABANDONED: True,
        RootCause.MERCHANT_INTEGRATION_ERROR: True,
        RootCause.SUBSCRIPTION_MANDATE_FAILURE: True,
        RootCause.SUSPECTED_FRAUD: False,
        RootCause.UNKNOWN: True,
    }

    # Urgency level per root cause
    _URGENCY: dict[RootCause, str] = {
        RootCause.BANK_DOWNTIME: "low",          # wait for bank to recover
        RootCause.INSUFFICIENT_FUNDS: "normal",   # wait for salary
        RootCause.EXPIRED_CARD: "normal",         # needs customer action
        RootCause.AUTH_OTP_FAILURE: "high",        # retry quickly
        RootCause.INVALID_DETAILS: "normal",       # needs correction
        RootCause.USER_ABANDONED: "high",          # nudge ASAP before intent fades
        RootCause.MERCHANT_INTEGRATION_ERROR: "low",  # needs dev fix
        RootCause.SUBSCRIPTION_MANDATE_FAILURE: "normal",
        RootCause.SUSPECTED_FRAUD: "critical",     # block everything
        RootCause.UNKNOWN: "normal",
    }

    def classify(
        self,
        failure_code: Optional[str] = None,
        failure_reason: Optional[str] = None,
        payment_method: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        subscription_type: Optional[str] = None,
        retry_count: int = 0,
        amount: float = 0.0,
    ) -> FailureClassification:
        """
        Classify a payment failure into a root cause.

        Priority cascade:
        1. Direct failure_reason match (highest confidence)
        2. Failure description keyword match
        3. Error code hint
        4. Timing-based heuristics
        5. Fallback to UNKNOWN
        """
        # Normalize inputs
        reason_lower = (failure_reason or "").lower().strip().replace(" ", "_")
        code_upper = (failure_code or "").upper().strip()

        # 1. Direct match on failure_reason as root cause enum
        for rc in RootCause:
            if reason_lower == rc.value.lower():
                return FailureClassification(
                    root_cause=rc,
                    confidence=0.95,
                    reasoning=f"Direct match: failure reason '{failure_reason}' maps to {rc.value}",
                    is_recoverable=self._RECOVERABILITY.get(rc, True),
                    recommended_urgency=self._URGENCY.get(rc, "normal"),
                )

        # 2. Keyword match in error description map
        for keyword, rc in _ERROR_DESCRIPTION_MAP.items():
            if keyword in reason_lower:
                confidence = 0.88
                reasoning = (
                    f"Keyword match: '{keyword}' found in failure reason "
                    f"'{failure_reason}' → {rc.value}"
                )
                return FailureClassification(
                    root_cause=rc,
                    confidence=confidence,
                    reasoning=reasoning,
                    is_recoverable=self._RECOVERABILITY.get(rc, True),
                    recommended_urgency=self._URGENCY.get(rc, "normal"),
                )

        # 3. Subscription-specific check
        if subscription_type and subscription_type in ("monthly", "quarterly", "annual"):
            if "mandate" in reason_lower or "recurring" in reason_lower or "auto_debit" in reason_lower:
                return FailureClassification(
                    root_cause=RootCause.SUBSCRIPTION_MANDATE_FAILURE,
                    confidence=0.85,
                    reasoning=(
                        f"Subscription type '{subscription_type}' with mandate-related "
                        f"failure reason → SUBSCRIPTION_MANDATE_FAILURE"
                    ),
                    is_recoverable=True,
                    recommended_urgency="normal",
                )

        # 4. Error code hint
        if code_upper in _ERROR_CODE_HINTS:
            rc = _ERROR_CODE_HINTS[code_upper]
            # Apply timing heuristic for GATEWAY_ERROR
            if code_upper == "GATEWAY_ERROR" and timestamp and timestamp.hour in _BANK_DOWNTIME_HOURS:
                rc = RootCause.BANK_DOWNTIME
                confidence = 0.78
                reasoning = (
                    f"Gateway error at {timestamp.strftime('%H:%M')} (late-night/early-morning) "
                    f"suggests bank downtime maintenance window"
                )
            else:
                confidence = 0.65
                reasoning = f"Error code '{code_upper}' suggests {rc.value} (lower confidence — no specific description match)"

            return FailureClassification(
                root_cause=rc,
                confidence=confidence,
                reasoning=reasoning,
                is_recoverable=self._RECOVERABILITY.get(rc, True),
                recommended_urgency=self._URGENCY.get(rc, "normal"),
            )

        # 5. Timing heuristic as last resort
        if timestamp and timestamp.hour in _BANK_DOWNTIME_HOURS and code_upper in ("GATEWAY_ERROR", "SERVER_ERROR", ""):
            return FailureClassification(
                root_cause=RootCause.BANK_DOWNTIME,
                confidence=0.55,
                reasoning=(
                    f"No specific failure reason, but failure occurred at "
                    f"{timestamp.strftime('%H:%M')} during typical bank maintenance hours"
                ),
                is_recoverable=True,
                recommended_urgency="low",
            )

        # 6. Fallback
        return FailureClassification(
            root_cause=RootCause.UNKNOWN,
            confidence=0.30,
            reasoning=f"Could not classify: code='{failure_code}', reason='{failure_reason}'",
            is_recoverable=True,
            recommended_urgency="normal",
        )


# Module-level singleton
failure_classifier = FailureClassifier()
