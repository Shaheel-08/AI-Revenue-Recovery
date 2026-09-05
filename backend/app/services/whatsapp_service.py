"""Mock WhatsApp service for RecoverOS. Logs messages to internal list."""
from __future__ import annotations
from datetime import datetime


class MockWhatsAppService:
    def __init__(self):
        self.messages: list[dict] = []

    def send_message(self, phone: str, template: str, transaction_id: str, amount: float) -> str:
        entry = {
            "channel": "whatsapp", "phone": phone, "template": template,
            "transaction_id": transaction_id, "amount": amount,
            "sent_at": datetime.utcnow().isoformat(), "status": "delivered",
        }
        self.messages.append(entry)
        return f"[MOCK] WhatsApp sent to {phone}: {template} for ₹{amount:,.0f}"


mock_whatsapp = MockWhatsAppService()
