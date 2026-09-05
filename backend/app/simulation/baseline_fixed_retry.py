"""
Baseline Fixed Retry Strategy for RecoverOS.

Simple 24h-interval retry, up to 3 retries, same channel, no diagnosis.
Used as the comparison baseline for the batch evaluator.
"""
from __future__ import annotations

import numpy as np
from typing import Any


class FixedRetryBaseline:
    """
    Fixed retry baseline:
    - Retries every 24h
    - Maximum 3 retries
    - Same payment method each time
    - No diagnosis, no channel switching, no discounts
    - No guardrails (may produce duplicate charges)
    """

    def __init__(self, max_retries: int = 3, retry_interval_hours: float = 24.0):
        self.max_retries = max_retries
        self.retry_interval_hours = retry_interval_hours

    def process_transaction(
        self,
        rng: np.random.Generator,
        transaction: dict[str, Any],
    ) -> dict:
        """
        Process a single transaction using fixed retry strategy.

        Returns outcome dict with recovery status and costs.
        """
        failure_reason = transaction.get("failure_reason", "UNKNOWN")
        amount = transaction.get("amount", 0)
        retry_count = 0
        recovered = False
        total_cost = 0.0
        total_messages = 0
        duplicate_charges = 0
        recovery_time_hours = 0.0

        # Fixed retry probabilities (much lower than intelligent approach)
        # These don't account for failure type at all
        base_retry_prob = self._get_naive_retry_prob(failure_reason)

        for attempt in range(self.max_retries):
            retry_count += 1

            # Fixed retry probability degrades linearly
            prob = base_retry_prob * (1.0 - 0.2 * attempt)

            if rng.random() < prob:
                recovered = True
                recovery_time_hours = self.retry_interval_hours * attempt + rng.uniform(0.5, 12)
                break

            # Small chance of duplicate charge (no idempotency in baseline)
            if rng.random() < 0.005:  # 0.5% per retry
                duplicate_charges += 1

            # Send a generic email each retry (fixed strategy = one channel)
            total_messages += 1
            total_cost += 0.10  # email cost

        revenue_recovered = amount if recovered else 0.0

        return {
            "recovered": recovered,
            "revenue_recovered": revenue_recovered,
            "cost": total_cost,
            "retry_count": retry_count,
            "message_count": total_messages,
            "duplicate_charges": duplicate_charges,
            "recovery_time_hours": recovery_time_hours,
            "action_taken": "retry_now",
        }

    def _get_naive_retry_prob(self, failure_reason: str) -> float:
        """
        Naive retry probability — doesn't adapt to failure type.
        This is intentionally worse than RecoverOS's intelligent approach.
        """
        # Fixed retry only works well for transient issues
        probs = {
            "BANK_DOWNTIME": 0.35,          # some chance
            "INSUFFICIENT_FUNDS": 0.12,      # low — still no money
            "EXPIRED_CARD": 0.03,            # card still expired!
            "AUTH_OTP_FAILURE": 0.18,         # OTP might work second time
            "INVALID_DETAILS": 0.05,         # details still wrong
            "USER_ABANDONED": 0.08,          # user already left
            "MERCHANT_INTEGRATION_ERROR": 0.25,  # might be fixed
            "SUBSCRIPTION_MANDATE_FAILURE": 0.10,  # mandate still invalid
            "SUSPECTED_FRAUD": 0.02,          # should never retry!
        }
        return probs.get(failure_reason, 0.10)


baseline_strategy = FixedRetryBaseline()
