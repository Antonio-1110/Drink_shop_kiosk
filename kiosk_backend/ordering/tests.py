from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from operation.models import Shop, Drink, Ingredient, Inventory, DrinkIngredient
from .models import Order, OrderItem
from .utils import paynow_payload, _crc16


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
