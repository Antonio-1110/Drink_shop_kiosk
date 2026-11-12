"""Stripe as a payment gateway: PayNow and GrabPay, in test mode (sk_test_ keys, no real money)
or live.

Each attempt becomes one Stripe PaymentIntent in SGD; its ID is the attempt's provider_ref and
the order and method ride along in its metadata. Stripe reports the result to
/checkout/webhooks/stripe/, and expire_unpaid_orders also asks Stripe before giving up on an
attempt, so a missed notification never loses a payment. Talks to Stripe's REST API directly,
so there is no extra package to install. Setup: docs/payments.md.
"""
import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

from django.conf import settings

from payments import paynow
from .providers import FAILED, PENDING, SUCCEEDED, PaymentUnavailable, Provider

logger = logging.getLogger(__name__)

API = 'https://api.stripe.com/v1/'
SIGNATURE_TOLERANCE_SECONDS = 300


def secret_key():
    key = settings.STRIPE_SECRET_KEY
    if not key:
        raise PaymentUnavailable("STRIPE_SECRET_KEY is not set.")
    if '_live_' in key and not settings.STRIPE_LIVE:
        # a live key moves real money; make that a deliberate choice
        raise PaymentUnavailable("STRIPE_SECRET_KEY is a live key but STRIPE_LIVE is off.")
    return key


def is_test_key():
    return '_test_' in settings.STRIPE_SECRET_KEY


def form_encode(data, prefix=''):
    """Stripe's form encoding: nested dicts as a[b]=c, lists as a[0]=c."""
    pairs = []
    items = data.items() if isinstance(data, dict) else enumerate(data)
    for key, value in items:
        name = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, (dict, list, tuple)):
            pairs += form_encode(value, name)
        elif isinstance(value, bool):
            pairs.append((name, 'true' if value else 'false'))
        else:
            pairs.append((name, str(value)))
    return pairs


def call(method, path, data=None, idempotency_key=None):
    """One Stripe API request. Returns the decoded JSON; raises PaymentUnavailable on any error."""
    body = urllib.parse.urlencode(form_encode(data)).encode() if data else None
    req = urllib.request.Request(API + path, data=body, method=method)
    req.add_header('Authorization', f"Bearer {secret_key()}")
    if idempotency_key:
        req.add_header('Idempotency-Key', idempotency_key)
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        try:
            message = json.loads(e.read())['error']['message']
        except Exception:
            message = str(e)
        raise PaymentUnavailable(f"Stripe {method} {path}: {message}") from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise PaymentUnavailable(f"Stripe {method} {path}: {e}") from e


def to_cents(amount):
    return int((Decimal(str(amount)) * 100).to_integral_value())


class StripeProvider(Provider):
    """What PayNow and GrabPay share. Subclasses set method, stripe_type and how the customer pays."""
    stripe_type = ''

    @property
    def test_mode(self):
        return is_test_key()

    def intent_for(self, attempt, base_url):
        """The attempt's PaymentIntent, created (and confirmed) the first time."""
        secret_key()  # refuse early when the keys aren't set up (or are live by mistake)
        if attempt.provider_ref:
            return call('GET', f"payment_intents/{attempt.provider_ref}")
        data = {
            'amount': to_cents(attempt.amount), 'currency': 'sgd',
            'payment_method_types': [self.stripe_type],
            'payment_method_data': {'type': self.stripe_type},
            'confirm': True,
            'description': f"Order {attempt.order_id}",
            'metadata': {'order_id': attempt.order_id, 'attempt_id': attempt.pk, 'method': self.method},
            **self.extra_intent_fields(attempt, base_url),
        }
        # the creation time keeps two databases sharing one Stripe account (two developers'
        # laptops) from reusing each other's keys for their attempt 1
        key = f"attempt-{attempt.pk}-{attempt.created_at.timestamp():.6f}"
        intent = call('POST', 'payment_intents', data, idempotency_key=key)
        attempt.provider_ref = intent['id']
        attempt.save(update_fields=['provider_ref'])
        return intent

    def extra_intent_fields(self, attempt, base_url):
        return {}

    def start(self, attempt, base_url=''):
        intent = self.intent_for(attempt, base_url)
        details = {'reference': f"ORDER{attempt.order_id}", **self.pay_details(intent)}
        if not details.get('qr_code'):
            raise PaymentUnavailable(f"Stripe {intent['id']} gave nothing to pay with "
                                     f"(status {intent.get('status')}).")
        return details

    def pay_details(self, intent):
        raise NotImplementedError

    def check_status(self, attempt):
        if not attempt.provider_ref:
            return None
        try:
            intent = call('GET', f"payment_intents/{attempt.provider_ref}")
        except PaymentUnavailable:
            logger.exception("Couldn't ask Stripe about attempt %s", attempt.pk)
            return None
        status = intent.get('status')
        if status == 'succeeded':
            return SUCCEEDED
        if status in ('canceled', 'requires_payment_method'):
            return FAILED  # requires_payment_method after confirming means the payment failed
        return PENDING

    def cancel(self, attempt):
        if not attempt.provider_ref:
            return
        try:
            call('POST', f"payment_intents/{attempt.provider_ref}/cancel")
        except PaymentUnavailable as e:
            # already paid or already cancelled: a payment still arriving is handled as a late payment
            logger.warning("Couldn't cancel Stripe payment %s: %s", attempt.provider_ref, e)

    def refund(self, attempt):
        if not attempt.provider_ref:
            return False
        refund = call('POST', 'refunds', {'payment_intent': attempt.provider_ref},
                      idempotency_key=f"refund-{attempt.provider_ref}")
        return refund.get('status') in ('succeeded', 'pending')


class StripePayNow(StripeProvider):
    """PayNow through Stripe: Stripe makes the QR code and tells us when it's paid."""
    method = 'stripe_paynow'
    label = 'PayNow'
    stripe_type = 'paynow'

    def pay_details(self, intent):
        qr = (intent.get('next_action') or {}).get('paynow_display_qr_code') or {}
        details = {}
        if qr.get('data'):
            details['qr_code'] = paynow.qr_png_data_url(qr['data'])
        if intent.get('livemode') is False and qr.get('hosted_instructions_url'):
            # in test mode this page has the button that pretends the customer paid
            details['test_pay_url'] = qr['hosted_instructions_url']
        return details


class StripeGrabPay(StripeProvider):
    """GrabPay through Stripe. GrabPay pays on a web page, so the kiosk shows that page's address
    as a QR code for the customer to open on their phone."""
    method = 'stripe_grabpay'
    label = 'GrabPay'
    stripe_type = 'grabpay'

    def extra_intent_fields(self, attempt, base_url):
        return {'return_url': f"{base_url}checkout/paid/"}

    def pay_details(self, intent):
        url = ((intent.get('next_action') or {}).get('redirect_to_url') or {}).get('url')
        if not url:
            return {}
        details = {'qr_code': paynow.qr_png_data_url(url), 'pay_url': url}
        if intent.get('livemode') is False:
            details['test_pay_url'] = url  # Stripe's test page has Authorize / Fail buttons
        return details


def verify_signature(payload, header, secret, now=None):
    """Checks a Stripe-Signature header (t=...,v1=...) against the raw body. Raises ValueError."""
    if not secret:
        raise ValueError("STRIPE_WEBHOOK_SECRET is not set")
    parts = [p.split('=', 1) for p in (header or '').split(',') if '=' in p]
    timestamps = [v for k, v in parts if k == 't']
    signatures = [v for k, v in parts if k == 'v1']
    if not timestamps or not signatures:
        raise ValueError("missing Stripe-Signature")
    try:
        timestamp = int(timestamps[0])
    except ValueError:
        raise ValueError("bad Stripe-Signature timestamp") from None
    if abs((now or time.time()) - timestamp) > SIGNATURE_TOLERANCE_SECONDS:
        raise ValueError("Stripe-Signature too old")
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in signatures):
        raise ValueError("Stripe-Signature doesn't match")


class StripeWebhooks:
    """Stripe sends every PaymentIntent event to one endpoint, whichever method it was."""

    def parse_webhook(self, request):
        verify_signature(request.body, request.headers.get('Stripe-Signature'), settings.STRIPE_WEBHOOK_SECRET)
        event = json.loads(request.body)
        kinds = {'payment_intent.succeeded': SUCCEEDED, 'payment_intent.payment_failed': FAILED}
        kind = kinds.get(event.get('type'))
        intent = (event.get('data') or {}).get('object') or {}
        meta = intent.get('metadata') or {}
        if kind is None or not meta.get('order_id') or not str(meta.get('method', '')).startswith('stripe_'):
            return []  # not about one of our orders (or an event we don't use): acknowledge and skip
        if intent.get('currency') != 'sgd':
            raise ValueError(f"unexpected currency {intent.get('currency')}")
        amount = Decimal(intent.get('amount_received') or intent.get('amount') or 0) / 100
        return [(kind, int(meta['order_id']), intent['id'], amount, meta['method'])]
