"""Payment paths that only go wrong on a bad day: forged or odd Stripe notifications, Stripe being
unreachable, refunds that fail, and cancelling a payment that can't be cancelled."""
import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase, override_settings

from ordering.models import Order
from . import services, stripe_gateway
from .models import PaymentAttempt
from .providers import FAILED, PENDING, PROVIDERS, SUCCEEDED, PaymentUnavailable
from .test_sandbox_payments import WEBHOOK_SECRET, StripeTestBase
from .tests import CheckoutTestBase

NOW = 1_800_000_000


def sign(body, secret=WEBHOOK_SECRET, t=NOW):
    return f"t={t},v1=" + hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()


class SignatureTests(SimpleTestCase):
    body = b'{"type": "payment_intent.succeeded"}'

    def check(self, header, secret=WEBHOOK_SECRET, body=None):
        stripe_gateway.verify_signature(body or self.body, header, secret, now=NOW)

    def test_good_signature(self):
        self.check(sign(self.body))

    def test_refused(self):
        cases = {
            'no secret configured': (sign(self.body), ''),
            'no header': (None, WEBHOOK_SECRET),
            'no v1': (f"t={NOW}", WEBHOOK_SECRET),
            'no timestamp': (sign(self.body).split(',')[1], WEBHOOK_SECRET),
            'timestamp not a number': (sign(self.body).replace(f"t={NOW}", "t=soon"), WEBHOOK_SECRET),
            'too old': (sign(self.body, t=NOW - 301), WEBHOOK_SECRET),
            'from the future': (sign(self.body, t=NOW + 301), WEBHOOK_SECRET),
            'other secret': (sign(self.body, secret='whsec_other'), WEBHOOK_SECRET),
        }
        for name, (header, secret) in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.check(header, secret)

    def test_body_changed_after_signing(self):
        with self.assertRaises(ValueError):
            self.check(sign(self.body), body=self.body.replace(b'succeeded', b'payment_failed'))

    def test_any_of_several_signatures_may_match(self):
        # Stripe sends one v1 per active secret while a secret is being rolled
        good = sign(self.body)
        self.check(f"{good},v1={'0' * 64}")
        self.check(f"t={NOW},v1={'0' * 64},{good.split(',')[1]}")


class StripeNotificationEdgeTests(StripeTestBase):
    def post(self, event):
        body = json.dumps(event).encode()
        return self.client.post('/checkout/webhooks/stripe/', body, content_type='application/json',
                                HTTP_STRIPE_SIGNATURE=sign(body, t=int(time.time())))

    def event(self, order, kind='payment_intent.succeeded', **intent):
        obj = {'id': 'pi_1', 'amount': 350, 'amount_received': 350, 'currency': 'sgd',
               'metadata': {'order_id': str(order.pk), 'method': 'stripe_paynow'}, **intent}
        return {'type': kind, 'data': {'object': obj}}

    def test_other_currency_is_refused(self):
        order, _ = self.place(self.milk_tea)
        self.start(order, 'stripe_paynow')
        with self.assertLogs('checkout.views', 'WARNING'):
            self.assertEqual(self.post(self.event(order, currency='usd')).status_code, 400)
        self.assertEqual(self.status(order), Order.Status.PENDING)

    def test_events_that_are_not_ours_are_acknowledged_and_skipped(self):
        order, _ = self.place(self.milk_tea)
        self.start(order, 'stripe_paynow')
        not_ours = [
            self.event(order, kind='charge.refunded'),
            self.event(order, metadata={}),
            self.event(order, metadata={'order_id': str(order.pk), 'method': 'paynow'}),
            {'type': 'payment_intent.succeeded'},
        ]
        for event in not_ours:
            with self.subTest(event=event):
                self.assertEqual(self.post(event).status_code, 200)
        self.assertEqual(self.status(order), Order.Status.PENDING)

    def test_signed_but_not_json_is_refused(self):
        body = b'not json'
        with self.assertLogs('checkout.views', 'WARNING'):
            res = self.client.post('/checkout/webhooks/stripe/', body, content_type='application/json',
                                   HTTP_STRIPE_SIGNATURE=sign(body, t=int(time.time())))
        self.assertEqual(res.status_code, 400)

    def test_notification_for_an_order_that_does_not_exist(self):
        order, _ = self.place(self.milk_tea)
        event = self.event(order)
        event['data']['object']['metadata']['order_id'] = '999999'
        with self.assertLogs('checkout.views', 'ERROR'):
            self.assertEqual(self.post(event).status_code, 200)  # acknowledged so Stripe stops retrying

    def test_status_mapping(self):
        order, _ = self.place(self.green_tea)
        self.start(order, 'stripe_paynow')
        attempt = order.payment_attempts.get()
        provider = PROVIDERS['stripe_paynow']
        expected = {'succeeded': SUCCEEDED, 'canceled': FAILED, 'requires_payment_method': FAILED,
                    'requires_action': PENDING, 'processing': PENDING}
        for stripe_status, ours in expected.items():
            with self.subTest(stripe_status):
                self.stripe.intents['pi_1']['status'] = stripe_status
                self.assertEqual(provider.check_status(attempt), ours)
        self.assertIsNone(provider.check_status(PaymentAttempt(provider_ref='')))

    def test_stripe_down_while_checking_leaves_the_payment_waiting(self):
        order, _ = self.place(self.green_tea)
        self.start(order, 'stripe_paynow')
        with mock.patch.object(stripe_gateway, 'call', side_effect=PaymentUnavailable('offline')), \
                self.assertLogs('checkout.stripe_gateway', 'ERROR'):
            self.assertIsNone(PROVIDERS['stripe_paynow'].check_status(order.payment_attempts.get()))

    def test_payment_that_cannot_be_cancelled_still_lets_the_order_expire(self):
        order, _ = self.place(self.green_tea)
        self.start(order, 'stripe_paynow')
        self.rewind(order, 16)
        real = self.stripe

        def stripe_refuses_cancel(method, path, *args, **kwargs):
            if path.endswith('/cancel'):
                raise PaymentUnavailable('already paid')
            return real(method, path, *args, **kwargs)

        with mock.patch.object(stripe_gateway, 'call', side_effect=stripe_refuses_cancel), \
                self.assertLogs('checkout.stripe_gateway', 'WARNING'):
            self.assertEqual(services.expire_unpaid_orders(), 1)
        self.assertEqual(self.status(order), Order.Status.CANCELLED)
        self.assertEqual(order.payment_attempts.get().status, PaymentAttempt.Status.EXPIRED)


@override_settings(PAYMENT_METHODS=['paynow', 'fake'])
class RefundFailureTests(CheckoutTestBase):
    def test_refund_that_crashes_is_left_for_staff(self):
        order, _ = self.place(self.milk_tea)
        services.confirm_payment(order, 'fake', order.revenue, provider_ref='tx-1')
        attempt = order.payment_attempts.get()
        attempt.status = PaymentAttempt.Status.REFUND_NEEDED
        attempt.save()
        with mock.patch.object(self.fake, 'refund', side_effect=RuntimeError('gateway 500')), \
                self.assertLogs('checkout.services', 'ERROR') as logs:
            services.refund(attempt)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUND_NEEDED)
        self.assertTrue(any('needs a refund by staff' in line for line in logs.output))

    def test_cancel_that_crashes_does_not_stop_expiry(self):
        order, _ = self.place(self.milk_tea)
        self.start(order)
        self.rewind(order, 16)
        self.fake.status = None
        with mock.patch.object(self.fake, 'cancel', side_effect=RuntimeError('boom'), create=True), \
                self.assertLogs('checkout.services', 'ERROR'):
            self.assertEqual(services.expire_unpaid_orders(), 1)
        self.assertEqual(self.status(order), Order.Status.CANCELLED)

    def test_wrong_amount_never_marks_the_order_paid(self):
        order, _ = self.place(self.milk_tea)
        for amount in (Decimal('0'), order.revenue - Decimal('0.01'), order.revenue + Decimal('0.01')):
            with self.subTest(amount=amount):
                try:
                    services.confirm_payment(order, 'fake', amount, provider_ref=f"tx-{amount}")
                except services.CheckoutError:
                    pass
                self.assertEqual(self.status(order), Order.Status.PENDING)
