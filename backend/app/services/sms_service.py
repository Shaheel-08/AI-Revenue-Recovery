"""Mock SMS service for RecoverOS."""
from __future__ import annotations
from datetime import datetime


class MockSMSService:
    def __init__(self):
        self.messages: list[dict] = []

    def send_sms(self, phone: str, transaction_id: str, amount: float) -> str:
        entry = {
            "channel": "sms", "phone": phone,
            "transaction_id": transaction_id, "amount": amount,
            "sent_at": datetime.utcnow().isoformat(), "status": "delivered",
        }
        self.messages.append(entry)
        return f"[MOCK] SMS sent to {phone}: Payment reminder for ₹{amount:,.0f}"


mock_sms = MockSMSService()
