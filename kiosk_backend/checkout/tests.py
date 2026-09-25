from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import override_settings
from django.utils import timezone

from ordering.models import Order, OrderItem
from ordering.tests import OrderingTestBase
from . import services
from .models import PaymentAttempt, StockHold
from .providers import PROVIDERS, Provider, SUCCEEDED, FAILED, PENDING


class FakeProvider(Provider):
    """A payment method that reports whatever the test tells it to."""
    method = 'fake'
    status = None
    refunds = True

    def __init__(self):
        self.refunded = []

    def start(self, attempt):
        return {'pay_url': f"https://pay.example/{attempt.pk}"}

    def check_status(self, attempt):
        return self.status

    def refund(self, attempt):
        self.refunded.append(attempt.pk)
        return self.refunds

    def parse_webhook(self, request):
        if request.headers.get('X-Signature') != 'good':
            raise ValueError("bad signature")
        d = request.data
        return [(d['event'], d['order'], d['ref'], d['amount'])]


@override_settings(PAYMENT_METHODS=['paynow', 'fake'],
                   PAYMENT_HOLD_MINUTES={'default': 10, 'paynow': 10, 'fake': 15},
                   PAYMENT_START_GRACE_MINUTES=2, ORDER_MAX_HOLD_MINUTES=30)
class CheckoutTestBase(OrderingTestBase):
    def setUp(self):
        super().setUp()
        self.fake = FakeProvider()
        patcher = mock.patch.dict(PROVIDERS, {'fake': self.fake})
        patcher.start()
        self.addCleanup(patcher.stop)

    def place(self, *drinks):
        res = self.order(*[(d, OrderItem.Size.SMALL) for d in drinks])
        self.assertEqual(res.status_code, 201, res.data)
        return Order.objects.get(pk=res.data['id']), res.data['order_token']

    def start(self, order, method='fake'):
        return self.client.post(f"/ordering/orders/{order.pk}/payments/", {'method': method}, format='json')

    def rewind(self, order, minutes):
        """Moves the order and its payments `minutes` into the past."""
        delta = timedelta(minutes=minutes)
        Order.objects.filter(pk=order.pk).update(time=order.time - delta)
        for a in order.payment_attempts.all():
            PaymentAttempt.objects.filter(pk=a.pk).update(
                expires_at=a.expires_at - delta, updated_at=a.updated_at - delta, created_at=a.created_at - delta)
        order.refresh_from_db()

    def stock(self):
        self.milk_stock.refresh_from_db()
        self.tea_stock.refresh_from_db()
        return self.milk_stock.current_stock, self.tea_stock.current_stock

    def status(self, order):
        order.refresh_from_db()
        return order.status


class HoldTests(CheckoutTestBase):
    def test_placing_an_order_holds_its_ingredients(self):
        order, _ = self.place(self.milk_tea)
        self.assertEqual(self.stock(), (Decimal("50"), Decimal("800")))
        self.assertEqual(sorted(h.quantity for h in order.stock_holds.all()), [Decimal("100"), Decimal("200")])
        self.assertTrue(all(h.status == StockHold.Status.HELD for h in order.stock_holds.all()))

    def test_hold_follows_the_payment_not_a_fixed_clock(self):
        order, _ = self.place(self.milk_tea)
        # 2 minutes to start paying...
        self.assertEqual(services.hold_expires_at(order), order.time + timedelta(minutes=2))
        # ...then as long as the chosen method allows (15 for this one)
        res = self.start(order)
        self.assertEqual(res.status_code, 200, res.data)
        attempt = PaymentAttempt.objects.get(pk=res.data['attempt'])
        self.assertEqual(services.hold_expires_at(order), attempt.expires_at)
        self.rewind(order, 5)  # past the start grace, but the payment is still open
        self.assertEqual(services.expire_unpaid_orders(), 0)
        self.assertEqual(self.status(order), Order.Status.PENDING)

    def test_starting_again_reuses_the_open_payment(self):
        order, _ = self.place(self.green_tea)
        self.assertEqual(self.start(order).data['attempt'], self.start(order).data['attempt'])

    def test_unpaid_order_is_cancelled_when_its_payment_expires(self):
        order, _ = self.place(self.milk_tea)
        self.start(order)
        self.rewind(order, 16)
        self.assertEqual(services.expire_unpaid_orders(), 1)
        self.assertEqual(self.status(order), Order.Status.CANCELLED)
        self.assertEqual(self.stock(), (Decimal("150"), Decimal("1000")))
        self.assertEqual(order.payment_attempts.get().status, PaymentAttempt.Status.EXPIRED)
        self.assertTrue(all(h.status == StockHold.Status.RELEASED for h in order.stock_holds.all()))
        # running again never returns the stock twice
        self.assertEqual(services.expire_unpaid_orders(), 0)
        self.assertEqual(self.stock(), (Decimal("150"), Decimal("1000")))

    def test_never_started_paying(self):
        order, _ = self.place(self.milk_tea)
        self.rewind(order, 3)
        self.assertEqual(services.expire_unpaid_orders(), 1)

    def test_failed_payment_leaves_time_to_try_another_method(self):
        order, _ = self.place(self.milk_tea)
        self.start(order)
        self.rewind(order, 1)
        services.payment_failed(order, 'fake')
        self.assertEqual(services.hold_expires_at(order).replace(microsecond=0),
                         (timezone.now() + timedelta(minutes=2)).replace(microsecond=0))

    def test_hold_is_capped(self):
        order, _ = self.place(self.milk_tea)
        self.rewind(order, 25)
        attempt, _ = services.start_payment(order, 'fake')  # 15 minutes would pass the 30 minute cap
        self.assertEqual(attempt.expires_at, order.time + timedelta(minutes=30))

    def test_release_returns_what_was_taken_even_if_the_recipe_changed(self):
        order, _ = self.place(self.milk_tea)
        self.milk_tea.required.filter(ingredient=self.milk).update(required_quantity=Decimal("999"))
        services.cancel_order(order)
        self.assertEqual(self.stock(), (Decimal("150"), Decimal("1000")))

    def test_payment_the_method_reports_late_still_counts(self):
        # the payment went through but its notification never arrived
        order, _ = self.place(self.milk_tea)
        self.start(order)
        self.rewind(order, 16)
        self.fake.status = SUCCEEDED
        self.assertEqual(services.expire_unpaid_orders(), 0)
        self.assertEqual(self.status(order), services.PAID)


class ConfirmPaymentTests(CheckoutTestBase):
    def test_paid_order_consumes_its_hold(self):
        order, _ = self.place(self.milk_tea)
        self.start(order)
        attempt = services.confirm_payment(order, 'fake', order.revenue, 'txn-1')
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(self.status(order), services.PAID)
        self.assertTrue(all(h.status == StockHold.Status.CONSUMED for h in order.stock_holds.all()))
        self.assertEqual(self.stock(), (Decimal("50"), Decimal("800")))

    def test_repeated_notification_is_ignored(self):
        order, _ = self.place(self.milk_tea)
        first = services.confirm_payment(order, 'fake', order.revenue, 'txn-1')
        again = services.confirm_payment(order, 'fake', order.revenue, 'txn-1')
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(again.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_late_payment_takes_the_stock_back_if_still_there(self):
        order, _ = self.place(self.milk_tea)
        services.cancel_order(order)
        attempt = services.confirm_payment(order, 'fake', order.revenue, 'txn-1')
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(self.status(order), services.PAID)
        self.assertEqual(self.stock(), (Decimal("50"), Decimal("800")))

    def test_late_payment_is_refunded_when_sold_out(self):
        order, _ = self.place(self.milk_tea)
        services.cancel_order(order)
        self.place(self.milk_tea)  # someone else buys the milk meanwhile
        attempt = services.confirm_payment(order, 'fake', order.revenue, 'txn-1')
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUNDED)
        self.assertEqual(self.fake.refunded, [attempt.pk])
        self.assertEqual(self.status(order), Order.Status.CANCELLED)
        self.assertEqual(self.stock(), (Decimal("50"), Decimal("800")))

    def test_refund_left_to_staff_when_the_method_cant(self):
        order, _ = self.place(self.milk_tea)
        services.cancel_order(order)
        self.place(self.milk_tea)
        self.fake.refunds = False
        with self.assertLogs('checkout.services', 'ERROR'):
            attempt = services.confirm_payment(order, 'fake', order.revenue, 'txn-1')
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUND_NEEDED)

    def test_wrong_amount_is_not_accepted(self):
        order, _ = self.place(self.milk_tea)
        attempt = services.confirm_payment(order, 'fake', Decimal("0.01"), 'txn-1')
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUNDED)
        self.assertEqual(self.status(order), Order.Status.PENDING)

    def test_second_payment_for_a_paid_order_is_refunded(self):
        order, _ = self.place(self.milk_tea)
        services.confirm_payment(order, 'fake', order.revenue, 'txn-1')
        attempt = services.confirm_payment(order, 'fake', order.revenue, 'txn-2')
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUNDED)

    def test_webhook_goes_through_the_same_path(self):
        order, _ = self.place(self.milk_tea)
        self.start(order)
        body = {'event': SUCCEEDED, 'order': order.pk, 'ref': 'txn-9', 'amount': str(order.revenue)}
        bad = self.client.post("/checkout/webhooks/fake/", body, format='json', HTTP_X_SIGNATURE='forged')
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.status(order), Order.Status.PENDING)
        ok = self.client.post("/checkout/webhooks/fake/", body, format='json', HTTP_X_SIGNATURE='good')
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.status(order), services.PAID)
        self.assertEqual(self.client.post("/checkout/webhooks/paynow/", {}, format='json').status_code, 404)


class EndpointTests(CheckoutTestBase):
    def test_cancel_needs_the_order_token_and_frees_stock(self):
        order, token = self.place(self.milk_tea)
        url = f"/ordering/orders/{order.pk}/cancel/"
        self.assertEqual(self.client.post(url, {'order_token': 'guess'}, format='json').status_code, 403)
        other, other_token = self.place(self.green_tea)
        self.assertEqual(self.client.post(url, {'order_token': other_token}, format='json').status_code, 403)
        self.assertEqual(self.client.post(url, {'order_token': token}, format='json').status_code, 200)
        self.assertEqual(self.stock()[0], Decimal("150"))
        self.assertEqual(self.client.post(url, {'order_token': token}, format='json').status_code, 409)

    def test_status(self):
        order, _ = self.place(self.milk_tea)
        self.start(order)
        data = self.client.get(f"/ordering/orders/{order.pk}/status/").data
        self.assertEqual(data['status'], Order.Status.PENDING)
        self.assertEqual([p['method'] for p in data['payments']], ['fake'])
        services.confirm_payment(order, 'fake', order.revenue, 'txn-1')
        data = self.client.get(f"/ordering/orders/{order.pk}/status/").data
        self.assertEqual(data['status'], services.PAID)
        self.assertIsNone(data['hold_expires_at'])

    def test_unknown_or_disabled_method(self):
        order, _ = self.place(self.milk_tea)
        self.assertEqual(self.start(order, 'bitcoin').status_code, 400)
        self.assertEqual(self.start(order, 'staff').status_code, 400)  # staff-only, not for customers

    def test_paynow_qr_shortcut(self):
        order, _ = self.place(self.green_tea)
        res = self.client.get(f"/ordering/orders/{order.pk}/paynow-qr/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['qr_code'].startswith("data:image/png;base64,"))
        self.assertEqual(res.data['reference'], f"ORDER{order.pk}")
        self.assertEqual(PaymentAttempt.objects.get(pk=res.data['attempt']).method, 'paynow')


class StockLogTests(CheckoutTestBase):
    def test_hold_and_release_are_logged(self):
        from operation.models import StockMovement
        order, _ = self.place(self.milk_tea)
        services.cancel_order(order)
        moves = StockMovement.objects.filter(order=order, inventory=self.milk_stock).order_by('created_at', 'pk')
        self.assertEqual([(m.reason, m.change) for m in moves],
                         [(StockMovement.Reason.ORDER, Decimal("-100")), (StockMovement.Reason.RELEASE, Decimal("100"))])
