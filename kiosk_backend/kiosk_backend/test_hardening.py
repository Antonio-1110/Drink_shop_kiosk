"""Speed and hardening of the API: query counts on the busy customer endpoints, request ids and
logs, staff sign-in lockout, order tokens on payment endpoints, pickup guessing limits and the
visitor address the rate limits use."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext

from checkout.models import PaymentAttempt
from checkout.tests import CheckoutTestBase
from checkout import services
from operation.models import Drink, DrinkIngredient
from ordering.models import Order
from .observability import client_ip


def queries(fn):
    with CaptureQueriesContext(connection) as q:
        fn()
    return len(q)


class QueryCountTests(CheckoutTestBase):
    def setUp(self):
        super().setUp()
        self.tea_stock.current_stock = Decimal("100000")
        self.tea_stock.save()

    def test_expiry_sweep_skips_orders_still_paying(self):
        # customers in the middle of paying don't make every other request slower
        for _ in range(3):
            order, _ = self.place(self.green_tea)
            self.assertEqual(self.start(order).status_code, 200)
        few = queries(services.expire_unpaid_orders)
        for _ in range(5):
            order, _ = self.place(self.green_tea)
            self.start(order)
        self.assertEqual(queries(services.expire_unpaid_orders), few)
        self.assertEqual(Order.objects.filter(status=Order.Status.PENDING).count(), 8)

    def test_expiry_sweep_still_finds_every_order_that_ran_out(self):
        not_started, _ = self.place(self.green_tea)
        paying, _ = self.place(self.green_tea)
        self.start(paying)
        capped, _ = self.place(self.green_tea)
        self.start(capped)
        fresh, _ = self.place(self.green_tea)
        self.rewind(not_started, 3)   # past the 2 minute grace with no payment
        self.rewind(paying, 16)       # its 15 minute payment ran out
        self.rewind(capped, 31)       # past ORDER_MAX_HOLD_MINUTES
        PaymentAttempt.objects.filter(order=capped).update(expires_at=capped.time + timedelta(hours=1))
        self.assertEqual(services.expire_unpaid_orders(), 3)
        self.assertEqual(self.status(fresh), Order.Status.PENDING)

    def test_menu_queries_dont_grow_with_the_number_of_drinks(self):
        url = f"/ordering/drinks/?shop_id={self.shop.id}"
        before = queries(lambda: self.assertEqual(self.client.get(url).status_code, 200))
        for i in range(5):
            drink = Drink.objects.create(name=f"Tea {i}", s_price=Decimal("2"), l_price=Decimal("3"))
            DrinkIngredient.objects.create(drink=drink, ingredient=self.tea, required_quantity=Decimal("100"))
        res = []
        after = queries(lambda: res.append(self.client.get(url)))
        self.assertEqual(len(res[0].data), 7)
        self.assertEqual(after, before)


class RequestIdTests(CheckoutTestBase):
    def test_each_response_carries_a_request_id(self):
        res = self.client.get("/ordering/shops/")
        self.assertRegex(res["X-Request-ID"], r"^[0-9a-f]{32}$")

    def test_a_sensible_incoming_id_is_kept_and_a_strange_one_replaced(self):
        res = self.client.get("/ordering/shops/", HTTP_X_REQUEST_ID="kiosk-1234abcd")
        self.assertEqual(res["X-Request-ID"], "kiosk-1234abcd")
        res = self.client.get("/ordering/shops/", HTTP_X_REQUEST_ID="bad id\nwith newline")
        self.assertNotIn("bad", res["X-Request-ID"])

    def test_requests_are_logged_with_timing_and_queries(self):
        with self.assertLogs("kiosk.requests", "INFO") as logs:
            self.client.get("/ordering/shops/")
        record = logs.records[0]
        self.assertEqual((record.method, record.path, record.status), ("GET", "/ordering/shops/", 200))
        self.assertGreaterEqual(record.queries, 1)

    @override_settings(SLOW_REQUEST_QUERIES=1)
    def test_heavy_requests_are_warnings(self):
        with self.assertLogs("kiosk.requests", "WARNING") as logs:
            self.client.get(f"/ordering/drinks/?shop_id={self.shop.id}")
        self.assertTrue(logs.records[0].slow)


@override_settings(ADMIN_LOGIN_ATTEMPTS=3, ADMIN_LOGIN_WINDOW_MINUTES=15)
class LoginLimitTests(CheckoutTestBase):
    def setUp(self):
        super().setUp()
        User.objects.create_superuser("boss", password="right-password-123")

    def login(self, password):
        return self.client.post("/admin/login/", {"username": "boss", "password": password})

    def test_address_is_locked_out_after_too_many_wrong_passwords(self):
        for _ in range(3):
            self.assertEqual(self.login("wrong").status_code, 200)
        self.assertEqual(self.login("right-password-123").status_code, 429)

    def test_right_password_clears_the_count(self):
        self.login("wrong")
        self.login("wrong")
        self.assertEqual(self.login("right-password-123").status_code, 302)
        self.client.logout()
        self.login("wrong")
        self.assertEqual(self.login("right-password-123").status_code, 302)

    def test_wrong_basic_auth_counts_too(self):
        bad = {"HTTP_AUTHORIZATION": "Basic Ym9zczp3cm9uZw=="}  # boss:wrong
        url = f"/operation/inventory/shop/{self.shop.id}/ingredient/{self.tea.id}/"
        for _ in range(3):
            res = self.client.patch(url, {"current_stock": 5}, format="json", **bad)
            self.assertIn(res.status_code, (401, 403))
        res = self.client.patch(url, {"current_stock": 5}, format="json", **bad)
        self.assertEqual(res.status_code, 429)


class OrderTokenTests(CheckoutTestBase):
    def test_wrong_token_is_refused(self):
        order, _ = self.place(self.green_tea)
        for res in (self.client.get(f"/ordering/orders/{order.pk}/status/", HTTP_X_ORDER_TOKEN="nope"),
                    self.client.get(f"/ordering/orders/{order.pk}/paynow-qr/?order_token=nope"),
                    self.client.post(f"/ordering/orders/{order.pk}/payments/",
                                     {"method": "fake", "order_token": "nope"}, format="json")):
            self.assertEqual(res.status_code, 403)

    def test_right_token_or_none_works_by_default(self):
        order, token = self.place(self.green_tea)
        self.assertEqual(self.client.get(f"/ordering/orders/{order.pk}/status/", HTTP_X_ORDER_TOKEN=token).status_code, 200)
        self.assertEqual(self.client.get(f"/ordering/orders/{order.pk}/status/").status_code, 200)

    @override_settings(REQUIRE_ORDER_TOKEN=True)
    def test_token_can_be_required(self):
        order, token = self.place(self.green_tea)
        self.assertEqual(self.client.get(f"/ordering/orders/{order.pk}/status/").status_code, 403)
        self.assertEqual(self.client.get(f"/ordering/orders/{order.pk}/status/?order_token={token}").status_code, 200)
        res = self.client.post(f"/ordering/orders/{order.pk}/payments/", {"method": "fake"},
                               format="json", HTTP_X_ORDER_TOKEN=token)
        self.assertEqual(res.status_code, 200, res.data)


@override_settings(PICKUP_FAILURES_PER_SHOP_PER_MINUTE=3)
class PickupGuessingTests(CheckoutTestBase):
    def test_wrong_codes_from_many_addresses_pause_the_shop(self):
        for i in range(3):
            res = self.client.post("/ordering/pickup/", {"shop": self.shop.id, "code": "000000"},
                                   format="json", REMOTE_ADDR=f"10.0.0.{i}")
            self.assertEqual(res.status_code, 404)
        res = self.client.post("/ordering/pickup/", {"shop": self.shop.id, "code": "000000"},
                               format="json", REMOTE_ADDR="10.0.0.99")
        self.assertEqual((res.status_code, res.data["reason"]), (429, "too_many"))


class ClientIpTests(CheckoutTestBase):
    def request(self, forwarded):
        return RequestFactory().get("/", REMOTE_ADDR="172.18.0.5", HTTP_X_FORWARDED_FOR=forwarded)

    def test_made_up_forwarded_addresses_are_ignored_behind_one_proxy(self):
        with self.settings(REST_FRAMEWORK={"NUM_PROXIES": 1}):
            self.assertEqual(client_ip(self.request("6.6.6.6, 203.0.113.9")), "203.0.113.9")

    def test_forwarded_header_ignored_without_proxies(self):
        with self.settings(REST_FRAMEWORK={"NUM_PROXIES": 0}):
            self.assertEqual(client_ip(self.request("6.6.6.6")), "172.18.0.5")

    def test_throttles_use_the_same_rule(self):
        from django.conf import settings
        self.assertIn("NUM_PROXIES", settings.REST_FRAMEWORK)
