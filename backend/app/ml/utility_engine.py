"""
Utility / Economics Engine for RecoverOS.

Implements: U(action) = P(recovery|action) × payment_value
                        − comm_cost(action)
                        − discount_cost(action)
                        − fatigue_cost(customer, action)
                        − risk_cost(action)

Every action candidate gets scored. The engine can justify *not* discounting
a customer who has a high baseline pay-anyway probability.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from app.models.base import ActionType, RootCause


# ── Cost Tables ──────────────────────────────────────────────────────────────

COMM_COST: dict[str, float] = {
    ActionType.RETRY_NOW.value: 0.0,
    ActionType.RETRY_DELAYED.value: 0.0,
    ActionType.SWITCH_TO_UPI.value: 0.0,
    ActionType.SEND_PAYMENT_LINK.value: 0.50,
    ActionType.WHATSAPP_NUDGE.value: 1.50,
    ActionType.EMAIL_REMINDER.value: 0.10,
    ActionType.SMS_REMINDER.value: 0.25,
    ActionType.OFFER_DISCOUNT.value: 0.10,  # comm cost only; discount is separate
    ActionType.ESCALATE_HUMAN.value: 50.00,
    ActionType.PTP_NEGOTIATION.value: 30.00,
    ActionType.STOP.value: 0.0,
}

# Default discount percentages per offer tier
DEFAULT_DISCOUNT_PCT = 10.0  # 10% default discount


@dataclass
class ActionScore:
    """Full economic breakdown of a candidate action."""
    action_type: str
    recovery_probability: float
    payment_value: float
    expected_gross_revenue: float
    communication_cost: float
    discount_cost: float
    fatigue_cost: float
    risk_cost: float
    net_expected_revenue: float
    is_recommended: bool = False
    explanation: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type,
            "recovery_probability": round(self.recovery_probability, 4),
            "expected_revenue": round(self.expected_gross_revenue, 2),
            "communication_cost": round(self.communication_cost, 2),
            "discount_cost": round(self.discount_cost, 2),
            "fatigue_cost": round(self.fatigue_cost, 2),
            "risk_cost": round(self.risk_cost, 2),
            "net_expected_revenue": round(self.net_expected_revenue, 2),
            "is_recommended": self.is_recommended,
            "explanation": self.explanation,
            "confidence": round(self.confidence, 3),
        }


class UtilityEngine:
    """
    Computes U(action) = P(recovery|action) × value − costs.

    Can justify NOT discounting by comparing: if baseline P(recovery) is high,
    discount adds cost without proportional benefit.
    """

    def __init__(
        self,
        default_discount_pct: float = DEFAULT_DISCOUNT_PCT,
    ):
        self.default_discount_pct = default_discount_pct

    def score_action(
        self,
        action_type: str,
        recovery_probability: float,
        payment_value: float,
        touchpoints_last_72h: int = 0,
        root_cause: str = "UNKNOWN",
        customer_segment: str = "regular",
        discount_pct: Optional[float] = None,
        is_fraud_flagged: bool = False,
    ) -> ActionScore:
        """
        Score a single candidate action.

        Args:
            action_type: e.g., "retry_now", "offer_discount"
            recovery_probability: P(recovery | this action)
            payment_value: transaction amount in INR
            touchpoints_last_72h: number of contacts in last 72h
            root_cause: classified failure root cause
            customer_segment: customer segment label
            discount_pct: override discount percentage (uses default if None)
            is_fraud_flagged: whether the transaction is fraud-suspected
        """
        # 1. Communication cost
        comm_cost = COMM_COST.get(action_type, 0.0)

        # 2. Discount cost
        discount_cost = 0.0
        if action_type == ActionType.OFFER_DISCOUNT.value:
            pct = discount_pct if discount_pct is not None else self.default_discount_pct
            discount_cost = payment_value * pct / 100.0

        # 3. Fatigue cost — exponential increase with touchpoints
        fatigue_cost = self._compute_fatigue_cost(
            action_type, touchpoints_last_72h, payment_value
        )

        # 4. Risk cost — fraud-flagged transactions get massive penalty on auto-actions
        risk_cost = self._compute_risk_cost(
            action_type, root_cause, is_fraud_flagged, payment_value
        )

        # 5. Expected gross revenue
        effective_value = payment_value - discount_cost
        expected_gross = recovery_probability * effective_value

        # 6. Net expected revenue
        net_expected = expected_gross - comm_cost - fatigue_cost - risk_cost

        # Confidence based on data quality signals
        confidence = self._compute_confidence(
            recovery_probability, action_type, root_cause
        )

        return ActionScore(
            action_type=action_type,
            recovery_probability=recovery_probability,
            payment_value=payment_value,
            expected_gross_revenue=expected_gross,
            communication_cost=comm_cost,
            discount_cost=discount_cost,
            fatigue_cost=fatigue_cost,
            risk_cost=risk_cost,
            net_expected_revenue=net_expected,
            confidence=confidence,
        )

    def score_all_actions(
        self,
        recovery_probs: dict[str, float],
        payment_value: float,
        touchpoints_last_72h: int = 0,
        root_cause: str = "UNKNOWN",
        customer_segment: str = "regular",
        is_fraud_flagged: bool = False,
        discount_pct: Optional[float] = None,
    ) -> list[ActionScore]:
        """
        Score all candidate actions and rank by net expected revenue.

        Returns sorted list (best first) with the top action marked as recommended.
        """
        scores = []
        for action_type, prob in recovery_probs.items():
            if action_type == ActionType.STOP.value:
                # STOP has zero revenue but also zero cost — baseline comparator
                scores.append(ActionScore(
                    action_type=action_type,
                    recovery_probability=0.0,
                    payment_value=payment_value,
                    expected_gross_revenue=0.0,
                    communication_cost=0.0,
                    discount_cost=0.0,
                    fatigue_cost=0.0,
                    risk_cost=0.0,
                    net_expected_revenue=0.0,
                    explanation="No action taken — baseline comparator",
                ))
                continue

            score = self.score_action(
                action_type=action_type,
                recovery_probability=prob,
                payment_value=payment_value,
                touchpoints_last_72h=touchpoints_last_72h,
                root_cause=root_cause,
                customer_segment=customer_segment,
                discount_pct=discount_pct,
                is_fraud_flagged=is_fraud_flagged,
            )
            scores.append(score)

        # Sort by net expected revenue (descending)
        scores.sort(key=lambda s: s.net_expected_revenue, reverse=True)

        # Mark the best as recommended
        if scores and scores[0].net_expected_revenue > 0:
            scores[0].is_recommended = True

        # Generate explanations
        for i, score in enumerate(scores):
            score.explanation = self._generate_explanation(
                score, scores, payment_value, root_cause, customer_segment
            )

        return scores

    def _compute_fatigue_cost(
        self,
        action_type: str,
        touchpoints_last_72h: int,
        payment_value: float,
    ) -> float:
        """
        Fatigue cost increases exponentially with touchpoint count.
        Contact actions (WhatsApp, email, SMS) are affected most.
        """
        contact_actions = {
            ActionType.WHATSAPP_NUDGE.value,
            ActionType.EMAIL_REMINDER.value,
            ActionType.SMS_REMINDER.value,
            ActionType.SEND_PAYMENT_LINK.value,
        }

        if action_type not in contact_actions:
            return 0.0

        if touchpoints_last_72h == 0:
            return 0.0

        # Exponential fatigue: cost = base × e^(0.5 × touchpoints)
        # Capped at 5% of payment value
        base = 2.0
        fatigue = base * math.exp(0.5 * touchpoints_last_72h)
        return min(fatigue, payment_value * 0.05)

    def _compute_risk_cost(
        self,
        action_type: str,
        root_cause: str,
        is_fraud_flagged: bool,
        payment_value: float,
    ) -> float:
        """
        Risk cost penalizes auto-retry actions on fraud-flagged transactions.
        """
        auto_charge_actions = {
            ActionType.RETRY_NOW.value,
            ActionType.RETRY_DELAYED.value,
        }

        if is_fraud_flagged or root_cause == RootCause.SUSPECTED_FRAUD.value:
            if action_type in auto_charge_actions:
                return payment_value * 2.0  # Massive penalty → effectively blocks
            elif action_type != ActionType.ESCALATE_HUMAN.value and action_type != ActionType.STOP.value:
                return payment_value * 0.5  # Moderate penalty on non-escalation actions

        # Small risk cost for retry actions (general double-charge risk)
        if action_type in auto_charge_actions:
            return payment_value * 0.001  # 0.1% risk premium

        return 0.0

    def _compute_confidence(
        self,
        recovery_probability: float,
        action_type: str,
        root_cause: str,
    ) -> float:
        """Confidence score reflecting how certain we are about the prediction."""
        # Higher confidence when root cause is well-understood
        cause_confidence = {
            RootCause.BANK_DOWNTIME.value: 0.85,
            RootCause.INSUFFICIENT_FUNDS.value: 0.80,
            RootCause.EXPIRED_CARD.value: 0.90,
            RootCause.AUTH_OTP_FAILURE.value: 0.75,
            RootCause.USER_ABANDONED.value: 0.70,
            RootCause.SUBSCRIPTION_MANDATE_FAILURE.value: 0.80,
            RootCause.SUSPECTED_FRAUD.value: 0.85,
            RootCause.INVALID_DETAILS.value: 0.75,
            RootCause.MERCHANT_INTEGRATION_ERROR.value: 0.70,
        }
        base = cause_confidence.get(root_cause, 0.50)

        # Extreme probabilities are more confident
        prob_factor = 1.0 - 2.0 * abs(recovery_probability - 0.5)
        base *= (0.8 + 0.2 * prob_factor)

        return min(max(base, 0.1), 0.98)

    def _generate_explanation(
        self,
        score: ActionScore,
        all_scores: list[ActionScore],
        payment_value: float,
        root_cause: str,
        customer_segment: str,
    ) -> str:
        """Generate a plain-language explanation for the action score."""
        action_names = {
            "retry_now": "immediate retry",
            "retry_delayed": "delayed retry",
            "switch_to_upi": "UPI payment method switch",
            "send_payment_link": "payment link",
            "whatsapp_nudge": "WhatsApp nudge",
            "email_reminder": "email reminder",
            "sms_reminder": "SMS reminder",
            "offer_discount": f"discount offer ({self.default_discount_pct}%)",
            "escalate_human": "human escalation",
            "ptp_negotiation": "Promise-to-Pay negotiation",
            "stop": "no further action",
        }

        action_name = action_names.get(score.action_type, score.action_type)
        prob_pct = score.recovery_probability * 100

        if score.is_recommended:
            # Explain why this is the best choice
            if len(all_scores) > 1:
                runner_up = all_scores[1]
                runner_up_name = action_names.get(runner_up.action_type, runner_up.action_type)
                delta = score.net_expected_revenue - runner_up.net_expected_revenue

                explanation = (
                    f"Chose {action_name} because recovery probability is {prob_pct:.0f}% "
                    f"with expected net revenue ₹{score.net_expected_revenue:,.0f}, "
                    f"which is ₹{delta:,.0f} more than the next best option ({runner_up_name} "
                    f"at ₹{runner_up.net_expected_revenue:,.0f})."
                )
            else:
                explanation = (
                    f"Chose {action_name} with {prob_pct:.0f}% recovery probability "
                    f"and expected net revenue ₹{score.net_expected_revenue:,.0f}."
                )

            # Add root-cause context
            cause_context = {
                "BANK_DOWNTIME": " Bank is likely to recover — delayed retry capitalizes on uptime.",
                "INSUFFICIENT_FUNDS": " Timing near salary cycle improves recovery odds.",
                "EXPIRED_CARD": " Card is expired — alternate payment method avoids the same failure.",
                "AUTH_OTP_FAILURE": " OTP friction avoided by switching to a simpler flow.",
                "USER_ABANDONED": " Quick nudge recaptures fading purchase intent.",
                "SUSPECTED_FRAUD": " Fraud flag requires human review — auto-actions blocked.",
            }
            explanation += cause_context.get(root_cause, "")

            # Justify NOT discounting if discount wasn't chosen
            if score.action_type != ActionType.OFFER_DISCOUNT.value:
                discount_scores = [s for s in all_scores if s.action_type == ActionType.OFFER_DISCOUNT.value]
                if discount_scores:
                    ds = discount_scores[0]
                    if ds.recovery_probability > 0.3:
                        explanation += (
                            f" Discount was not chosen despite {ds.recovery_probability*100:.0f}% recovery "
                            f"probability because the discount cost (₹{ds.discount_cost:,.0f}) reduces "
                            f"net revenue to ₹{ds.net_expected_revenue:,.0f}."
                        )

            return explanation
        else:
            return (
                f"{action_name.capitalize()}: {prob_pct:.0f}% recovery probability, "
                f"net expected revenue ₹{score.net_expected_revenue:,.0f}"
            )


# Module-level singleton
utility_engine = UtilityEngine()
