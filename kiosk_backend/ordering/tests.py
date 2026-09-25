import io
from unittest import mock
from pathlib import Path
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient
from operation.models import Shop, Drink, Ingredient, Inventory, DrinkIngredient, DesignerConfig
from .models import Order, OrderItem


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

    def test_items_keep_sale_price_and_nutri_grade(self):
        res = self.order((self.milk_tea, OrderItem.Size.LARGE))
        self.assertEqual(res.status_code, 201, res.data)
        self.milk_tea.l_price = Decimal("9.99")
        self.milk_tea.save()
        item = OrderItem.objects.get(order_id=res.data["id"])
        self.assertEqual(item.unit_price, Decimal("4.50"))
        self.assertEqual(item.nutri_grade, "A")  # test ingredients carry no sugar or fat

    def test_retired_drink_cannot_be_ordered(self):
        self.green_tea.is_active = False
        self.green_tea.save()
        self.assertEqual(self.order((self.green_tea, 0)).status_code, 400)

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
        self.assertEqual(res.status_code, 409)

    def test_qr_pays_the_configured_account(self):
        order_id = self.order((self.green_tea, 0)).data["id"]
        with self.settings(PAYNOW_PROXY_VALUE="201912345K", PAYNOW_MERCHANT_NAME="Test Drinks"):
            res = self.client.get(f"/ordering/orders/{order_id}/paynow-qr/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["reference"], f"ORDER{order_id}")

    def test_qr_refused_when_paynow_not_configured(self):
        order_id = self.order((self.green_tea, 0)).data["id"]
        with self.settings(PAYNOW_PROXY_VALUE=""), self.assertLogs("checkout.views", "ERROR"):
            res = self.client.get(f"/ordering/orders/{order_id}/paynow-qr/")
        self.assertEqual(res.status_code, 503)

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


class PickupTests(OrderingTestBase):
    def setUp(self):
        super().setUp()
        cache.clear()  # the pickup rate limit counts attempts in the cache

    def place(self):
        res = self.order((self.green_tea, 0))
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def collect(self, code, shop=None):
        return self.client.post("/ordering/pickup/", {"shop": shop or self.shop.id, "code": code}, format="json")

    def pay(self, order_id):
        Order.objects.filter(pk=order_id).update(status=Order.Status.PAID)

    def test_new_order_gets_pin_and_qr(self):
        data = self.place()
        self.assertRegex(data["pickup_pin"], r"^\d{6}$")
        self.assertTrue(data["pickup_qr"].startswith("data:image/png;base64,"))
        order = Order.objects.get(pk=data["id"])
        self.assertEqual(order.pickup_pin, data["pickup_pin"])
        self.assertGreaterEqual(len(order.pickup_token), 20)
        # the codes are never shown again, e.g. in the order status
        status_data = self.client.get(f"/ordering/orders/{data['id']}/status/").data
        self.assertNotIn(data["pickup_pin"], str(status_data))

    def test_collect_by_pin_once(self):
        data = self.place()
        self.pay(data["id"])
        res = self.collect(data["pickup_pin"])
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["status"], Order.Status.COLLECTED)
        self.assertIsNotNone(Order.objects.get(pk=data["id"]).collected_at)
        again = self.collect(data["pickup_pin"])
        self.assertEqual((again.status_code, again.data["reason"]), (409, "already_collected"))

    def test_collect_by_qr_token(self):
        data = self.place()
        self.pay(data["id"])
        token = Order.objects.get(pk=data["id"]).pickup_token
        self.assertEqual(self.collect(token).status_code, 200)

    def test_unpaid_order_is_not_handed_over(self):
        data = self.place()
        res = self.collect(data["pickup_pin"])
        self.assertEqual((res.status_code, res.data["reason"]), (409, "not_paid"))
        self.assertEqual(Order.objects.get(pk=data["id"]).status, Order.Status.PENDING)

    def test_wrong_code_or_other_shop(self):
        data = self.place()
        self.pay(data["id"])
        wrong = "000000" if data["pickup_pin"] != "000000" else "111111"
        self.assertEqual(self.collect(wrong).status_code, 404)
        other = Shop.objects.create(name="Other", address="2 Road")
        self.assertEqual(self.collect(data["pickup_pin"], shop=other.id).status_code, 404)
        self.assertEqual(self.client.post("/ordering/pickup/", {"code": "123456"}, format="json").status_code, 400)

    def test_pins_are_unique_among_uncollected_orders(self):
        with mock.patch("ordering.pickup.secrets.randbelow", side_effect=[42, 42, 7]):
            first, second = self.place(), self.place()
        self.assertEqual(first["pickup_pin"], "000042")
        self.assertEqual(second["pickup_pin"], "000007")

    def test_guessing_is_rate_limited(self):
        codes = [self.collect(f"{n:06d}").status_code for n in range(12)]
        self.assertEqual(codes[:10], [404] * 10)
        self.assertEqual(codes[10:], [429, 429])


class DesignerTests(OrderingTestBase):
    def setUp(self):
        super().setUp()
        Ingredient.objects.filter(pk=self.tea.pk).update(
            code="BT", kind=Ingredient.Kind.LIQUID, share=3, offered_in_designer=True, designer_category="Tea")
        Ingredient.objects.filter(pk=self.milk.pk).update(
            code="FM", kind=Ingredient.Kind.LIQUID, share=2, offered_in_designer=True, designer_category="Milk",
            designer_price=Decimal("0.80"))
        self.pearls = Ingredient.objects.create(name="Pearls", unit_of_measure="g", code="TP",
                                                kind=Ingredient.Kind.TOPPING, offered_in_designer=True)
        self.pearl_stock = Inventory.objects.create(shop=self.shop, ingredient=self.pearls, current_stock=Decimal("100"))
        self.syrup = Ingredient.objects.create(name="Syrup", unit_of_measure="mL", code="BS",
                                               kind=Ingredient.Kind.OTHER, sugar_per_100=65)
        self.syrup_stock = Inventory.objects.create(shop=self.shop, ingredient=self.syrup, current_stock=Decimal("1000"))
        config = DesignerConfig.load()
        config.sweetener = self.syrup
        config.save()

    def custom(self, codes, size=0, sugar=4):
        return self.client.post("/ordering/log-order/", {
            "shop": self.shop.id, "items": [{"custom": codes, "size": size, "sugar": sugar, "ice": 2}]}, format="json")

    def test_options(self):
        res = self.client.get("/ordering/designer/options/", {"shop_id": self.shop.id})
        self.assertEqual(res.status_code, 200)
        by_code = {i["code"]: i for i in res.data["ingredients"]}
        self.assertEqual(set(by_code), {"BT", "FM", "TP"})  # the sweetener isn't picked
        self.assertEqual(by_code["TP"]["kind"], "topping")
        # a large cup of only milk needs 500 mL, the shop has 150
        self.assertFalse(by_code["FM"]["available"])
        self.assertTrue(by_code["BT"]["available"])
        self.assertEqual(res.data["pricing"]["overrides"], {"FM": "0.80"})
        self.assertEqual(res.data["sweetener"]["code"], "BS")
        self.assertEqual(self.client.get("/ordering/designer/options/", {"shop_id": 999}).status_code, 404)

    def test_order_custom_drink_prices_and_holds_stock(self):
        res = self.custom(["BT", "FM", "TP"], sugar=2)
        self.assertEqual(res.status_code, 201, res.data)
        order = Order.objects.get(pk=res.data["id"])
        # small cup 2.80 + tea 0.50 + milk 0.80 + pearls 0.60
        self.assertEqual(order.revenue, Decimal("4.70"))
        self.assertEqual(res.data["items"][0]["custom"], ["BT", "FM", "TP"])
        amounts = {l.ingredient.code: l.amount for l in order.items.get().custom_ingredients.select_related("ingredient")}
        # 360 mL split 3:2, 60 g of pearls, half of 30 mL syrup at 50% sugar
        self.assertEqual(amounts, {"BT": Decimal("216.00"), "FM": Decimal("144.00"), "TP": Decimal("60.00"),
                                   "BS": Decimal("15.00")})
        self.tea_stock.refresh_from_db()
        self.pearl_stock.refresh_from_db()
        self.assertEqual(self.tea_stock.current_stock, Decimal("784"))
        self.assertEqual(self.pearl_stock.current_stock, Decimal("40"))
        self.assertTrue(order.items.get().nutri_grade)

    def test_mixed_cart_and_shortfall(self):
        # a menu milk tea (100 mL milk) plus a custom milk drink (360 mL) is more than the 150 mL there is
        res = self.client.post("/ordering/log-order/", {"shop": self.shop.id, "items": [
            {"drink": self.milk_tea.id, "size": 0, "sugar": 2, "ice": 2},
            {"custom": ["FM"], "size": 0, "sugar": 0, "ice": 2}]}, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["options"], ["FM"])
        self.assertEqual(res.data["drinks"], [self.milk_tea.id])
        self.assertEqual(Order.objects.count(), 0)

    def test_invalid_custom_drinks(self):
        self.assertEqual(self.custom(["XX"]).status_code, 400)
        self.assertEqual(self.custom(["TP"]).status_code, 400)  # no liquid
        self.assertEqual(self.custom(["BS"]).status_code, 400)  # the sweetener isn't pickable
        both = self.client.post("/ordering/log-order/", {"shop": self.shop.id, "items": [
            {"drink": self.milk_tea.id, "custom": ["BT"], "size": 0}]}, format="json")
        self.assertEqual(both.status_code, 400)

    def test_cancelling_returns_custom_stock(self):
        from checkout.services import cancel_order
        order = Order.objects.get(pk=self.custom(["BT", "TP"]).data["id"])
        cancel_order(order)
        self.tea_stock.refresh_from_db()
        self.pearl_stock.refresh_from_db()
        self.assertEqual((self.tea_stock.current_stock, self.pearl_stock.current_stock), (Decimal("1000"), Decimal("100")))
