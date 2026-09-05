"""
Idempotency Layer for RecoverOS.

Generates idempotency keys per (transaction_id, action_type, time_window).
Prevents duplicate charges even under retried webhook delivery or race conditions.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import IdempotencyRecord


def generate_idempotency_key(
    transaction_id: int,
    action_type: str,
    timestamp_window: Optional[str] = None,
) -> str:
    """
    Generate a deterministic idempotency key.

    The key is based on transaction_id + action_type + time window,
    so the same action for the same transaction in the same window
    always produces the same key → prevents duplicate execution.
    """
    if timestamp_window is None:
        # Default window: 1-hour buckets
        now = datetime.utcnow()
        timestamp_window = now.strftime("%Y-%m-%d-%H")

    raw = f"{transaction_id}:{action_type}:{timestamp_window}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


async def check_idempotency(
    db: AsyncSession,
    idempotency_key: str,
) -> Optional[dict]:
    """
    Check if an action with this idempotency key has already been executed.

    Returns the previous result if found, None otherwise.
    """
    stmt = select(IdempotencyRecord).where(
        IdempotencyRecord.idempotency_key == idempotency_key
    )
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if record is not None:
        return {
            "already_executed": True,
            "idempotency_key": idempotency_key,
            "transaction_id": record.transaction_id,
            "action_type": record.action_type,
            "result": json.loads(record.result_json) if record.result_json else {},
            "executed_at": record.created_at.isoformat() if record.created_at else None,
        }
    return None


async def record_idempotency(
    db: AsyncSession,
    idempotency_key: str,
    transaction_id: int,
    action_type: str,
    result: Optional[dict] = None,
) -> IdempotencyRecord:
    """
    Record an executed action's idempotency key to prevent duplicates.
    """
    record = IdempotencyRecord(
        idempotency_key=idempotency_key,
        transaction_id=transaction_id,
        action_type=action_type,
        result_json=json.dumps(result or {}),
    )
    db.add(record)
    await db.flush()
    return record


class IdempotencyGuard:
    """
    High-level idempotency guard for recovery actions.

    Usage:
        guard = IdempotencyGuard(db)
        key = guard.generate_key(txn_id, action_type)
        previous = await guard.check(key)
        if previous:
            return previous  # Already executed — return cached result
        # ... execute action ...
        await guard.record(key, txn_id, action_type, result)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    def generate_key(
        self,
        transaction_id: int,
        action_type: str,
        window: Optional[str] = None,
    ) -> str:
        return generate_idempotency_key(transaction_id, action_type, window)

    async def check(self, key: str) -> Optional[dict]:
        return await check_idempotency(self.db, key)

    async def record(
        self,
        key: str,
        transaction_id: int,
        action_type: str,
        result: Optional[dict] = None,
    ) -> IdempotencyRecord:
        return await record_idempotency(self.db, key, transaction_id, action_type, result)
