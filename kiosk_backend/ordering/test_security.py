"""Limits that stop anyone from tying up a shop's stock or the server through the public ordering API."""
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from rest_framework.throttling import ScopedRateThrottle

from .models import Order
from .serializer import MAX_CUSTOM_INGREDIENTS
from .tests import OrderingTestBase


class OrderLimitTests(OrderingTestBase):
    def setUp(self):
        super().setUp()
        cache.clear()  # rate limits count requests in the cache

    def test_order_with_too_many_drinks_is_refused(self):
        res = self.order(*[(self.green_tea, 0)] * (settings.ORDER_MAX_ITEMS + 1))
        self.assertEqual(res.status_code, 400)
        self.assertIn("items", res.data)
        self.assertFalse(Order.objects.exists())

    def test_order_with_the_most_drinks_allowed_is_checked_normally(self):
        res = self.order(*[(self.green_tea, 0)] * settings.ORDER_MAX_ITEMS)
        self.assertNotEqual(res.status_code, 400, res.data)

    def test_cart_check_with_too_many_drinks_is_refused(self):
        cart = [self.green_tea.id] * (settings.ORDER_MAX_ITEMS + 1)
        for url in ("/ordering/drinks/", "/ordering/check-order/"):
            res = self.client.get(url, {"shop_id": self.shop.id, "cart": cart})
            self.assertEqual(res.status_code, 400, url)

    def test_designer_drink_with_too_many_ingredients_is_refused(self):
        res = self.client.post("/ordering/log-order/", {
            "shop": self.shop.id,
            "items": [{"custom": [f"X{i}" for i in range(MAX_CUSTOM_INGREDIENTS + 1)], "size": 0}],
        }, format="json")
        self.assertEqual(res.status_code, 400)

    def test_placing_orders_is_rate_limited(self):
        # the test runner lifts the limit for the rest of the suite; put a small one back here
        rates = {**ScopedRateThrottle.THROTTLE_RATES, 'orders': '2/min'}
        with mock.patch.object(ScopedRateThrottle, 'THROTTLE_RATES', rates):
            codes = [self.order((self.green_tea, 0)).status_code for _ in range(3)]
        self.assertEqual(codes, [201, 201, 429])
        self.assertEqual(Order.objects.count(), 2)
