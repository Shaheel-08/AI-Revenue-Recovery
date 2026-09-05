import pytest
from app.ml.utility_engine import utility_engine
from app.core.circuit_breaker import circuit_breaker
from app.models.base import ActionType, Transaction

def test_utility_engine_economics():
    """Test that the utility engine properly calculates net expected revenue."""
    recovery_probs = {
        "retry_now": 0.20,
        "whatsapp_nudge": 0.85,
        "offer_discount": 0.90,
    }
    amount = 5000.0
    
    scores = utility_engine.score_all_actions(
        recovery_probs=recovery_probs,
        payment_value=amount,
        touchpoints_last_72h=1,
        root_cause="INSUFFICIENT_FUNDS",
        customer_segment="regular"
    )
    
    # Check that whatsapp has communication cost
    whatsapp = next(s for s in scores if s.action_type == "whatsapp_nudge")
    assert whatsapp.communication_cost == 1.50
    assert whatsapp.expected_gross_revenue == 0.85 * amount
    assert whatsapp.net_expected_revenue == (0.85 * amount) - 1.50
    
    # Check that discount has discount cost
    discount = next(s for s in scores if s.action_type == "offer_discount")
    assert discount.communication_cost == 0.10  # Cost of sending email/sms
    expected_discount = amount * 0.10  # 10% discount default
    assert discount.expected_gross_revenue == 0.90 * (amount - expected_discount)

def test_circuit_breaker_fraud_block():
    """Test that the circuit breaker strictly blocks suspected fraud."""
    from app.core.config import get_settings
    settings = get_settings()
    
    txn = Transaction(
        merchant_id=1,
        customer_id=1,
        amount=1000.0,
        status="failed",
        root_cause="SUSPECTED_FRAUD",
        retry_count=0
    )
    
    passed, reason = circuit_breaker.check_execution_allowed(
        transaction=txn,
        action_type="retry_now",
        touchpoints_72h=0,
        settings=settings
    )
    
    assert passed is False
    assert "SUSPECTED_FRAUD" in reason
