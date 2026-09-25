import io
from datetime import timedelta
from pathlib import Path
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from operation.models import Shop, Drink, Ingredient, Inventory, DrinkIngredient
from .models import Order, OrderItem
from .utils import paynow_payload, _crc16, expire_unpaid_orders, mark_order_paid, cancel_order


class OrderingTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.shop = Shop.objects.create(name="Test Shop", address="1 Test Road")
        self.milk = Ingredient.objects.create(name="Milk", unit_of_measure="mL")
        self.tea = Ingredient.objects.create(name="Tea", unit_of_measure="mL")
        self.milk_tea = Drink.objects.create(name="Milk Tea", s_price=Decimal("3.50"), l_price=Decimal("4.50"))
        self.green_tea = Drink.objects.create(name="Green Tea", s_price=Decimal("2.50"), l_price=Decimal("3.00"))
        DrinkIngredient.objects.create(drink=self.milk_tea, ingredient=self.milk, required_quantity=Decimal("100"))
        DrinkIngredient.objects.create(drink=self.milk_tea, ingredient=self.tea, required_quantity=Decimal("200"))
        DrinkIngredient.objects.create(drink=self.green_tea, ingredient=self.tea, required_quantity=Decimal("300"))
        self.milk_stock = Inventory.objects.create(shop=self.shop, ingredient=self.milk, current_stock=Decimal("150"))
        self.tea_stock = Inventory.objects.create(shop=self.shop, ingredient=self.tea, current_stock=Decimal("1000"))

    def order(self, *items):
        return self.client.post("/ordering/log-order/", {
            "shop": self.shop.id,
            "items": [{"drink": d.id, "size": size, "sugar": 2, "ice": 2} for d, size in items],
        }, format="json")


class KeyInOrderTests(OrderingTestBase):
    def test_creates_order_with_revenue_and_deducts_stock(self):
        res = self.order((self.milk_tea, OrderItem.Size.LARGE), (self.green_tea, OrderItem.Size.SMALL))
        self.assertEqual(res.status_code, 201, res.data)
        order = Order.objects.get(pk=res.data["id"])
        self.assertEqual(order.revenue, Decimal("7.00"))
        self.assertEqual(order.item_quantity, 2)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.milk_stock.refresh_from_db()
        self.tea_stock.refresh_from_db()
        self.assertEqual(self.milk_stock.current_stock, Decimal("50"))
        self.assertEqual(self.tea_stock.current_stock, Decimal("500"))

    def test_rejects_order_that_exceeds_stock(self):
        # two milk teas need 200 mL of milk, only 150 in stock
        res = self.order((self.milk_tea, 0), (self.milk_tea, 0))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["drinks"], [self.milk_tea.id])
        self.assertEqual(Order.objects.count(), 0)
        self.milk_stock.refresh_from_db()
        self.assertEqual(self.milk_stock.current_stock, Decimal("150"))

    def test_missing_inventory_row_counts_as_out_of_stock(self):
        self.milk_stock.delete()
        res = self.order((self.milk_tea, 0))
        self.assertEqual(res.status_code, 409)

    def test_rejects_empty_or_unknown_items(self):
        self.assertEqual(self.order().status_code, 400)
        res = self.client.post("/ordering/log-order/", {
            "shop": self.shop.id, "items": [{"drink": 999}]}, format="json")
        self.assertEqual(res.status_code, 400)


class AvailabilityTests(OrderingTestBase):
    def test_drinks_excludes_what_cannot_be_made(self):
        res = self.client.get("/ordering/drinks/", {"shop_id": self.shop.id, "cart": [self.milk_tea.id]})
        self.assertEqual(res.status_code, 200)
        names = [d["name"] for d in res.data]
        # after one milk tea only 50 mL of milk is left
        self.assertNotIn("Milk Tea", names)
        self.assertIn("Green Tea", names)

    def test_check_order(self):
        ok = self.client.get("/ordering/check-order/", {"shop_id": self.shop.id, "cart": [self.milk_tea.id]})
        self.assertEqual(ok.status_code, 200)
        bad = self.client.get("/ordering/check-order/",
                              {"shop_id": self.shop.id, "cart": [self.milk_tea.id, self.milk_tea.id]})
        self.assertEqual(bad.status_code, 409)


class PayNowTests(OrderingTestBase):
    def test_qr_for_pending_order(self):
        order_id = self.order((self.green_tea, 0)).data["id"]
        res = self.client.get(f"/ordering/orders/{order_id}/paynow-qr/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["qr_code"].startswith("data:image/png;base64,"))
        self.assertEqual(res.data["amount"], "2.50")

    def test_qr_refused_once_order_is_resolved(self):
        order_id = self.order((self.green_tea, 0)).data["id"]
        Order.objects.filter(pk=order_id).update(status=Order.Status.COMPLETED)
        res = self.client.get(f"/ordering/orders/{order_id}/paynow-qr/")
        self.assertEqual(res.status_code, 404)

    def test_payload_has_amount_and_valid_crc(self):
        payload = paynow_payload(Decimal("4.5"), "ORDER1")
        self.assertIn("54044.50", payload)
        self.assertIn("SG.PAYNOW", payload)
        self.assertEqual(payload[-4:], _crc16(payload[:-4]))

    def test_crc_matches_known_value(self):
        # standard CRC-16/CCITT-FALSE check value
        self.assertEqual(_crc16("123456789"), "29B1")


class UnpaidOrderTests(OrderingTestBase):
    def age(self, order_id, minutes):
        Order.objects.filter(pk=order_id).update(time=timezone.now() - timedelta(minutes=minutes))

    def test_expired_order_is_cancelled_and_stock_returned(self):
        order_id = self.order((self.milk_tea, 0)).data["id"]
        self.age(order_id, 11)
        self.assertEqual(expire_unpaid_orders(), 1)
        self.assertEqual(Order.objects.get(pk=order_id).status, Order.Status.CANCELLED)
        self.milk_stock.refresh_from_db()
        self.tea_stock.refresh_from_db()
        self.assertEqual(self.milk_stock.current_stock, Decimal("150"))
        self.assertEqual(self.tea_stock.current_stock, Decimal("1000"))
        # a second run finds nothing, so stock is never returned twice
        self.assertEqual(expire_unpaid_orders(), 0)
        self.milk_stock.refresh_from_db()
        self.assertEqual(self.milk_stock.current_stock, Decimal("150"))

    def test_recent_and_paid_orders_are_kept(self):
        recent = self.order((self.green_tea, 0)).data["id"]
        paid = self.order((self.green_tea, 0)).data["id"]
        self.assertTrue(mark_order_paid(Order.objects.get(pk=paid)))
        self.age(paid, 60)
        self.assertEqual(expire_unpaid_orders(), 0)
        self.assertEqual(Order.objects.get(pk=recent).status, Order.Status.PENDING)
        self.assertEqual(Order.objects.get(pk=paid).status, Order.Status.TBM)

    def test_abandoned_order_frees_stock_for_the_next_customer(self):
        # the first milk tea takes 100 of the 150 mL of milk, so a second can't be made...
        first = self.order((self.milk_tea, 0)).data["id"]
        self.assertEqual(self.order((self.milk_tea, 0)).status_code, 409)
        # ...until the first order goes unpaid past the timeout
        self.age(first, 11)
        self.assertEqual(self.order((self.milk_tea, 0)).status_code, 201)

    def test_qr_refused_after_expiry_and_reports_deadline(self):
        order_id = self.order((self.green_tea, 0)).data["id"]
        self.assertIn("expires_at", self.client.get(f"/ordering/orders/{order_id}/paynow-qr/").data)
        self.age(order_id, 11)
        self.assertEqual(self.client.get(f"/ordering/orders/{order_id}/paynow-qr/").status_code, 404)

    def test_cancel_and_mark_paid_only_apply_to_pending_orders(self):
        order = Order.objects.get(pk=self.order((self.milk_tea, 0)).data["id"])
        self.assertTrue(cancel_order(order))
        self.assertFalse(cancel_order(order))
        self.assertFalse(mark_order_paid(order))
        self.milk_stock.refresh_from_db()
        self.assertEqual(self.milk_stock.current_stock, Decimal("150"))


class PermissionTests(OrderingTestBase):
    url = "/operation/inventory/shop/{}/ingredient/{}/"

    def test_inventory_update_needs_staff(self):
        url = self.url.format(self.shop.id, self.milk.id)
        self.assertEqual(self.client.patch(url, {"current_stock": "0"}, format="json").status_code, 403)
        User = get_user_model()
        self.client.force_authenticate(User.objects.create_user("customer", password="x"))
        self.assertEqual(self.client.patch(url, {"current_stock": "0"}, format="json").status_code, 403)
        self.client.force_authenticate(User.objects.create_user("staff", password="x", is_staff=True))
        res = self.client.patch(url, {"current_stock": "500"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.milk_stock.refresh_from_db()
        self.assertEqual(self.milk_stock.current_stock, Decimal("500"))

    def test_kiosk_endpoints_stay_public(self):
        self.assertEqual(self.client.get("/ordering/shops/").status_code, 200)
        self.assertEqual(self.client.get("/ordering/drinks/", {"shop_id": self.shop.id}).status_code, 200)
        self.assertEqual(self.order((self.green_tea, 0)).status_code, 201)


class ApiContractTests(TestCase):
    def test_committed_schema_is_up_to_date(self):
        # openapi.yaml is the API contract the frontend and mobile app build against
        out = io.StringIO()
        call_command("spectacular", stdout=out)
        committed = (Path(settings.BASE_DIR) / "openapi.yaml").read_text()
        self.assertEqual(out.getvalue(), committed,
                         "openapi.yaml is out of date: run `python manage.py spectacular --file openapi.yaml`")

    def test_schema_and_docs_are_served(self):
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)
        self.assertEqual(self.client.get("/api/docs/").status_code, 200)


class SeedDemoTests(TestCase):
    def test_seed_is_orderable_and_safe_to_rerun(self):
        call_command("seed_demo", stdout=io.StringIO())
        call_command("seed_demo", stdout=io.StringIO())
        self.assertEqual(Shop.objects.count(), 2)
        shop = Shop.objects.first()
        res = APIClient().get("/ordering/drinks/", {"shop_id": shop.id})
        self.assertEqual(len(res.data), Drink.objects.count())
        drink = Drink.objects.get(name="Classic Milk Tea")
        res = APIClient().post("/ordering/log-order/", {
            "shop": shop.id, "items": [{"drink": drink.id, "size": 1, "sugar": 2, "ice": 2}]}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
