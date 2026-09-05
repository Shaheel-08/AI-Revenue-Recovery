"""Mock payment link service for RecoverOS."""
from __future__ import annotations
import uuid
from datetime import datetime


class MockPaymentLinkService:
    """Generates mock Razorpay payment links."""

    def __init__(self):
        self.links_created: list[dict] = []

    def create_link(self, transaction_id: str, amount: float, description: str = "") -> str:
        link_id = f"plink_{uuid.uuid4().hex[:12]}"
        short_url = f"https://rzp.io/i/{link_id[:8]}"
        entry = {
            "link_id": link_id,
            "transaction_id": transaction_id,
            "amount": amount,
            "short_url": short_url,
            "description": description or f"Payment for {transaction_id}",
            "created_at": datetime.utcnow().isoformat(),
            "status": "created",
        }
        self.links_created.append(entry)
        return short_url


mock_payment_link = MockPaymentLinkService()
