"""
What-If Simulator for RecoverOS.

For any transaction, evaluates all candidate actions and returns the full
ranked comparison table with recovery_probability, expected_revenue, cost,
and net_expected_revenue.
"""
from __future__ import annotations

from app.ml.failure_classifier import failure_classifier
from app.ml.recovery_predictor import recovery_predictor
from app.ml.utility_engine import utility_engine, ActionScore
from app.models.base import ActionType


def simulate_whatif(
    failure_reason: str,
    amount: float,
    customer_segment: str = "regular",
    payment_method: str = "card",
    retry_count: int = 0,
    previous_success_rate: float = 0.5,
    previous_transactions: int = 5,
    customer_lifetime_value: float = 5000.0,
    days_since_last_payment: int = 7,
    touchpoints_last_72h: int = 0,
    hour_of_day: int = 12,
    day_of_month: int = 15,
) -> list[dict]:
    """
    Evaluate all candidate actions for a transaction and return ranked results.
    Used by both the API what-if endpoint and the batch evaluator.
    """
    # Get recovery probabilities for all actions
    actions = [a.value for a in ActionType if a != ActionType.STOP]
    recovery_probs = recovery_predictor.predict(
        failure_reason=failure_reason,
        customer_segment=customer_segment,
        payment_method=payment_method,
        amount=amount,
        retry_count=retry_count,
        previous_transactions=previous_transactions,
        previous_success_rate=previous_success_rate,
        avg_payment_amount=amount,
        customer_lifetime_value=customer_lifetime_value,
        days_since_last_payment=days_since_last_payment,
        hour_of_day=hour_of_day,
        day_of_month=day_of_month,
        actions=actions,
    )

    # Score via utility engine
    is_fraud = failure_reason == "SUSPECTED_FRAUD"
    scores = utility_engine.score_all_actions(
        recovery_probs=recovery_probs,
        payment_value=amount,
        touchpoints_last_72h=touchpoints_last_72h,
        root_cause=failure_reason,
        customer_segment=customer_segment,
        is_fraud_flagged=is_fraud,
    )

    return [s.to_dict() for s in scores]
