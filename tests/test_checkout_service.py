import unittest
from unittest.mock import Mock, patch

from src.models import CartItem, Order
from src.pricing import PricingError
from src.checkout import CheckoutService, ChargeResult


class TestCheckoutService(unittest.TestCase):
    def setUp(self):
        self.payments = Mock()
        self.email = Mock()
        self.fraud = Mock()
        self.repo = Mock()

    def _checkout(self, pricing):
        return CheckoutService(
            payments=self.payments,
            email=self.email,
            fraud=self.fraud,
            repo=self.repo,
            pricing=pricing,
        )

    def test_checkout_invalid_user_returns_invalid_user(self):
        svc = self._checkout(pricing=Mock())
        out = svc.checkout(user_id="   ", items=[], payment_token="tok", country="CL")
        self.assertEqual(out, "INVALID_USER")
        self.payments.charge.assert_not_called()
        self.repo.save.assert_not_called()
        self.email.send_receipt.assert_not_called()

    def test_checkout_invalid_cart_when_pricing_raises(self):
        pricing = Mock()
        pricing.total_cents.side_effect = PricingError("unsupported country")
        svc = self._checkout(pricing=pricing)

        out = svc.checkout(user_id="u1", items=[], payment_token="tok", country="XX", coupon_code=None)
        self.assertEqual(out, "INVALID_CART:unsupported country")
        self.fraud.score.assert_not_called()
        self.payments.charge.assert_not_called()
        self.repo.save.assert_not_called()
        self.email.send_receipt.assert_not_called()

    def test_checkout_rejected_when_fraud_score_high(self):
        pricing = Mock()
        pricing.total_cents.return_value = 1234
        svc = self._checkout(pricing=pricing)
        self.fraud.score.return_value = 80

        out = svc.checkout(user_id="u1", items=[CartItem("A", 1, 1)], payment_token="tok", country="CL")
        self.assertEqual(out, "REJECTED_FRAUD")
        self.payments.charge.assert_not_called()
        self.repo.save.assert_not_called()
        self.email.send_receipt.assert_not_called()

    def test_checkout_payment_failed_returns_reason(self):
        pricing = Mock()
        pricing.total_cents.return_value = 2500
        svc = self._checkout(pricing=pricing)
        self.fraud.score.return_value = 0
        self.payments.charge.return_value = ChargeResult(ok=False, reason="DECLINED")

        out = svc.checkout(user_id="u1", items=[], payment_token="tok", country="CL")
        self.assertEqual(out, "PAYMENT_FAILED:DECLINED")
        self.repo.save.assert_not_called()
        self.email.send_receipt.assert_not_called()

    def test_checkout_success_saves_order_and_sends_receipt(self):
        pricing = Mock()
        pricing.total_cents.return_value = 7777
        svc = self._checkout(pricing=pricing)
        self.fraud.score.return_value = 0
        self.payments.charge.return_value = ChargeResult(ok=True, charge_id="ch_123")

        with patch("src.checkout.uuid.uuid4", return_value="00000000-0000-0000-0000-000000000000"):
            out = svc.checkout(
                user_id="u1",
                items=[CartItem("A", 1, 1)],
                payment_token="tok",
                country=" cl ",
                coupon_code="SAVE10",
            )

        self.assertEqual(out, "OK:00000000-0000-0000-0000-000000000000")
        self.payments.charge.assert_called_once_with(user_id="u1", amount_cents=7777, payment_token="tok")
        self.fraud.score.assert_called_once_with("u1", 7777)
        self.repo.save.assert_called_once()
        saved_order = self.repo.save.call_args[0][0]
        self.assertIsInstance(saved_order, Order)
        self.assertEqual(saved_order.order_id, "00000000-0000-0000-0000-000000000000")
        self.assertEqual(saved_order.user_id, "u1")
        self.assertEqual(saved_order.total_cents, 7777)
        self.assertEqual(saved_order.payment_charge_id, "ch_123")
        self.assertEqual(saved_order.coupon_code, "SAVE10")
        self.assertEqual(saved_order.country, "CL")
        self.email.send_receipt.assert_called_once_with("u1", "00000000-0000-0000-0000-000000000000", 7777)

    def test_checkout_success_uses_unknown_charge_id_when_none(self):
        pricing = Mock()
        pricing.total_cents.return_value = 100
        svc = self._checkout(pricing=pricing)
        self.fraud.score.return_value = 0
        self.payments.charge.return_value = ChargeResult(ok=True, charge_id=None)

        with patch("src.checkout.uuid.uuid4", return_value="11111111-1111-1111-1111-111111111111"):
            out = svc.checkout(user_id="u1", items=[], payment_token="tok", country="US", coupon_code=None)

        self.assertEqual(out, "OK:11111111-1111-1111-1111-111111111111")
        saved_order = self.repo.save.call_args[0][0]
        self.assertEqual(saved_order.payment_charge_id, "UNKNOWN")
