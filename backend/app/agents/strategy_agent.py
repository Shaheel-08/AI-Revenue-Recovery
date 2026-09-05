"""
Strategy Agent — Action selection orchestrator for RecoverOS.

Receives diagnosis → generates candidate actions → scores each via
recovery predictor + utility engine → ranks → applies bandit exploration
→ selects best → generates explanation with confidence score.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.agents.diagnostic_agent import DiagnosisResult
from app.ml.recovery_predictor import recovery_predictor
from app.ml.utility_engine import utility_engine, ActionScore
from app.ml.contextual_bandit import contextual_bandit
from app.models.base import ActionType, RootCause


# Actions that should NOT be offered for certain root causes
_BLOCKED_ACTIONS: dict[str, set[str]] = {
    RootCause.SUSPECTED_FRAUD.value: {
        ActionType.RETRY_NOW.value,
        ActionType.RETRY_DELAYED.value,
        ActionType.OFFER_DISCOUNT.value,
        ActionType.SEND_PAYMENT_LINK.value,
    },
    RootCause.EXPIRED_CARD.value: {
        ActionType.RETRY_NOW.value,  # retrying a dead card is pointless
    },
}


class StrategyResult:
    """Result of strategy agent's action selection."""

    def __init__(
        self,
        recommended_action: str,
        all_scores: list[ActionScore],
        bandit_details: dict,
        explanation: str,
        confidence: float,
        requires_approval: bool = False,
    ):
        self.recommended_action = recommended_action
        self.all_scores = all_scores
        self.bandit_details = bandit_details
        self.explanation = explanation
        self.confidence = confidence
        self.requires_approval = requires_approval

    def to_dict(self) -> dict:
        return {
            "recommended_action": self.recommended_action,
            "all_scores": [s.to_dict() for s in self.all_scores],
            "explanation": self.explanation,
            "confidence": round(self.confidence, 3),
            "requires_approval": self.requires_approval,
        }


class StrategyAgent:
    """
    Orchestrates action selection:
    1. Generate candidate actions (filter by root cause)
    2. Predict P(recovery|action) for each candidate
    3. Score each via utility engine (U = P×V - costs)
    4. Apply contextual bandit for exploration/exploitation balance
    5. Generate plain-language explanation
    """

    def select_action(
        self,
        diagnosis: DiagnosisResult,
        transaction_amount: float,
        payment_method: str = "card",
    ) -> StrategyResult:
        """
        Select the best recovery action given a diagnosis.
        """
        root_cause = diagnosis.classification.root_cause.value
        segment = diagnosis.customer_context.get("segment", "regular")
        ctx = diagnosis.customer_context

        # 1. Determine available actions
        available = self._get_available_actions(root_cause, diagnosis.is_b2b)

        # 2. Predict recovery probability per action
        recovery_probs = recovery_predictor.predict(
            failure_reason=root_cause,
            customer_segment=segment,
            payment_method=payment_method,
            amount=transaction_amount,
            retry_count=diagnosis.retry_count,
            previous_transactions=ctx.get("previous_transactions", 0),
            previous_success_rate=ctx.get("previous_success_rate", 0.5),
            avg_payment_amount=ctx.get("avg_payment_amount", 1000.0),
            customer_lifetime_value=ctx.get("ltv", 5000.0),
            days_since_last_payment=ctx.get("days_since_last_payment", 7),
            actions=available,
        )

        # 3. Score via utility engine
        is_fraud = root_cause == RootCause.SUSPECTED_FRAUD.value
        scores = utility_engine.score_all_actions(
            recovery_probs=recovery_probs,
            payment_value=transaction_amount,
            touchpoints_last_72h=diagnosis.touchpoints_last_72h,
            root_cause=root_cause,
            customer_segment=segment,
            is_fraud_flagged=is_fraud,
        )

        # 4. Apply contextual bandit for exploration
        utility_map = {s.action_type: s.net_expected_revenue for s in scores}
        bandit_action, bandit_details = contextual_bandit.select_action(
            segment=segment,
            utility_scores=utility_map,
            available_actions=available,
        )

        # 5. Determine final action (bandit can override utility ranking)
        # Use bandit selection but validate it's reasonable
        final_action = bandit_action
        final_score = next(
            (s for s in scores if s.action_type == final_action),
            scores[0] if scores else None,
        )

        # If bandit picks something with negative utility, fall back to utility ranking
        if final_score and final_score.net_expected_revenue < 0 and scores:
            best_util = scores[0]
            if best_util.net_expected_revenue > 0:
                final_action = best_util.action_type
                final_score = best_util

        # Mark the final action as recommended
        for s in scores:
            s.is_recommended = (s.action_type == final_action)

        # 6. Check if approval needed
        requires_approval = diagnosis.is_high_value and final_action not in (
            ActionType.ESCALATE_HUMAN.value, ActionType.STOP.value
        )

        # For B2B high-value, consider PTP
        if diagnosis.is_b2b and transaction_amount > 100000:
            final_action = ActionType.PTP_NEGOTIATION.value
            requires_approval = True

        # 7. Generate comprehensive explanation
        explanation = self._generate_explanation(
            final_action=final_action,
            scores=scores,
            diagnosis=diagnosis,
            transaction_amount=transaction_amount,
        )

        confidence = final_score.confidence if final_score else 0.5

        return StrategyResult(
            recommended_action=final_action,
            all_scores=scores,
            bandit_details=bandit_details,
            explanation=explanation,
            confidence=confidence,
            requires_approval=requires_approval,
        )

    def _get_available_actions(self, root_cause: str, is_b2b: bool) -> list[str]:
        """Get actions available for this root cause."""
        all_actions = [a.value for a in ActionType if a != ActionType.STOP]
        blocked = _BLOCKED_ACTIONS.get(root_cause, set())

        available = [a for a in all_actions if a not in blocked]

        # Add PTP for B2B
        if not is_b2b and ActionType.PTP_NEGOTIATION.value in available:
            available.remove(ActionType.PTP_NEGOTIATION.value)

        return available

    def _generate_explanation(
        self,
        final_action: str,
        scores: list[ActionScore],
        diagnosis: DiagnosisResult,
        transaction_amount: float,
    ) -> str:
        """
        Generate a plain-language reasoning trace.

        Example: "Chose WhatsApp payment link because 7/8 of this customer's
        past payments succeeded via UPI, average response time 5.2h, and
        expected net revenue (₹4,200) exceeds retry (₹3,900) and email (₹3,100)."
        """
        ctx = diagnosis.customer_context
        root_cause = diagnosis.classification.root_cause.value
        segment = ctx.get("segment", "regular")
        success_rate = ctx.get("previous_success_rate", 0.5)
        prev_txns = ctx.get("previous_transactions", 0)
        ltv = ctx.get("ltv", 0)
        preferred = ctx.get("preferred_channel", "email")

        action_names = {
            "retry_now": "immediate retry",
            "retry_delayed": "delayed retry",
            "switch_to_upi": "UPI payment method switch",
            "send_payment_link": "payment link",
            "whatsapp_nudge": "WhatsApp nudge",
            "email_reminder": "email reminder",
            "sms_reminder": "SMS reminder",
            "offer_discount": "discount offer",
            "escalate_human": "human escalation",
            "ptp_negotiation": "Promise-to-Pay negotiation",
            "stop": "no further action",
        }

        chosen_name = action_names.get(final_action, final_action)
        chosen_score = next((s for s in scores if s.action_type == final_action), None)

        # Build explanation
        parts = [f"Chose {chosen_name}"]

        # Root cause context
        cause_reasons = {
            "BANK_DOWNTIME": "bank is experiencing downtime — delayed retry waits for recovery",
            "INSUFFICIENT_FUNDS": "customer had insufficient funds",
            "EXPIRED_CARD": "card is expired — alternate payment method needed",
            "AUTH_OTP_FAILURE": "OTP authentication failed — simpler payment flow avoids friction",
            "USER_ABANDONED": "customer abandoned checkout — quick nudge recaptures intent",
            "SUBSCRIPTION_MANDATE_FAILURE": "subscription mandate failed — re-authorization needed",
            "SUSPECTED_FRAUD": "transaction flagged as suspected fraud — requires human review",
            "INVALID_DETAILS": "payment details were invalid — customer needs to re-enter",
            "MERCHANT_INTEGRATION_ERROR": "merchant integration error — technical fix may resolve",
        }
        reason = cause_reasons.get(root_cause, "")
        if reason:
            parts.append(f"because {reason}")

        # Customer history
        if prev_txns > 0:
            success_count = int(prev_txns * success_rate)
            parts.append(
                f"{success_count}/{prev_txns} of this customer's past payments succeeded"
            )

        # Segment context
        if segment == "vip":
            parts.append(f"(VIP customer, LTV ₹{ltv:,.0f})")
        elif segment == "b2b":
            parts.append(f"(B2B customer, LTV ₹{ltv:,.0f})")

        # Revenue comparison
        if chosen_score and len(scores) > 1:
            others = [s for s in scores if s.action_type != final_action and s.net_expected_revenue > 0]
            if others:
                comparisons = []
                for s in others[:2]:
                    name = action_names.get(s.action_type, s.action_type)
                    comparisons.append(f"{name} (₹{s.net_expected_revenue:,.0f})")
                parts.append(
                    f"and expected net revenue (₹{chosen_score.net_expected_revenue:,.0f}) "
                    f"exceeds {' and '.join(comparisons)}"
                )

        explanation = ", ".join(parts) + "."

        # Add confidence note
        if chosen_score:
            explanation += f" Confidence: {chosen_score.confidence*100:.0f}%."

        return explanation


# Module-level singleton
strategy_agent = StrategyAgent()
