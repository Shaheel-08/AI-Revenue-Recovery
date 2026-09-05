"""
Synthetic Transaction Dataset Generator for RecoverOS.

Generates realistic failed-payment data with encoded recovery patterns:
- INSUFFICIENT_FUNDS → better recovery on delayed retry near salary dates (25th-5th)
- EXPIRED_CARD → low retry recovery, high alternate-method recovery
- BANK_DOWNTIME → high delayed-retry recovery (1-6h later)
- SUSPECTED_FRAUD → near-zero auto-recovery
- AUTH_OTP_FAILURE → moderate recovery via payment link
- USER_ABANDONED → recoverable via nudge within 1h
- SUBSCRIPTION_MANDATE_FAILURE → recoverable via mandate re-auth link

Usage:
    python -m app.simulation.synthetic_data_generator --count 2000 --seed 42
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

# ── Constants ────────────────────────────────────────────────────────────────

FAILURE_REASONS = [
    "BANK_DOWNTIME",
    "INSUFFICIENT_FUNDS",
    "EXPIRED_CARD",
    "AUTH_OTP_FAILURE",
    "INVALID_DETAILS",
    "USER_ABANDONED",
    "MERCHANT_INTEGRATION_ERROR",
    "SUBSCRIPTION_MANDATE_FAILURE",
    "SUSPECTED_FRAUD",
]

FAILURE_WEIGHTS = [0.12, 0.25, 0.10, 0.13, 0.05, 0.15, 0.05, 0.08, 0.07]

PAYMENT_METHODS = ["upi", "card", "netbanking", "wallet", "emi", "nach"]
PAYMENT_METHOD_WEIGHTS = [0.35, 0.30, 0.15, 0.10, 0.05, 0.05]

CUSTOMER_SEGMENTS = ["new", "regular", "vip", "at_risk", "b2b"]
SEGMENT_WEIGHTS = [0.15, 0.40, 0.20, 0.15, 0.10]

SUBSCRIPTION_TYPES = [None, "monthly", "quarterly", "annual"]
SUBSCRIPTION_WEIGHTS = [0.60, 0.25, 0.10, 0.05]

PREFERRED_CHANNELS = ["email", "whatsapp", "sms", "upi"]
CHANNEL_WEIGHTS = [0.30, 0.35, 0.20, 0.15]

ACTION_TYPES = [
    "retry_now", "retry_delayed", "switch_to_upi", "send_payment_link",
    "whatsapp_nudge", "email_reminder", "sms_reminder",
    "offer_discount", "escalate_human", "stop",
]

# Razorpay-style error codes mapped to root causes
ERROR_CODE_MAP = {
    "BANK_DOWNTIME": ["BAD_REQUEST_ERROR", "GATEWAY_ERROR", "SERVER_ERROR"],
    "INSUFFICIENT_FUNDS": ["BAD_REQUEST_ERROR"],
    "EXPIRED_CARD": ["BAD_REQUEST_ERROR"],
    "AUTH_OTP_FAILURE": ["BAD_REQUEST_ERROR", "GATEWAY_ERROR"],
    "INVALID_DETAILS": ["BAD_REQUEST_ERROR"],
    "USER_ABANDONED": ["BAD_REQUEST_ERROR"],
    "MERCHANT_INTEGRATION_ERROR": ["SERVER_ERROR"],
    "SUBSCRIPTION_MANDATE_FAILURE": ["BAD_REQUEST_ERROR"],
    "SUSPECTED_FRAUD": ["BAD_REQUEST_ERROR"],
}


# ── Recovery probability functions (encode realistic patterns) ──────────────


def _base_recovery_prob(
    failure_reason: str,
    action: str,
    day_of_month: int,
    hour: int,
    customer_segment: str,
    previous_success_rate: float,
    payment_method: str,
    amount: float,
    retry_count: int,
) -> float:
    """
    Compute a realistic base recovery probability for (failure_reason, action).
    Encodes domain knowledge about which interventions work for which failure types.
    """
    p = 0.05  # absolute minimum

    # ── Failure-specific base rates per action ──
    if failure_reason == "BANK_DOWNTIME":
        rates = {
            "retry_now": 0.15,
            "retry_delayed": 0.72,  # banks come back — delayed retry is king
            "switch_to_upi": 0.30,
            "send_payment_link": 0.55,
            "whatsapp_nudge": 0.25,
            "email_reminder": 0.20,
            "sms_reminder": 0.18,
            "offer_discount": 0.30,
            "escalate_human": 0.40,
            "stop": 0.0,
        }
    elif failure_reason == "INSUFFICIENT_FUNDS":
        rates = {
            "retry_now": 0.08,
            "retry_delayed": 0.45,  # salary date effect
            "switch_to_upi": 0.15,
            "send_payment_link": 0.35,
            "whatsapp_nudge": 0.30,
            "email_reminder": 0.22,
            "sms_reminder": 0.20,
            "offer_discount": 0.48,  # discount helps!
            "escalate_human": 0.25,
            "stop": 0.0,
        }
    elif failure_reason == "EXPIRED_CARD":
        rates = {
            "retry_now": 0.02,  # card is still expired!
            "retry_delayed": 0.05,
            "switch_to_upi": 0.62,  # alternate method is the answer
            "send_payment_link": 0.58,
            "whatsapp_nudge": 0.45,
            "email_reminder": 0.40,
            "sms_reminder": 0.35,
            "offer_discount": 0.38,
            "escalate_human": 0.42,
            "stop": 0.0,
        }
    elif failure_reason == "AUTH_OTP_FAILURE":
        rates = {
            "retry_now": 0.25,
            "retry_delayed": 0.35,
            "switch_to_upi": 0.50,
            "send_payment_link": 0.55,  # payment link avoids OTP friction
            "whatsapp_nudge": 0.40,
            "email_reminder": 0.30,
            "sms_reminder": 0.28,
            "offer_discount": 0.35,
            "escalate_human": 0.38,
            "stop": 0.0,
        }
    elif failure_reason == "USER_ABANDONED":
        rates = {
            "retry_now": 0.10,
            "retry_delayed": 0.20,
            "switch_to_upi": 0.25,
            "send_payment_link": 0.48,
            "whatsapp_nudge": 0.55,  # nudge within 1h is best
            "email_reminder": 0.35,
            "sms_reminder": 0.30,
            "offer_discount": 0.52,
            "escalate_human": 0.20,
            "stop": 0.0,
        }
    elif failure_reason == "SUBSCRIPTION_MANDATE_FAILURE":
        rates = {
            "retry_now": 0.12,
            "retry_delayed": 0.25,
            "switch_to_upi": 0.40,
            "send_payment_link": 0.55,  # re-auth link
            "whatsapp_nudge": 0.42,
            "email_reminder": 0.38,
            "sms_reminder": 0.32,
            "offer_discount": 0.30,
            "escalate_human": 0.45,
            "stop": 0.0,
        }
    elif failure_reason == "SUSPECTED_FRAUD":
        # Almost nothing works automatically — escalation is the only real option
        rates = {
            "retry_now": 0.01,
            "retry_delayed": 0.01,
            "switch_to_upi": 0.02,
            "send_payment_link": 0.03,
            "whatsapp_nudge": 0.02,
            "email_reminder": 0.02,
            "sms_reminder": 0.01,
            "offer_discount": 0.01,
            "escalate_human": 0.15,
            "stop": 0.0,
        }
    elif failure_reason == "INVALID_DETAILS":
        rates = {
            "retry_now": 0.05,
            "retry_delayed": 0.08,
            "switch_to_upi": 0.35,
            "send_payment_link": 0.50,
            "whatsapp_nudge": 0.42,
            "email_reminder": 0.38,
            "sms_reminder": 0.30,
            "offer_discount": 0.28,
            "escalate_human": 0.35,
            "stop": 0.0,
        }
    elif failure_reason == "MERCHANT_INTEGRATION_ERROR":
        rates = {
            "retry_now": 0.30,  # if fixed, retry works
            "retry_delayed": 0.55,
            "switch_to_upi": 0.20,
            "send_payment_link": 0.45,
            "whatsapp_nudge": 0.15,
            "email_reminder": 0.12,
            "sms_reminder": 0.10,
            "offer_discount": 0.10,
            "escalate_human": 0.60,  # needs developer fix
            "stop": 0.0,
        }
    else:
        rates = {a: 0.10 for a in ACTION_TYPES}
        rates["stop"] = 0.0

    p = rates.get(action, 0.05)

    # ── Modifiers ──

    # Salary-date effect for INSUFFICIENT_FUNDS
    if failure_reason == "INSUFFICIENT_FUNDS" and action in ("retry_delayed", "send_payment_link"):
        if 25 <= day_of_month or day_of_month <= 5:
            p *= 1.35  # much better near salary dates

    # Time-based modifier for USER_ABANDONED (nudge within 1h is best)
    if failure_reason == "USER_ABANDONED" and action == "whatsapp_nudge":
        # Higher prob if we act quickly (simulated by hour proximity)
        p *= 1.20

    # VIP customers are more responsive
    if customer_segment == "vip":
        p *= 1.15
    elif customer_segment == "b2b":
        p *= 1.05
    elif customer_segment == "at_risk":
        p *= 0.75
    elif customer_segment == "new":
        p *= 0.90

    # Previous success rate matters
    p *= (0.6 + 0.4 * previous_success_rate)

    # Retry fatigue: each previous retry reduces probability
    p *= max(0.3, 1.0 - 0.15 * retry_count)

    # High-value transactions have slightly lower recovery (more considered purchases)
    if amount > 10000:
        p *= 0.92
    elif amount > 50000:
        p *= 0.85

    return min(max(p, 0.0), 0.99)


def _select_best_action(rng: np.random.Generator, probs: dict[str, float]) -> str:
    """Select action weighted by recovery probability + some randomness."""
    actions = list(probs.keys())
    weights = np.array([probs[a] for a in actions])
    if weights.sum() == 0:
        return "stop"
    # Softmax-like selection biased toward higher-prob actions
    weights = weights ** 2
    weights /= weights.sum()
    return rng.choice(actions, p=weights)


def _simulate_outcome(
    rng: np.random.Generator,
    recovery_prob: float,
    action: str,
    amount: float,
) -> tuple[bool, float, float, float]:
    """
    Simulate whether recovery succeeded and associated costs.
    Returns: (recovered, revenue_recovered, cost, recovery_time_hours)
    """
    recovered = rng.random() < recovery_prob

    # Communication costs
    comm_costs = {
        "retry_now": 0.0,
        "retry_delayed": 0.0,
        "switch_to_upi": 0.0,
        "send_payment_link": 0.50,
        "whatsapp_nudge": 1.50,
        "email_reminder": 0.10,
        "sms_reminder": 0.25,
        "offer_discount": 0.10,
        "escalate_human": 50.0,
        "stop": 0.0,
    }
    cost = comm_costs.get(action, 0.0)

    # Discount cost
    discount = 0.0
    if action == "offer_discount":
        discount_pct = rng.choice([5, 8, 10, 12, 15], p=[0.3, 0.25, 0.25, 0.12, 0.08])
        discount = amount * discount_pct / 100
        cost += discount

    revenue = (amount - discount) if recovered else 0.0

    # Recovery time
    time_map = {
        "retry_now": rng.uniform(0.1, 1.0),
        "retry_delayed": rng.uniform(2.0, 48.0),
        "switch_to_upi": rng.uniform(0.5, 4.0),
        "send_payment_link": rng.uniform(1.0, 24.0),
        "whatsapp_nudge": rng.uniform(0.5, 12.0),
        "email_reminder": rng.uniform(2.0, 48.0),
        "sms_reminder": rng.uniform(1.0, 24.0),
        "offer_discount": rng.uniform(0.5, 12.0),
        "escalate_human": rng.uniform(4.0, 72.0),
        "stop": 0.0,
    }
    recovery_time = time_map.get(action, 12.0) if recovered else 0.0

    return recovered, revenue, cost, recovery_time


# ── Main Generator ───────────────────────────────────────────────────────────


def generate_synthetic_data(
    count: int = 2000,
    seed: int = 42,
    num_merchants: int = 3,
    num_customers: int = 500,
) -> list[dict[str, Any]]:
    """
    Generate synthetic failed-payment transactions with realistic recovery patterns.

    Returns a list of dicts, each representing one transaction with its outcome.
    """
    rng = np.random.default_rng(seed)

    # Pre-generate customer profiles
    customers = []
    for i in range(num_customers):
        segment = rng.choice(CUSTOMER_SEGMENTS, p=SEGMENT_WEIGHTS)
        ltv_ranges = {
            "new": (500, 10000),
            "regular": (5000, 50000),
            "vip": (50000, 500000),
            "at_risk": (1000, 20000),
            "b2b": (100000, 2000000),
        }
        ltv_lo, ltv_hi = ltv_ranges[segment]
        ltv = round(rng.uniform(ltv_lo, ltv_hi), 2)
        prev_txns = int(rng.exponential(scale=15)) + 1
        success_rate = min(rng.beta(8, 2), 0.99) if segment != "at_risk" else min(rng.beta(3, 5), 0.99)

        customers.append({
            "customer_id": f"cust_{i+1:04d}",
            "merchant_id": int(rng.integers(1, num_merchants + 1)),
            "segment": segment,
            "ltv": ltv,
            "preferred_channel": rng.choice(PREFERRED_CHANNELS, p=CHANNEL_WEIGHTS),
            "previous_transactions": prev_txns,
            "previous_success_rate": round(success_rate, 3),
            "avg_payment_amount": round(rng.lognormal(mean=7, sigma=1.2), 2),
            "days_since_last_payment": int(rng.exponential(scale=15)),
        })

    # Generate transactions
    records = []
    base_time = datetime(2025, 7, 1, 0, 0, 0)

    for i in range(count):
        cust = customers[int(rng.integers(0, num_customers))]

        # Amount distribution — log-normal for realistic spread
        amount_mult = {"new": 1.0, "regular": 1.5, "vip": 5.0, "at_risk": 0.8, "b2b": 10.0}
        amount = round(
            rng.lognormal(mean=7.5, sigma=1.0) * amount_mult.get(cust["segment"], 1.0), 2
        )
        amount = max(50, min(amount, 500000))  # clamp

        # Timestamp spread over 30 days
        ts_offset = timedelta(
            days=float(rng.uniform(0, 30)),
            hours=float(rng.uniform(0, 24)),
            minutes=int(rng.integers(0, 60)),
        )
        timestamp = base_time + ts_offset
        day_of_month = timestamp.day
        hour = timestamp.hour

        # Failure reason
        failure_reason = rng.choice(FAILURE_REASONS, p=FAILURE_WEIGHTS)

        # Payment method (some failures correlate with methods)
        if failure_reason == "EXPIRED_CARD":
            payment_method = "card"
        elif failure_reason == "SUBSCRIPTION_MANDATE_FAILURE":
            payment_method = rng.choice(["nach", "card", "upi"], p=[0.5, 0.3, 0.2])
        else:
            payment_method = rng.choice(PAYMENT_METHODS, p=PAYMENT_METHOD_WEIGHTS)

        # Subscription type
        sub_type = rng.choice(SUBSCRIPTION_TYPES, p=SUBSCRIPTION_WEIGHTS)
        if failure_reason == "SUBSCRIPTION_MANDATE_FAILURE" and sub_type is None:
            sub_type = "monthly"

        # Failure code
        error_codes = ERROR_CODE_MAP.get(failure_reason, ["BAD_REQUEST_ERROR"])
        failure_code = rng.choice(error_codes)

        retry_count = int(rng.integers(0, 4))

        # Compute recovery probabilities for all actions
        action_probs = {}
        for action in ACTION_TYPES:
            if action == "stop":
                action_probs[action] = 0.0
                continue
            p = _base_recovery_prob(
                failure_reason=failure_reason,
                action=action,
                day_of_month=day_of_month,
                hour=hour,
                customer_segment=cust["segment"],
                previous_success_rate=cust["previous_success_rate"],
                payment_method=payment_method,
                amount=amount,
                retry_count=retry_count,
            )
            action_probs[action] = round(p, 4)

        # Select the action taken (biased toward higher-prob actions)
        action_taken = _select_best_action(rng, action_probs)
        recovery_prob = action_probs.get(action_taken, 0.0)

        # Simulate outcome
        recovered, revenue, cost, recovery_time = _simulate_outcome(
            rng, recovery_prob, action_taken, amount
        )

        # Discount amount (only for offer_discount action)
        discount = 0.0
        if action_taken == "offer_discount" and recovered:
            discount = round(cost - 0.10, 2)  # cost includes comm + discount
            discount = max(0, discount)

        records.append({
            "transaction_id": f"txn_{i+1:06d}",
            "customer_id": cust["customer_id"],
            "merchant_id": cust["merchant_id"],
            "amount": amount,
            "payment_method": payment_method,
            "failure_reason": failure_reason,
            "failure_code": failure_code,
            "timestamp": timestamp.isoformat(),
            "customer_segment": cust["segment"],
            "previous_transactions": cust["previous_transactions"],
            "previous_success_rate": cust["previous_success_rate"],
            "avg_payment_amount": cust["avg_payment_amount"],
            "customer_lifetime_value": cust["ltv"],
            "preferred_channel": cust["preferred_channel"],
            "retry_count": retry_count,
            "subscription_type": sub_type or "",
            "days_since_last_payment": cust["days_since_last_payment"],
            "action_taken": action_taken,
            "recovered": int(recovered),
            "recovery_time": round(recovery_time, 2),
            "discount": round(discount, 2),
            "communication_cost": round(cost, 2),
        })

    return records, customers


def save_csv(records: list[dict], filepath: str) -> None:
    """Save records to CSV."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    if not records:
        return
    fieldnames = list(records[0].keys())
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"  [OK] Saved {len(records)} records to {filepath}")


async def seed_database(records: list[dict], customers: list[dict]) -> None:
    """Seed the SQLite database with generated data."""
    from app.db.session import async_session_factory, init_db
    from app.models.base import (
        Merchant, Customer, Transaction,
    )

    await init_db()

    async with async_session_factory() as session:
        # Create merchants
        merchants = [
            Merchant(id=1, name="TechStore India", business_type="ecommerce"),
            Merchant(id=2, name="CloudSaaS Pro", business_type="saas"),
            Merchant(id=3, name="MegaRetail Corp", business_type="retail"),
        ]
        for m in merchants:
            session.add(m)
        await session.flush()

        # Create customers
        cust_map = {}
        for i, c in enumerate(customers):
            cust = Customer(
                id=i + 1,
                external_id=c["customer_id"],
                merchant_id=c["merchant_id"],
                name=f"Customer {i+1}",
                email=f"{c['customer_id']}@example.com",
                phone=f"+91{9000000000 + i}",
                segment=c["segment"],
                ltv=c["ltv"],
                preferred_channel=c["preferred_channel"],
                previous_transactions=c["previous_transactions"],
                previous_success_rate=c["previous_success_rate"],
                avg_payment_amount=c["avg_payment_amount"],
                days_since_last_payment=c["days_since_last_payment"],
                payment_history_json=json.dumps([]),
            )
            session.add(cust)
            cust_map[c["customer_id"]] = i + 1
        await session.flush()

        # Create transactions
        for i, r in enumerate(records):
            txn = Transaction(
                id=i + 1,
                external_id=r["transaction_id"],
                merchant_id=r["merchant_id"],
                customer_id=cust_map.get(r["customer_id"], 1),
                amount=r["amount"],
                payment_method=r["payment_method"],
                status="failed",
                failure_code=r["failure_code"],
                failure_reason=r["failure_reason"],
                root_cause=r["failure_reason"],
                subscription_type=r["subscription_type"] or None,
                retry_count=r["retry_count"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
            )
            session.add(txn)

        await session.commit()
        print(f"  [OK] Seeded database: {len(merchants)} merchants, {len(customers)} customers, {len(records)} transactions")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic transaction data for RecoverOS")
    parser.add_argument("--count", type=int, default=2000, help="Number of transactions")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--output", type=str, default=None, help="Output CSV path")
    parser.add_argument("--no-db", action="store_true", help="Skip database seeding")
    args = parser.parse_args()

    # Resolve output path
    project_dir = Path(__file__).resolve().parent.parent.parent.parent
    output_path = args.output or str(project_dir / "data" / "synthetic_transactions.csv")

    print(f"\n[*] RecoverOS Synthetic Data Generator")
    print(f"  Generating {args.count} transactions (seed={args.seed})...")

    records, customers = generate_synthetic_data(count=args.count, seed=args.seed)
    save_csv(records, output_path)

    # Show summary
    import collections
    cause_counts = collections.Counter(r["failure_reason"] for r in records)
    recovery_rate = sum(r["recovered"] for r in records) / len(records) * 100

    print(f"\n[+] Dataset Summary:")
    print(f"  Total transactions: {len(records)}")
    print(f"  Overall recovery rate: {recovery_rate:.1f}%")
    print(f"  Failure distribution:")
    for cause, count in sorted(cause_counts.items(), key=lambda x: -x[1]):
        pct = count / len(records) * 100
        cause_recovered = sum(1 for r in records if r["failure_reason"] == cause and r["recovered"])
        cause_rate = cause_recovered / count * 100 if count > 0 else 0
        print(f"    {cause:35s} {count:5d} ({pct:5.1f}%)  recovery: {cause_rate:.1f}%")

    # Seed database
    if not args.no_db:
        import asyncio
        print(f"\n[*] Seeding database...")
        asyncio.run(seed_database(records, customers))

    print(f"\n[OK] Done!\n")


if __name__ == "__main__":
    main()
