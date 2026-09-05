# RecoverOS — API Contract (Frontend Source of Truth)

> **Generated from**: actual backend code in `backend/app/api/` + `backend/app/schemas/base.py`  
> **Date**: 2026-08-23  
> **Base URL**: `http://localhost:8000`

---

## Health

### `GET /`
**Response** `200`:
```json
{
  "name": "RecoverOS",
  "version": "1.0.0",
  "status": "operational",
  "description": "AI Revenue Recovery Agent"
}
```

### `GET /health`
**Response** `200`:
```json
{ "status": "healthy" }
```

---

## Dashboard — `/dashboard`

### `GET /dashboard/summary?merchant_id=1`
**Response** `200` — `DashboardSummary`:
```json
{
  "total_at_risk": 1234567.89,
  "total_recoverable": 987654.32,
  "total_recovered": 246913.57,
  "recovery_rate": 25.1,
  "total_transactions": 2000,
  "failed_transactions": 1500,
  "recovered_transactions": 500,
  "in_progress_transactions": 0,
  "top_failure_causes": [
    { "cause": "INSUFFICIENT_FUNDS", "count": 500, "amount": 345678.90 }
  ],
  "recent_actions": [
    {
      "transaction_id": 42,
      "external_id": "txn_000042",
      "amount": 1500.0,
      "action_type": "whatsapp_nudge",
      "status": "executed",
      "explanation": "Chose WhatsApp nudge because...",
      "created_at": "2025-07-15T14:30:00"
    }
  ],
  "daily_trends": [
    {
      "date": "2025-07-01",
      "failed_amount": 50000.0,
      "recovered_amount": 12000.0,
      "recovery_rate": 24.0
    }
  ]
}
```

### `GET /dashboard/transactions?merchant_id=1&status=failed&root_cause=BANK_DOWNTIME&limit=50&offset=0`
All query params optional. **Response** `200` — `list[TransactionListItem]`:
```json
[
  {
    "id": 1,
    "external_id": "txn_000001",
    "amount": 2500.0,
    "payment_method": "card",
    "status": "failed",
    "root_cause": "BANK_DOWNTIME",
    "customer_segment": "",
    "timestamp": "2025-07-01T08:30:00",
    "action_count": 1
  }
]
```

---

## Recovery — `/transactions`

### `GET /transactions/{transaction_id}`
**Response** `200` — `TransactionDetail`:
```json
{
  "id": 1,
  "external_id": "txn_000001",
  "merchant_id": 1,
  "customer_id": 1,
  "customer_name": "Customer 1",
  "customer_segment": "regular",
  "amount": 2500.0,
  "payment_method": "card",
  "status": "failed",
  "failure_code": "GATEWAY_ERROR",
  "failure_reason": "BANK_DOWNTIME",
  "root_cause": "BANK_DOWNTIME",
  "subscription_type": null,
  "retry_count": 0,
  "timestamp": "2025-07-01T08:30:00",
  "actions": [
    {
      "id": 1,
      "action_type": "retry_delayed",
      "utility_score": 1250.50,
      "recovery_probability": 0.72,
      "expected_revenue": 1800.0,
      "cost": 0.0,
      "explanation": "Chose delayed retry because bank is experiencing downtime...",
      "confidence": 0.85,
      "status": "executed",
      "requires_approval": false,
      "executed_at": "2025-07-01T08:31:00",
      "created_at": "2025-07-01T08:30:30",
      "outcome": {
        "recovered": true,
        "revenue_recovered": 2500.0,
        "cost": 0.0,
        "time_to_recovery_hours": 3.5
      }
    }
  ]
}
```

### `GET /transactions/{transaction_id}/whatif`
**Response** `200` — `WhatIfResponse`:
```json
{
  "transaction_id": 1,
  "external_id": "txn_000001",
  "amount": 2500.0,
  "root_cause": "BANK_DOWNTIME",
  "customer_segment": "regular",
  "candidates": [
    {
      "action_type": "retry_delayed",
      "recovery_probability": 0.72,
      "expected_revenue": 1800.0,
      "communication_cost": 0.0,
      "discount_cost": 0.0,
      "fatigue_cost": 0.0,
      "risk_cost": 2.50,
      "net_expected_revenue": 1797.50,
      "is_recommended": true,
      "explanation": "Chose delayed retry because..."
    }
  ],
  "chosen_action": { "...same shape as candidate..." },
  "decision_explanation": "Full decision reasoning...",
  "confidence": 0.85
}
```

### `POST /transactions/{transaction_id}/execute`
**Request body** (optional) — `ExecuteActionRequest`:
```json
{
  "action_type": "retry_delayed",
  "force": false
}
```
Both fields optional. If `action_type` is null, uses the recommended action.

**Response** `200`:
```json
{
  "action_id": 1,
  "action_type": "retry_delayed",
  "status": "executed",
  "explanation": "[MOCK] schedule_retry: {...}",
  "requires_approval": false,
  "approval_id": null,
  "guardrail_result": {
    "allowed": true,
    "checks": [{ "rule": "allowed_channel", "passed": true, "reason": "..." }]
  },
  "idempotency_hit": false
}
```

### `POST /transactions/{transaction_id}/outcome?recovered=true&revenue_recovered=2500&cost=0&time_to_recovery_hours=3.5`
All query params. **Response** `200`:
```json
{
  "action_id": 1,
  "recovered": true,
  "reward": 1.0,
  "segment": "regular",
  "action_type": "retry_delayed",
  "revenue_recovered": 2500.0,
  "cost": 0.0,
  "bandit_updated": true
}
```

---

## Approvals — `/approvals`

### `GET /approvals/pending?merchant_id=1`
**Response** `200` — `list[ApprovalRequestResponse]`:
```json
[
  {
    "id": 1,
    "action_id": 5,
    "merchant_id": 1,
    "transaction_id": 42,
    "transaction_amount": 75000.0,
    "action_type": "whatsapp_nudge",
    "reason": "High-value transaction (₹75,000) requires human approval...",
    "status": "pending",
    "explanation": "Chose WhatsApp nudge because...",
    "customer_segment": "vip",
    "recovery_probability": 0.65,
    "decided_by": null,
    "decided_at": null,
    "created_at": "2025-07-15T14:30:00"
  }
]
```

### `POST /approvals/{approval_id}/decision`
**Request body** — `ApprovalDecision`:
```json
{
  "approved": true,
  "decided_by": "merchant_admin",
  "reason": ""
}
```

**Response** `200` (approved):
```json
{
  "approval_id": 1,
  "status": "approved",
  "execution": {
    "action_id": 5,
    "action_type": "whatsapp_nudge",
    "status": "executed",
    "explanation": "[MOCK] WhatsApp sent...",
    "requires_approval": false,
    "approval_id": null,
    "guardrail_result": null,
    "idempotency_hit": false
  }
}
```

**Response** `200` (rejected):
```json
{
  "approval_id": 1,
  "status": "rejected",
  "reason": "Too risky"
}
```

---

## Policy — `/policy`

### `GET /policy?merchant_id=1`
**Response** `200` — `PolicyResponse`:
```json
{
  "merchant_id": 1,
  "rules": [
    { "id": 1, "rule_type": "max_retries", "value": 3, "active": true }
  ],
  "config": {
    "max_retries": 3,
    "max_discount_percent": 15.0,
    "max_touchpoints_72h": 5,
    "quiet_hour_start": 22,
    "quiet_hour_end": 8,
    "approval_threshold_amount": 50000.0,
    "allowed_channels": ["retry_now", "retry_delayed", "..."],
    "auto_retry_enabled": true
  }
}
```

### `POST /policy?merchant_id=1`
**Request body** — `PolicyConfig` (all fields optional for partial update):
```json
{
  "max_retries": 5,
  "max_discount_percent": 20.0
}
```
**Response** `200` — same as `GET /policy`.

---

## Simulation — `/simulate`

### `POST /simulate/batch`
**Request body** (optional) — `BatchEvaluationRequest`:
```json
{
  "transaction_count": 2000,
  "seed": 42
}
```

**Response** `200` — `BatchEvaluationReport`:
```json
{
  "transaction_count": 2000,
  "ros_recovery_rate": 38.5,
  "ros_net_revenue": 2345678.90,
  "ros_total_recovered": 2400000.0,
  "ros_avg_attempts": 1.0,
  "ros_message_count": 450,
  "ros_duplicate_charges": 0,
  "baseline_recovery_rate": 18.2,
  "baseline_net_revenue": 987654.32,
  "baseline_total_recovered": 990000.0,
  "baseline_avg_attempts": 2.5,
  "baseline_message_count": 5400,
  "baseline_duplicate_charges": 15,
  "recovery_rate_improvement": 20.3,
  "net_revenue_improvement": 1358024.58,
  "message_reduction": 91.7,
  "per_cause_comparison": [
    {
      "cause": "BANK_DOWNTIME",
      "ros_recovery_rate": 55.0,
      "baseline_recovery_rate": 30.0,
      "ros_net_revenue": 345000.0,
      "baseline_net_revenue": 180000.0
    }
  ]
}
```

---

## Webhooks — `/webhooks`

### `POST /webhooks/payment-failed`
**Request body** — `PaymentFailedWebhook`:
```json
{
  "payment_id": "pay_ABC123",
  "merchant_id": 1,
  "customer_id": "cust_0001",
  "amount": 2500.0,
  "payment_method": "card",
  "failure_code": "GATEWAY_ERROR",
  "failure_reason": "bank_server_down",
  "subscription_type": null,
  "timestamp": "2025-07-01T08:30:00"
}
```

**Response** `200`:
```json
{
  "status": "processed",
  "transaction_id": 2001,
  "root_cause": "BANK_DOWNTIME",
  "root_cause_confidence": 0.88,
  "recommended_action": "retry_delayed",
  "execution_status": "executed",
  "explanation": "Chose delayed retry because bank is experiencing downtime...",
  "confidence": 0.85,
  "requires_approval": false,
  "approval_id": null
}
```
