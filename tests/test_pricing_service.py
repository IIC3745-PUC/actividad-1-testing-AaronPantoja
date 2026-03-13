import unittest

from src.models import CartItem
from src.pricing import PricingService, PricingError


class TestPricingService(unittest.TestCase):
    def setUp(self):
        self.svc = PricingService()

    def test_subtotal_empty_cart_is_zero(self):
        self.assertEqual(self.svc.subtotal_cents([]), 0)

    def test_subtotal_adds_items(self):
        items = [CartItem("A", 100, 2), CartItem("B", 50, 3)]
        self.assertEqual(self.svc.subtotal_cents(items), 100 * 2 + 50 * 3)

    def test_subtotal_raises_when_qty_non_positive(self):
        with self.assertRaises(PricingError) as ctx:
            self.svc.subtotal_cents([CartItem("A", 100, 0)])
        self.assertIn("qty must be > 0", str(ctx.exception))

    def test_subtotal_raises_when_unit_price_negative(self):
        with self.assertRaises(PricingError) as ctx:
            self.svc.subtotal_cents([CartItem("A", -1, 1)])
        self.assertIn("unit_price_cents must be >= 0", str(ctx.exception))

    def test_apply_coupon_none_empty_or_spaces_returns_subtotal(self):
        self.assertEqual(self.svc.apply_coupon(12345, None), 12345)
        self.assertEqual(self.svc.apply_coupon(12345, ""), 12345)
        self.assertEqual(self.svc.apply_coupon(12345, "   "), 12345)

    def test_apply_coupon_save10_is_case_insensitive_and_floors(self):
        self.assertEqual(self.svc.apply_coupon(99, "save10"), 90)
        self.assertEqual(self.svc.apply_coupon(100, " SAVE10 "), 90)

    def test_apply_coupon_clp2000_never_below_zero(self):
        self.assertEqual(self.svc.apply_coupon(5000, "clp2000"), 3000)
        self.assertEqual(self.svc.apply_coupon(1500, "CLP2000"), 0)

    def test_apply_coupon_invalid_raises(self):
        with self.assertRaises(PricingError) as ctx:
            self.svc.apply_coupon(1000, "NOPE")
        self.assertIn("invalid coupon", str(ctx.exception))

    def test_tax_cents_supported_countries(self):
        self.assertEqual(self.svc.tax_cents(10000, "CL"), 1900)
        self.assertEqual(self.svc.tax_cents(10000, "eu"), 2100)
        self.assertEqual(self.svc.tax_cents(10000, " US "), 0)

    def test_tax_cents_unsupported_country_raises(self):
        with self.assertRaises(PricingError) as ctx:
            self.svc.tax_cents(10000, "AR")
        self.assertIn("unsupported country", str(ctx.exception))

    def test_shipping_cl_free_over_threshold_and_paid_under(self):
        self.assertEqual(self.svc.shipping_cents(20000, "CL"), 0)
        self.assertEqual(self.svc.shipping_cents(19999, "cl"), 2500)

    def test_shipping_us_eu_fixed(self):
        self.assertEqual(self.svc.shipping_cents(1, "US"), 5000)
        self.assertEqual(self.svc.shipping_cents(1, "eu"), 5000)

    def test_shipping_unsupported_country_raises(self):
        with self.assertRaises(PricingError) as ctx:
            self.svc.shipping_cents(1, "BR")
        self.assertIn("unsupported country", str(ctx.exception))

    def test_total_cents_composes_components(self):
        items = [CartItem("A", 10000, 2)]
        total = self.svc.total_cents(items, coupon_code=None, country="CL")
        self.assertEqual(total, 20000 + (20000 * 19 // 100) + 0)
