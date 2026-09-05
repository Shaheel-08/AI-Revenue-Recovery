"""Mock Email service for RecoverOS."""
from __future__ import annotations
from datetime import datetime


class MockEmailService:
    def __init__(self):
        self.emails: list[dict] = []

    def send_email(self, to: str, subject: str, transaction_id: str, amount: float) -> str:
        entry = {
            "channel": "email", "to": to, "subject": subject,
            "transaction_id": transaction_id, "amount": amount,
            "sent_at": datetime.utcnow().isoformat(), "status": "delivered",
        }
        self.emails.append(entry)
        return f"[MOCK] Email sent to {to}: {subject} for ₹{amount:,.0f}"


mock_email = MockEmailService()
