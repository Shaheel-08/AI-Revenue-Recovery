"""Policy API — Merchant guardrail configuration."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.policy_engine import policy_engine
from app.models.base import PolicyRule
from app.schemas.base import PolicyConfig, PolicyResponse, PolicyRuleResponse

router = APIRouter()


@router.get("")
async def get_policy(
    merchant_id: int = Query(default=1),
    db: AsyncSession = Depends(get_db),
) -> PolicyResponse:
    """Get current merchant policy / guardrail configuration."""
    policy = await policy_engine.get_merchant_policy(db, merchant_id)

    # Get DB rules for IDs
    stmt = select(PolicyRule).where(PolicyRule.merchant_id == merchant_id)
    result = await db.execute(stmt)
    db_rules = result.scalars().all()

    rules = [
        PolicyRuleResponse(
            id=r.id,
            rule_type=r.rule_type,
            value=json.loads(r.value_json) if r.value_json else None,
            active=r.active,
        )
        for r in db_rules
    ]

    config = PolicyConfig(
        max_retries=policy.get("max_retries"),
        max_discount_percent=policy.get("max_discount_percent"),
        max_touchpoints_72h=policy.get("max_touchpoints_72h"),
        quiet_hour_start=policy.get("quiet_hour_start"),
        quiet_hour_end=policy.get("quiet_hour_end"),
        approval_threshold_amount=policy.get("approval_threshold_amount"),
        allowed_channels=policy.get("allowed_channels"),
        auto_retry_enabled=policy.get("auto_retry_enabled"),
    )

    return PolicyResponse(merchant_id=merchant_id, rules=rules, config=config)


@router.post("")
async def update_policy(
    config: PolicyConfig,
    merchant_id: int = Query(default=1),
    db: AsyncSession = Depends(get_db),
) -> PolicyResponse:
    """Update merchant guardrail configuration."""
    updates = config.model_dump(exclude_none=True)

    await policy_engine.update_merchant_policy(db, merchant_id, updates)
    return await get_policy(merchant_id=merchant_id, db=db)
