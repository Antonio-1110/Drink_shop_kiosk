"""Sandbox payments (the fake bank) and Stripe in test mode, end to end through the API."""
import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.test import override_settings

from ordering.models import Order
from . import services, stripe_gateway
from .models import PaymentAttempt
from .providers import PROVIDERS, PENDING, sandbox_pay_path
from .tests import CheckoutTestBase


@override_settings(PAYMENTS_SANDBOX=True, PAYMENT_METHODS=['sandbox', 'paynow'], PAYNOW_METHOD='sandbox',
                   PUBLIC_BASE_URL='http://192.168.1.5:8000')
class SandboxTests(CheckoutTestBase):
    def qr(self, order):
        res = self.client.get(f"/ordering/orders/{order.pk}/paynow-qr/")
        self.assertEqual(res.status_code, 200, res.data)
        return res.data

    def bank(self, data, action=None):
        path = data['pay_url'].removeprefix('http://192.168.1.5:8000')
        if action:
            return self.client.post(path, {'action': action})
        return self.client.get(path)

    def test_paynow_screen_gets_a_test_qr_code_that_opens_the_fake_bank(self):
        order, _ = self.place(self.milk_tea)
        data = self.qr(order)
        self.assertEqual(data['method'], 'sandbox')
        self.assertTrue(data['test_mode'])
        self.assertTrue(data['qr_code'].startswith('data:image/png;base64,'))
        self.assertTrue(data['pay_url'].startswith('http://192.168.1.5:8000/checkout/sandbox/pay/'))
        page = self.bank(data)
        self.assertContains(page, 'Pay S$3.50')
        self.assertContains(page, 'Test bank')

    def test_paying_marks_the_order_paid_once(self):
        order, _ = self.place(self.milk_tea)
        data = self.qr(order)
        self.assertEqual(self.bank(data, 'pay').status_code, 302)
        self.assertEqual(self.status(order), Order.Status.PAID)
        self.bank(data, 'pay')  # pressed twice: the same payment, not a second one
        attempts = order.payment_attempts.all()
        self.assertEqual([a.status for a in attempts], [PaymentAttempt.Status.SUCCEEDED])
        self.assertEqual(self.client.get(f"/ordering/orders/{order.pk}/status/").data['status'], 'PAID')

    def test_decline_leaves_the_order_open_to_pay_again(self):
        order, _ = self.place(self.milk_tea)
        data = self.qr(order)
        self.bank(data, 'decline')
        self.assertEqual(order.payment_attempts.get().status, PaymentAttempt.Status.FAILED)
        self.assertEqual(self.status(order), Order.Status.PENDING)
        self.bank(data, 'pay')
        self.assertEqual(self.status(order), Order.Status.PAID)

    def test_wrong_amount_is_refunded_and_the_order_still_waits(self):
        order, _ = self.place(self.milk_tea)
        data = self.qr(order)
        self.bank(data, 'wrong_amount')
        self.assertEqual(self.status(order), Order.Status.PENDING)
        wrong = order.payment_attempts.get(amount=Decimal('3.40'))
        self.assertEqual(wrong.status, PaymentAttempt.Status.REFUNDED)
        self.bank(data, 'pay')
        self.assertEqual(self.status(order), Order.Status.PAID)

    def test_late_payment_goes_through_while_the_stock_lasts(self):
        order, token = self.place(self.milk_tea)
        data = self.qr(order)
        self.client.post(f"/ordering/orders/{order.pk}/cancel/", {'order_token': token}, format='json')
        self.assertEqual(self.status(order), Order.Status.CANCELLED)
        self.bank(data, 'pay')
        self.assertEqual(self.status(order), Order.Status.PAID)
        self.assertEqual(self.stock(), (Decimal("50"), Decimal("800")))

    def test_late_payment_is_refunded_when_the_stock_is_gone(self):
        order, token = self.place(self.milk_tea)
        data = self.qr(order)
        self.client.post(f"/ordering/orders/{order.pk}/cancel/", {'order_token': token}, format='json')
        self.place(self.milk_tea)  # someone else buys the last milk
        self.bank(data, 'pay')
        self.assertEqual(self.status(order), Order.Status.CANCELLED)
        self.assertEqual(order.payment_attempts.get().status, PaymentAttempt.Status.REFUNDED)

    def test_index_lists_waiting_payments(self):
        order, _ = self.place(self.milk_tea)
        self.qr(order)
        self.assertContains(self.client.get('/checkout/sandbox/'), f"Order {order.pk}")

    def test_forged_link_is_refused(self):
        self.assertEqual(self.client.get('/checkout/sandbox/pay/1/').status_code, 404)

    def test_off_means_no_fake_bank_and_the_real_qr_code(self):
        order, _ = self.place(self.milk_tea)
        data = self.qr(order)
        attempt = PaymentAttempt.objects.get(pk=data['attempt'])
        with self.settings(PAYMENTS_SANDBOX=False):
            self.assertEqual(self.client.get('/checkout/sandbox/').status_code, 404)
            self.assertEqual(self.client.get('/' + sandbox_pay_path(attempt)).status_code, 404)
            data = self.qr(order)
            self.assertEqual(data['method'], 'paynow')
            self.assertFalse(data['test_mode'])
            self.assertEqual(self.start(order, 'sandbox').status_code, 400)

    @override_settings(DEBUG=False)
    def test_check_warns_when_sandbox_is_on_without_debug(self):
        from .checks import sandbox_off_in_production
        self.assertEqual([p.id for p in sandbox_off_in_production(None)], ['checkout.W001'])


def intent(pi_id='pi_1', status='requires_action', kind='paynow', **extra):
    next_action = {
        'paynow': {'type': 'paynow_display_qr_code', 'paynow_display_qr_code': {
            'data': '00020101021226...', 'hosted_instructions_url': 'https://pay.stripe.com/test/qr'}},
        'grabpay': {'type': 'redirect_to_url', 'redirect_to_url': {'url': 'https://pm-redirects.stripe.com/x'}},
    }[kind]
    return {'id': pi_id, 'object': 'payment_intent', 'status': status, 'livemode': False,
            'next_action': next_action, **extra}


class FakeStripe:
    """Stands in for stripe_gateway.call and records what was asked."""

    def __init__(self):
        self.calls = []
        self.intents = {}
        self.next_id = 1

    def __call__(self, method, path, data=None, idempotency_key=None):
        self.calls.append((method, path, data, idempotency_key))
        if method == 'POST' and path == 'payment_intents':
            pi = intent(f"pi_{self.next_id}", kind=data['payment_method_types'][0])
            self.next_id += 1
            self.intents[pi['id']] = pi
            return pi
        if method == 'GET' and path.startswith('payment_intents/'):
            return self.intents[path.split('/')[1]]
        if path.endswith('/cancel'):
            self.intents[path.split('/')[1]]['status'] = 'canceled'
            return self.intents[path.split('/')[1]]
        if path == 'refunds':
            return {'id': 're_1', 'status': 'succeeded'}
        raise AssertionError(f"unexpected Stripe call {method} {path}")


WEBHOOK_SECRET = 'whsec_test'


@override_settings(PAYMENT_METHODS=['stripe_paynow', 'stripe_grabpay'], PAYNOW_METHOD='stripe_paynow',
                   STRIPE_SECRET_KEY='sk_test_abc', STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET, STRIPE_LIVE=False,
                   PUBLIC_BASE_URL='https://api.example.sg/')
class StripeTests(CheckoutTestBase):
    def setUp(self):
        super().setUp()
        self.stripe = FakeStripe()
        patcher = mock.patch.object(stripe_gateway, 'call', self.stripe)
        patcher.start()
        self.addCleanup(patcher.stop)

    def webhook(self, order, pi_id, kind='payment_intent.succeeded', amount=350, method='stripe_paynow',
                secret=WEBHOOK_SECRET, timestamp=None):
        body = json.dumps({'type': kind, 'data': {'object': {
            'id': pi_id, 'amount': amount, 'amount_received': amount, 'currency': 'sgd',
            'metadata': {'order_id': str(order.pk), 'method': method}}}}).encode()
        t = timestamp or int(time.time())
        sig = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
        return self.client.post('/checkout/webhooks/stripe/', body, content_type='application/json',
                                HTTP_STRIPE_SIGNATURE=f"t={t},v1={sig}")

    def test_paynow_creates_one_payment_intent_and_shows_its_qr_code(self):
        order, _ = self.place(self.milk_tea)
        res = self.client.get(f"/ordering/orders/{order.pk}/paynow-qr/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['method'], 'stripe_paynow')
        self.assertTrue(res.data['test_mode'])
        self.assertTrue(res.data['qr_code'].startswith('data:image/png'))
        self.assertEqual(res.data['test_pay_url'], 'https://pay.stripe.com/test/qr')
        method, path, data, key = self.stripe.calls[0]
        self.assertEqual((method, path, data['amount'], data['currency']), ('POST', 'payment_intents', 350, 'sgd'))
        self.assertEqual(data['payment_method_types'], ['paynow'])
        self.assertEqual(data['metadata'], {'order_id': order.pk, 'attempt_id': res.data['attempt'],
                                            'method': 'stripe_paynow'})
        self.assertTrue(key.startswith(f"attempt-{res.data['attempt']}-"))
        self.assertEqual(PaymentAttempt.objects.get().provider_ref, 'pi_1')
        # asking again shows the same payment rather than starting another
        self.client.get(f"/ordering/orders/{order.pk}/paynow-qr/")
        self.assertEqual([c[:2] for c in self.stripe.calls], [('POST', 'payment_intents'), ('GET', 'payment_intents/pi_1')])

    def test_grabpay_qr_code_opens_the_grab_page_and_comes_back(self):
        order, _ = self.place(self.milk_tea)
        res = self.start(order, 'stripe_grabpay')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['pay_url'], 'https://pm-redirects.stripe.com/x')
        self.assertEqual(res.data['label'], 'GrabPay')
        self.assertEqual(self.stripe.calls[0][2]['return_url'], 'https://api.example.sg/checkout/paid/')
        self.assertContains(self.client.get('/checkout/paid/'), 'go back to the kiosk')

    def test_signed_notification_pays_the_order_once(self):
        order, _ = self.place(self.milk_tea)
        self.start(order, 'stripe_paynow')
        self.assertEqual(self.webhook(order, 'pi_1').status_code, 200)
        self.assertEqual(self.status(order), Order.Status.PAID)
        self.assertEqual(self.webhook(order, 'pi_1').status_code, 200)  # Stripe retries
        self.assertEqual(list(order.payment_attempts.values_list('status', flat=True)), ['SUCCEEDED'])
        self.assertFalse([c for c in self.stripe.calls if c[1] == 'refunds'])

    def test_unsigned_or_stale_notifications_are_refused(self):
        order, _ = self.place(self.milk_tea)
        self.start(order, 'stripe_paynow')
        with self.assertLogs('checkout.views', 'WARNING'):
            self.assertEqual(self.webhook(order, 'pi_1', secret='whsec_wrong').status_code, 400)
            self.assertEqual(self.webhook(order, 'pi_1', timestamp=int(time.time()) - 3600).status_code, 400)
        self.assertEqual(self.status(order), Order.Status.PENDING)

    def test_failed_payment_frees_the_order_to_try_again(self):
        order, _ = self.place(self.milk_tea)
        self.start(order, 'stripe_paynow')
        self.webhook(order, 'pi_1', kind='payment_intent.payment_failed')
        self.assertEqual(order.payment_attempts.get().status, PaymentAttempt.Status.FAILED)
        res = self.start(order, 'stripe_grabpay')
        self.assertEqual(res.status_code, 200)

    def test_expired_payment_is_cancelled_at_stripe_and_a_late_one_still_counts(self):
        order, _ = self.place(self.milk_tea)
        self.start(order, 'stripe_paynow')
        self.rewind(order, 16)
        self.assertEqual(services.expire_unpaid_orders(), 1)
        self.assertIn(('POST', 'payment_intents/pi_1/cancel', None, None), self.stripe.calls)
        self.assertEqual(self.status(order), Order.Status.CANCELLED)
        # the customer paid just before the cancel reached Stripe
        self.webhook(order, 'pi_1')
        self.assertEqual(self.status(order), Order.Status.PAID)
        self.assertEqual(order.payment_attempts.get().status, PaymentAttempt.Status.SUCCEEDED)

    def test_paid_but_missed_notification_is_found_before_expiring(self):
        order, _ = self.place(self.milk_tea)
        self.start(order, 'stripe_paynow')
        self.stripe.intents['pi_1']['status'] = 'succeeded'
        self.rewind(order, 16)
        self.assertEqual(services.expire_unpaid_orders(), 0)
        self.assertEqual(self.status(order), Order.Status.PAID)

    def test_wrong_amount_is_refunded_through_stripe(self):
        order, _ = self.place(self.milk_tea)
        self.start(order, 'stripe_paynow')
        self.webhook(order, 'pi_1', amount=300)
        attempt = order.payment_attempts.get()
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUNDED)
        self.assertIn(('POST', 'refunds', {'payment_intent': 'pi_1'}, 'refund-pi_1'), self.stripe.calls)

    def test_notification_naming_another_orders_payment_is_ignored(self):
        order, _ = self.place(self.green_tea)
        other, _ = self.place(self.green_tea)
        self.start(order, 'stripe_paynow')
        with self.assertLogs('checkout.views', 'ERROR'):
            self.webhook(other, 'pi_1', amount=250)
        self.assertEqual(self.status(other), Order.Status.PENDING)
        self.assertEqual(self.status(order), Order.Status.PENDING)

    def test_status_mapping(self):
        provider = PROVIDERS['stripe_paynow']
        order, _ = self.place(self.green_tea)
        self.start(order, 'stripe_paynow')
        attempt = order.payment_attempts.get()
        self.assertEqual(provider.check_status(attempt), PENDING)

    def test_live_key_needs_stripe_live(self):
        order, _ = self.place(self.milk_tea)
        with self.settings(STRIPE_SECRET_KEY='sk_live_abc'), self.assertLogs('checkout.views', 'ERROR'):
            self.assertEqual(self.start(order, 'stripe_paynow').status_code, 503)
        with self.settings(STRIPE_SECRET_KEY='sk_live_abc'), self.assertRaises(SystemCheckError):
            call_command('check')


class StripeHelpersTests(CheckoutTestBase):
    def test_form_encoding_matches_stripes_nesting(self):
        self.assertEqual(stripe_gateway.form_encode({'a': 1, 'types': ['paynow'], 'meta': {'order': 5}, 'ok': True}),
                         [('a', '1'), ('types[0]', 'paynow'), ('meta[order]', '5'), ('ok', 'true')])

    def test_cents(self):
        self.assertEqual(stripe_gateway.to_cents(Decimal('4.50')), 450)
        self.assertEqual(stripe_gateway.to_cents('0.1'), 10)


@override_settings(STRIPE_SECRET_KEY='sk_test_abc', STRIPE_LIVE=False)
class StripeCallTests(CheckoutTestBase):
    def test_sends_the_key_form_body_and_idempotency_key(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"id": "pi_9"}'
        with mock.patch('urllib.request.urlopen', return_value=response) as urlopen:
            self.assertEqual(stripe_gateway.call('POST', 'payment_intents', {'amount': 350}, 'k1'), {'id': 'pi_9'})
        req = urlopen.call_args[0][0]
        self.assertEqual(req.full_url, 'https://api.stripe.com/v1/payment_intents')
        self.assertEqual(req.data, b'amount=350')
        self.assertEqual(req.get_header('Authorization'), 'Bearer sk_test_abc')
        self.assertEqual(req.get_header('Idempotency-key'), 'k1')

    def test_stripe_errors_become_payment_unavailable(self):
        import io
        import urllib.error
        from .providers import PaymentUnavailable
        err = urllib.error.HTTPError('u', 402, 'x', {}, io.BytesIO(b'{"error": {"message": "card declined"}}'))
        with mock.patch('urllib.request.urlopen', side_effect=err), \
                self.assertRaisesMessage(PaymentUnavailable, 'card declined'):
            stripe_gateway.call('GET', 'payment_intents/pi_1')
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('offline')), \
                self.assertRaisesMessage(PaymentUnavailable, 'offline'):
            stripe_gateway.call('GET', 'payment_intents/pi_1')
