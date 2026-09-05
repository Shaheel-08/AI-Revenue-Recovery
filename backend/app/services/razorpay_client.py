"""Mock Razorpay client for RecoverOS. Logs all actions to console/DB instead of calling live APIs."""
from __future__ import annotations
import uuid
from datetime import datetime


class MockRazorpayClient:
    """Mock Razorpay test-mode wrapper. All operations are logged, not executed."""

    def __init__(self):
        self.operations_log: list[dict] = []

    def _log(self, operation: str, details: dict) -> str:
        entry = {"operation": operation, "timestamp": datetime.utcnow().isoformat(), **details}
        self.operations_log.append(entry)
        return f"[MOCK] {operation}: {details}"

    def retry_payment(self, payment_id: str) -> str:
        return self._log("retry_payment", {
            "payment_id": payment_id,
            "status": "retry_initiated",
            "mock_order_id": f"order_{uuid.uuid4().hex[:12]}",
        })

    def schedule_retry(self, payment_id: str, delay_hours: float = 6.0) -> str:
        return self._log("schedule_retry", {
            "payment_id": payment_id,
            "delay_hours": delay_hours,
            "scheduled_at": datetime.utcnow().isoformat(),
            "status": "scheduled",
        })

    def switch_payment_method(self, payment_id: str, new_method: str) -> str:
        return self._log("switch_payment_method", {
            "payment_id": payment_id,
            "new_method": new_method,
            "status": "method_switch_initiated",
        })

    def create_refund(self, payment_id: str, amount: float) -> str:
        return self._log("create_refund", {
            "payment_id": payment_id,
            "amount": amount,
            "refund_id": f"rfnd_{uuid.uuid4().hex[:12]}",
        })

    def get_payment_status(self, payment_id: str) -> dict:
        return {"payment_id": payment_id, "status": "failed", "mock": True}


mock_razorpay = MockRazorpayClient()
