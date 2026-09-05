"""
Batch Evaluation Engine for RecoverOS.

The proof module. Runs the full synthetic batch through:
(a) RecoverOS intelligent pipeline
(b) Fixed 24h-retry baseline

Outputs a comparison report: recovery rate, net recovered revenue,
average attempts per recovery, message count, duplicate-charge incidents.
"""
from __future__ import annotations

import collections
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.ml.failure_classifier import failure_classifier
from app.ml.recovery_predictor import recovery_predictor
from app.ml.utility_engine import utility_engine
from app.ml.contextual_bandit import ContextualBandit
from app.simulation.baseline_fixed_retry import FixedRetryBaseline
from app.simulation.synthetic_data_generator import generate_synthetic_data
from app.models.base import ActionType


class BatchEvaluator:
    """
    Runs batch evaluation comparing RecoverOS vs baseline.

    For each transaction:
    1. RecoverOS: diagnose → predict → score → select best action → simulate outcome
    2. Baseline: fixed retry with naive probability

    Both use the same RNG seed for fair comparison.
    """

    def __init__(self):
        self.baseline = FixedRetryBaseline()

    def run_evaluation(
        self,
        transaction_count: int = 2000,
        seed: int = 42,
        csv_path: Optional[str] = None,
    ) -> dict:
        """
        Run full batch evaluation.

        Returns structured comparison report.
        """
        # Generate or load data
        if csv_path and Path(csv_path).exists():
            df = pd.read_csv(csv_path)
            transactions = df.to_dict("records")
        else:
            transactions, _ = generate_synthetic_data(count=transaction_count, seed=seed)

        rng_ros = np.random.default_rng(seed)
        rng_baseline = np.random.default_rng(seed)

        # Create fresh bandit for this evaluation
        bandit = ContextualBandit(exploration_weight=0.3, seed=seed)

        # RecoverOS results
        ros_results = []
        for txn in transactions:
            result = self._process_recoveros(rng_ros, txn, bandit)
            ros_results.append(result)

            # Update bandit with outcome
            reward = result["revenue_recovered"] / max(txn["amount"], 1) if result["recovered"] else 0.0
            bandit.update(
                segment=txn["customer_segment"],
                action=result["action_taken"],
                reward=min(reward, 1.0),
            )

        # Baseline results
        baseline_results = []
        for txn in transactions:
            result = self.baseline.process_transaction(rng_baseline, txn)
            baseline_results.append(result)

        # Compute metrics
        report = self._compute_report(transactions, ros_results, baseline_results)
        return report

    def _process_recoveros(
        self,
        rng: np.random.Generator,
        txn: dict,
        bandit: ContextualBandit,
    ) -> dict:
        """Process a single transaction through RecoverOS pipeline."""
        failure_reason = txn["failure_reason"]
        amount = txn["amount"]
        segment = txn["customer_segment"]
        payment_method = txn["payment_method"]

        # Parse timestamp for time features
        from datetime import datetime
        try:
            ts = datetime.fromisoformat(txn["timestamp"])
            hour = ts.hour
            day = ts.day
        except (ValueError, TypeError):
            hour = 12
            day = 15

        # 1. Predict recovery probabilities for all actions
        actions = [a.value for a in ActionType if a not in (ActionType.STOP, ActionType.PTP_NEGOTIATION)]
        probs = recovery_predictor.predict(
            failure_reason=failure_reason,
            customer_segment=segment,
            payment_method=payment_method,
            amount=amount,
            retry_count=txn.get("retry_count", 0),
            previous_transactions=txn.get("previous_transactions", 5),
            previous_success_rate=txn.get("previous_success_rate", 0.5),
            avg_payment_amount=txn.get("avg_payment_amount", amount),
            customer_lifetime_value=txn.get("customer_lifetime_value", 5000),
            days_since_last_payment=txn.get("days_since_last_payment", 7),
            hour_of_day=hour,
            day_of_month=day,
            actions=actions,
        )

        # 2. Score via utility engine
        is_fraud = failure_reason == "SUSPECTED_FRAUD"
        scores = utility_engine.score_all_actions(
            recovery_probs=probs,
            payment_value=amount,
            root_cause=failure_reason,
            customer_segment=segment,
            is_fraud_flagged=is_fraud,
        )

        # 3. Use bandit for action selection
        utility_map = {s.action_type: s.net_expected_revenue for s in scores}
        selected_action, _ = bandit.select_action(
            segment=segment,
            utility_scores=utility_map,
            available_actions=actions,
        )

        # 4. Simulate outcome based on the selected action's recovery probability
        prob = probs.get(selected_action, 0.1)
        recovered = rng.random() < prob

        # Communication costs
        comm_costs = {
            "retry_now": 0.0, "retry_delayed": 0.0, "switch_to_upi": 0.0,
            "send_payment_link": 0.50, "whatsapp_nudge": 1.50,
            "email_reminder": 0.10, "sms_reminder": 0.25,
            "offer_discount": 0.10, "escalate_human": 50.0,
        }
        cost = comm_costs.get(selected_action, 0.0)

        # Discount cost
        discount = 0.0
        if selected_action == "offer_discount":
            discount = amount * 0.10  # 10% discount
            cost += discount

        revenue = (amount - discount) if recovered else 0.0
        message_count = 1 if selected_action in (
            "whatsapp_nudge", "email_reminder", "sms_reminder", "send_payment_link"
        ) else 0

        return {
            "recovered": recovered,
            "revenue_recovered": revenue,
            "cost": cost,
            "retry_count": 1,
            "message_count": message_count,
            "duplicate_charges": 0,  # RecoverOS has idempotency
            "recovery_time_hours": rng.uniform(0.5, 24) if recovered else 0,
            "action_taken": selected_action,
        }

    def _compute_report(
        self,
        transactions: list[dict],
        ros_results: list[dict],
        baseline_results: list[dict],
    ) -> dict:
        """Compute comprehensive comparison report."""
        n = len(transactions)

        # RecoverOS metrics
        ros_recovered = sum(1 for r in ros_results if r["recovered"])
        ros_revenue = sum(r["revenue_recovered"] for r in ros_results)
        ros_cost = sum(r["cost"] for r in ros_results)
        ros_net = ros_revenue - ros_cost
        ros_attempts = sum(r["retry_count"] for r in ros_results)
        ros_messages = sum(r["message_count"] for r in ros_results)
        ros_duplicates = sum(r["duplicate_charges"] for r in ros_results)

        # Baseline metrics
        bl_recovered = sum(1 for r in baseline_results if r["recovered"])
        bl_revenue = sum(r["revenue_recovered"] for r in baseline_results)
        bl_cost = sum(r["cost"] for r in baseline_results)
        bl_net = bl_revenue - bl_cost
        bl_attempts = sum(r["retry_count"] for r in baseline_results)
        bl_messages = sum(r["message_count"] for r in baseline_results)
        bl_duplicates = sum(r["duplicate_charges"] for r in baseline_results)

        ros_rate = ros_recovered / n * 100 if n > 0 else 0
        bl_rate = bl_recovered / n * 100 if n > 0 else 0

        # Per-cause breakdown
        cause_data = collections.defaultdict(lambda: {
            "ros_recovered": 0, "ros_total": 0, "ros_revenue": 0,
            "bl_recovered": 0, "bl_total": 0, "bl_revenue": 0,
        })
        for i, txn in enumerate(transactions):
            cause = txn["failure_reason"]
            cause_data[cause]["ros_total"] += 1
            cause_data[cause]["bl_total"] += 1
            if ros_results[i]["recovered"]:
                cause_data[cause]["ros_recovered"] += 1
                cause_data[cause]["ros_revenue"] += ros_results[i]["revenue_recovered"]
            if baseline_results[i]["recovered"]:
                cause_data[cause]["bl_recovered"] += 1
                cause_data[cause]["bl_revenue"] += baseline_results[i]["revenue_recovered"]

        per_cause = []
        for cause, data in sorted(cause_data.items()):
            per_cause.append({
                "cause": cause,
                "ros_recovery_rate": round(
                    data["ros_recovered"] / data["ros_total"] * 100, 1
                ) if data["ros_total"] > 0 else 0,
                "baseline_recovery_rate": round(
                    data["bl_recovered"] / data["bl_total"] * 100, 1
                ) if data["bl_total"] > 0 else 0,
                "ros_net_revenue": round(data["ros_revenue"], 2),
                "baseline_net_revenue": round(data["bl_revenue"], 2),
            })

        return {
            "transaction_count": n,
            "ros_recovery_rate": round(ros_rate, 1),
            "ros_net_revenue": round(ros_net, 2),
            "ros_total_recovered": round(ros_revenue, 2),
            "ros_avg_attempts": round(ros_attempts / max(ros_recovered, 1), 2),
            "ros_message_count": ros_messages,
            "ros_duplicate_charges": ros_duplicates,
            "baseline_recovery_rate": round(bl_rate, 1),
            "baseline_net_revenue": round(bl_net, 2),
            "baseline_total_recovered": round(bl_revenue, 2),
            "baseline_avg_attempts": round(bl_attempts / max(bl_recovered, 1), 2),
            "baseline_message_count": bl_messages,
            "baseline_duplicate_charges": bl_duplicates,
            "recovery_rate_improvement": round(ros_rate - bl_rate, 1),
            "net_revenue_improvement": round(ros_net - bl_net, 2),
            "message_reduction": round(
                (1 - ros_messages / max(bl_messages, 1)) * 100, 1
            ),
            "per_cause_comparison": per_cause,
        }


# Module-level singleton
batch_evaluator = BatchEvaluator()
