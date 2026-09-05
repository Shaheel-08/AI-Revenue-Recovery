"""
Learning Agent — Outcome observation and bandit weight updates for RecoverOS.

After every outcome, persists (context, action, outcome, revenue_recovered,
cost, time_to_recovery) and updates the bandit's per-segment action values.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.contextual_bandit import contextual_bandit
from app.models.base import (
    BanditState, Customer, Outcome, RecoveryAction,
    Transaction, TransactionStatus,
)


class LearningAgent:
    """
    Observes outcomes and updates the contextual bandit:
    1. Record outcome (recovered, revenue, cost, time)
    2. Compute reward signal
    3. Update bandit weights for (segment, action)
    4. Persist bandit state to DB
    5. Update transaction status
    """

    async def record_outcome(
        self,
        db: AsyncSession,
        action_id: int,
        recovered: bool,
        revenue_recovered: float = 0.0,
        cost: float = 0.0,
        time_to_recovery_hours: Optional[float] = None,
    ) -> dict:
        """
        Record the outcome of a recovery action and update learning models.
        """
        # Get action and related data
        stmt = select(RecoveryAction).where(RecoveryAction.id == action_id)
        result = await db.execute(stmt)
        action = result.scalar_one_or_none()
        if action is None:
            return {"error": f"Action {action_id} not found"}

        # Get transaction
        stmt = select(Transaction).where(Transaction.id == action.transaction_id)
        result = await db.execute(stmt)
        transaction = result.scalar_one_or_none()

        # Get customer for segment
        segment = "regular"
        if transaction:
            stmt = select(Customer).where(Customer.id == transaction.customer_id)
            result = await db.execute(stmt)
            customer = result.scalar_one_or_none()
            if customer:
                segment = customer.segment

        # 1. Record outcome
        outcome = Outcome(
            action_id=action_id,
            recovered=recovered,
            revenue_recovered=revenue_recovered,
            cost=cost,
            time_to_recovery_hours=time_to_recovery_hours,
        )
        db.add(outcome)

        # 2. Compute reward signal (0-1 scale)
        reward = self._compute_reward(
            recovered=recovered,
            revenue_recovered=revenue_recovered,
            cost=cost,
            payment_value=transaction.amount if transaction else 0,
        )

        # 3. Update bandit
        contextual_bandit.update(
            segment=segment,
            action=action.action_type,
            reward=reward,
            context={
                "transaction_id": transaction.id if transaction else None,
                "root_cause": transaction.root_cause if transaction else None,
                "amount": transaction.amount if transaction else 0,
                "revenue_recovered": revenue_recovered,
                "cost": cost,
            },
        )

        # 4. Persist bandit state to DB
        await self._persist_bandit_state(db, segment, action.action_type)

        # 5. Update transaction status
        if transaction:
            if recovered:
                transaction.status = TransactionStatus.RECOVERED.value
            # Don't change status if not recovered — might try another action

        await db.flush()

        return {
            "action_id": action_id,
            "recovered": recovered,
            "reward": round(reward, 4),
            "segment": segment,
            "action_type": action.action_type,
            "revenue_recovered": revenue_recovered,
            "cost": cost,
            "bandit_updated": True,
        }

    def _compute_reward(
        self,
        recovered: bool,
        revenue_recovered: float,
        cost: float,
        payment_value: float,
    ) -> float:
        """
        Compute a 0-1 reward signal from outcome.

        Reward is proportional to net recovery efficiency:
        - 1.0 = full recovery at zero cost
        - 0.0 = no recovery
        - Partial = proportional to (revenue - cost) / payment_value
        """
        if not recovered or payment_value <= 0:
            return 0.0

        net = revenue_recovered - cost
        efficiency = net / payment_value

        # Clamp to [0, 1]
        return min(max(efficiency, 0.0), 1.0)

    async def _persist_bandit_state(
        self,
        db: AsyncSession,
        segment: str,
        action_type: str,
    ):
        """Persist the current bandit arm state for a (segment, action) pair."""
        arm = contextual_bandit.arms[segment].get(action_type)
        if arm is None:
            return

        stmt = select(BanditState).where(
            BanditState.segment == segment,
            BanditState.action_type == action_type,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.alpha = arm.alpha
            existing.beta_param = arm.beta
            existing.total_reward = arm.total_reward
            existing.count = arm.count
        else:
            state = BanditState(
                segment=segment,
                action_type=action_type,
                alpha=arm.alpha,
                beta_param=arm.beta,
                total_reward=arm.total_reward,
                count=arm.count,
            )
            db.add(state)

    async def load_bandit_state(self, db: AsyncSession):
        """Load persisted bandit state from DB on startup."""
        stmt = select(BanditState)
        result = await db.execute(stmt)
        records = result.scalars().all()

        for record in records:
            arm = contextual_bandit.arms[record.segment].get(record.action_type)
            if arm:
                arm.alpha = record.alpha
                arm.beta = record.beta_param
                arm.total_reward = record.total_reward
                arm.count = record.count

    async def get_learning_stats(self, db: AsyncSession) -> dict:
        """Get learning statistics."""
        stmt = select(BanditState)
        result = await db.execute(stmt)
        records = result.scalars().all()

        total_observations = sum(r.count for r in records)
        total_reward = sum(r.total_reward for r in records)

        best_by_segment = contextual_bandit.get_best_actions_by_segment()

        return {
            "total_observations": total_observations,
            "total_reward": round(total_reward, 2),
            "best_actions_by_segment": best_by_segment,
            "bandit_state": contextual_bandit.get_state(),
        }


# Module-level singleton
learning_agent = LearningAgent()
