"""Whole order journeys, start to finish, through the same HTTP endpoints the kiosk, the payment
provider and the drink machine use. After every journey the daily check (check_orders) must find
nothing wrong: status history, payments, stock holds and stock movements all agree."""
from decimal import Decimal

from django.test import override_settings
from django.utils import timezone

from operation.kiosk_auth import new_key
from operation.models import Kiosk, StockMovement
from ordering.models import Order
from .audit import check_orders
from .models import PaymentAttempt, StockHold
from .tests import CheckoutTestBase
from . import services

S = Order.Status
P = PaymentAttempt.Status


@override_settings(MACHINE_SIMULATOR=False)
class LifecycleTests(CheckoutTestBase):
    def setUp(self):
        super().setUp()
        self.kiosk = Kiosk.objects.create(shop=self.shop, machine_id='K-1', operational_status=Kiosk.Status.ONLINE,
                                          last_heartbeat=timezone.now())
        self.key = new_key(self.kiosk)
        self.start_stock = self.stock()

    # --- the callers ---

    def place_order(self, *drinks):
        res = self.order(*[(d, 0) for d in drinks])
        self.assertEqual(res.status_code, 201, res.data)
        return Order.objects.get(pk=res.data['id']), res.data

    def provider_says_paid(self, order, amount=None, ref=None):
        body = {'event': 'succeeded', 'order': order.pk, 'ref': ref or f"tx-{order.pk}",
                'amount': str(order.revenue if amount is None else amount)}
        res = self.client.post("/checkout/webhooks/fake/", body, format='json', HTTP_X_SIGNATURE='good')
        self.assertEqual(res.status_code, 200, res.data)

    def machine(self, path, body=None):
        return self.client.post(path, body or {}, format='json', HTTP_AUTHORIZATION=f"Kiosk {self.key}")

    def take_next(self):
        res = self.machine('/operation/machine/next-order/')
        return res.data['id'] if res.status_code == 200 else None

    def report(self, order, to, reason=''):
        return self.machine(f"/ordering/orders/{order.pk}/progress/", {'status': to, 'reason': reason})

    def collect(self, code):
        return self.client.post("/ordering/pickup/", {'shop': self.shop.pk, 'code': code}, format='json')

    # --- what must hold afterwards ---

    def steps(self, order):
        return [(e.from_status, e.to_status) for e in order.events.order_by('at', 'pk')]

    def assert_books_balance(self):
        self.assertEqual([(r.title, r.problems) for r in check_orders()], [])

    def used(self):
        milk, tea = self.stock()
        return self.start_stock[0] - milk, self.start_stock[1] - tea

    # --- journeys ---

    def test_paid_made_and_collected(self):
        order, placed = self.place_order(self.milk_tea)
        self.assertEqual(self.used(), (Decimal('100'), Decimal('200')))  # held as soon as it's placed
        self.assertEqual(self.start(order).status_code, 200)

        self.provider_says_paid(order)
        self.provider_says_paid(order)  # the provider repeats itself: still paid once
        self.assertEqual(self.status(order), S.PAID)
        self.assertEqual(order.payment_attempts.get().status, P.SUCCEEDED)
        self.assertEqual(self.collect(placed['pickup_pin']).data['reason'], 'preparing')

        self.assertEqual(self.take_next(), order.pk)
        self.assertIsNone(self.take_next())  # nobody else gets the same order
        self.assertEqual(self.status(order), S.PREPARING)
        self.assertEqual(self.report(order, 'READY').status_code, 200)
        self.assertEqual(self.report(order, 'READY').status_code, 200)  # a repeated report is harmless

        res = self.collect(placed['pickup_pin'])
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(self.status(order), S.COLLECTED)
        self.assertIsNotNone(order.collected_at)
        again = self.collect(placed['pickup_pin'])
        self.assertEqual((again.status_code, again.data['reason']), (409, 'already_collected'))
        self.assertEqual(self.report(order, 'FAILED').status_code, 409)  # too late to fail it

        self.assertEqual(self.steps(order), [('', S.PENDING), (S.PENDING, S.PAID), (S.PAID, S.PREPARING),
                                             (S.PREPARING, S.READY), (S.READY, S.COLLECTED)])
        self.assertEqual(self.used(), (Decimal('100'), Decimal('200')))
        self.assertEqual(set(order.stock_holds.values_list('status', flat=True)), {StockHold.Status.CONSUMED})
        self.assert_books_balance()

    def test_collected_with_the_qr_code(self):
        order, placed = self.place_order(self.green_tea)
        self.provider_says_paid(order)
        self.take_next()
        self.report(order, 'READY')
        self.assertTrue(placed['pickup_qr'].startswith('data:image/png'))
        token = Order.objects.get(pk=order.pk).pickup_token  # what the QR code holds
        self.assertEqual(self.collect(token).status_code, 200)
        self.assertEqual(self.status(order), S.COLLECTED)
        self.assert_books_balance()

    def test_customer_cancels_before_paying(self):
        order, placed = self.place_order(self.milk_tea)
        self.start(order)
        url = f"/ordering/orders/{order.pk}/cancel/"
        self.assertEqual(self.client.post(url, {'order_token': 'guess'}, format='json').status_code, 403)
        self.assertEqual(self.client.post(url, {'order_token': placed['order_token']}, format='json').status_code, 200)

        self.assertEqual(self.status(order), S.CANCELLED)
        self.assertEqual(self.used(), (0, 0))  # back on sale straight away
        self.assertEqual(order.payment_attempts.get().status, P.CANCELLED)
        self.assertEqual(self.collect(placed['pickup_pin']).data['reason'], 'cancelled')
        self.assertIsNone(self.take_next())
        self.assertEqual(self.steps(order), [('', S.PENDING), (S.PENDING, S.CANCELLED)])
        self.assert_books_balance()

    def test_not_paid_in_time_then_paid_late(self):
        order, _ = self.place_order(self.milk_tea)
        self.start(order)
        self.rewind(order, 16)  # past the 15 minutes the fake method holds stock for
        self.assertEqual(services.expire_unpaid_orders(), 1)
        self.assertEqual(self.status(order), S.CANCELLED)
        self.assertEqual(self.used(), (0, 0))
        self.assert_books_balance()

        # the money arrives anyway and the ingredients are still there, so the order goes ahead
        self.provider_says_paid(order)
        self.assertEqual(self.status(order), S.PAID)
        self.assertEqual(self.used(), (Decimal('100'), Decimal('200')))
        self.assertEqual(self.take_next(), order.pk)
        self.assertEqual(self.steps(order)[-3:], [(S.PENDING, S.CANCELLED), (S.CANCELLED, S.PAID),
                                                  (S.PAID, S.PREPARING)])
        self.assert_books_balance()

    def test_paid_late_after_it_sold_out_is_refunded(self):
        order, _ = self.place_order(self.milk_tea)
        self.start(order)
        self.rewind(order, 16)
        services.expire_unpaid_orders()
        # someone else buys the last of the milk meanwhile
        self.milk_stock.adjust_stock(-self.milk_stock.current_stock, StockMovement.Reason.WASTE)

        self.provider_says_paid(order)
        self.assertEqual(self.status(order), S.CANCELLED)
        attempt = order.payment_attempts.get()
        self.assertEqual(attempt.status, P.REFUNDED)
        self.assertEqual(self.fake.refunded, [attempt.pk])
        self.assertIsNone(self.take_next())
        self.assert_books_balance()

    def test_wrong_amount_is_refunded_and_order_stays_unpaid(self):
        order, _ = self.place_order(self.green_tea)
        self.start(order)
        self.provider_says_paid(order, amount=Decimal('0.01'))
        self.assertEqual(self.status(order), S.PENDING)
        self.assertEqual(order.payment_attempts.get().status, P.REFUNDED)
        self.assertIsNone(self.take_next())
        self.assert_books_balance()

    def test_machine_fails_retries_then_staff_refund(self):
        order, placed = self.place_order(self.green_tea)
        self.provider_says_paid(order)
        self.take_next()
        self.assertEqual(self.report(order, 'FAILED', 'cup jammed').status_code, 200)
        self.assertEqual(self.collect(placed['pickup_pin']).data['reason'], 'failed')
        self.assertEqual(self.report(order, 'PREPARING').status_code, 200)  # the machine tries again
        self.assertEqual(self.report(order, 'FAILED', 'cup jammed again').status_code, 200)
        self.assert_books_balance()

        self.assertTrue(services.refund_failed_order(order, reason="Jammed twice.", actor='staff:test'))
        self.assertEqual(self.status(order), S.REFUND_NEEDED)
        self.assertEqual(order.payment_attempts.get().status, P.REFUNDED)
        self.assertEqual(self.collect(placed['pickup_pin']).data['reason'], 'refunding')
        self.assertEqual(self.report(order, 'PREPARING').status_code, 409)  # refunded orders stay refunded
        self.assertEqual(self.steps(order), [('', S.PENDING), (S.PENDING, S.PAID), (S.PAID, S.PREPARING),
                                             (S.PREPARING, S.FAILED), (S.FAILED, S.PREPARING),
                                             (S.PREPARING, S.FAILED), (S.FAILED, S.REFUND_NEEDED)])
        self.assert_books_balance()

    def test_machine_can_only_touch_its_own_shops_orders(self):
        other = self.shop.__class__.objects.create(name="Other", address="2 Road")
        order, _ = self.place_order(self.green_tea)
        self.provider_says_paid(order)
        Order.objects.filter(pk=order.pk).update(shop=other)
        self.assertIsNone(self.take_next())
        self.assertEqual(self.report(order, 'PREPARING').status_code, 404)
        self.assertEqual(self.client.post("/operation/machine/next-order/", {}, format='json',
                                          HTTP_AUTHORIZATION="Kiosk not-a-key").status_code, 401)

    def test_a_busy_day_balances(self):
        """Many orders taking every route at once; the books still add up at the end."""
        self.tea_stock.adjust_stock(5000, StockMovement.Reason.RESTOCK)
        self.start_stock = self.stock()
        made, failed = [], []
        for i in range(12):
            order, placed = self.place_order(self.green_tea)
            self.start(order)
            route = i % 4
            if route == 0:
                self.provider_says_paid(order)
                made.append(placed['pickup_pin'])
            elif route == 1:
                self.client.post(f"/ordering/orders/{order.pk}/cancel/", {'order_token': placed['order_token']},
                                 format='json')
            elif route == 2:
                self.rewind(order, 16)
            else:
                self.provider_says_paid(order)
                failed.append(order)
        services.expire_unpaid_orders()
        while (job := self.take_next()) is not None:
            order = Order.objects.get(pk=job)
            self.report(order, 'FAILED' if order in failed else 'READY', 'test')
        for pin in made:
            self.assertEqual(self.collect(pin).status_code, 200)
        for order in failed:
            services.refund_failed_order(order, actor='staff:test')

        counts = {s: Order.objects.filter(status=s).count() for s in S.values}
        self.assertEqual({s: n for s, n in counts.items() if n},
                         {S.COLLECTED: 3, S.CANCELLED: 6, S.REFUND_NEEDED: 3})
        # three collected and three refunded drinks used tea; the cancelled ones gave it back
        self.assertEqual(self.used(), (0, Decimal('300') * 6))
        self.assert_books_balance()
