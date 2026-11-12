"""Payment methods. Each one is a Provider; checkout.services does the rest the same way for all.

To add a method (another gateway, cards), subclass Provider, implement what the method supports,
and add it to PROVIDERS and settings.PAYMENT_METHODS. A gateway that sends one stream of
notifications for several methods (Stripe) also goes in WEBHOOKS. See docs/payments.md.

Methods: paynow (company PayNow QR, staff confirm), staff (cash etc., admin only), sandbox (a fake
bank for testing, no real money), stripe_paynow and stripe_grabpay (Stripe, test or live keys).
"""
from django.conf import settings
from django.core import signing
from payments import paynow
from payments.config import paynow_config_from_settings
from zoneinfo import ZoneInfo

SUCCEEDED, PENDING, FAILED = 'succeeded', 'pending', 'failed'


class PaymentUnavailable(Exception):
    """The payment method can't take payments right now (missing settings, gateway down). The
    message is for staff and the logs, not customers."""


class Provider:
    method = ''
    label = ''
    # True when payments with this method move no real money (sandbox, gateway test keys)
    test_mode = False

    @property
    def hold_minutes(self):
        # how long the customer gets to pay, which is how long the order's stock stays held
        return settings.PAYMENT_HOLD_MINUTES.get(self.method, settings.PAYMENT_HOLD_MINUTES['default'])

    def start(self, attempt, base_url=''):
        """Begin a payment; returns what the customer needs to pay (e.g. a QR code). Called again
        for the same attempt whenever the screen asks again, so it must not start a second payment.
        base_url is this backend's address as the customer's phone reaches it (ends in /).
        Raises PaymentUnavailable if it can't."""
        raise NotImplementedError

    def check_status(self, attempt):
        """Ask the payment method whether the attempt was paid: SUCCEEDED, PENDING, FAILED, or
        None if this method can't tell (then the attempt simply expires)."""
        return None

    def cancel(self, attempt):
        """Tell the payment method to stop accepting this payment, where it supports that."""

    def refund(self, attempt):
        """Refund a payment we can't fulfil. Returns True if refunded, False if staff must do it."""
        return False

    def parse_webhook(self, request):
        """Read a payment notification. Returns a list of (event, order_id, provider_ref, amount),
        or (event, order_id, provider_ref, amount, method) when one gateway reports for several
        methods; event is SUCCEEDED or FAILED. Must check the notification really came from the
        provider, and raise ValueError if it didn't."""
        raise NotImplementedError


class PayNowManual(Provider):
    """A PayNow QR code paid straight into the company account. PayNow itself doesn't tell us
    when it's paid, so staff confirm the payment (admin) until a PayNow gateway is added."""
    method = 'paynow'
    label = 'PayNow'

    def start(self, attempt, base_url=''):
        # banking apps refuse the code after this date; the hold itself ends much sooner
        expires_on = attempt.expires_at.astimezone(ZoneInfo('Asia/Singapore')).date()
        reference = f"ORDER{attempt.order_id}"
        payload = paynow.build_payload(paynow_config_from_settings(), amount=attempt.amount,
                                       reference=reference, expires_on=expires_on)
        return {'qr_code': paynow.qr_png_data_url(payload), 'reference': reference}


class StaffConfirmed(Provider):
    """A payment staff take themselves (cash, or a transfer they checked) and record in the admin."""
    method = 'staff'
    label = 'Confirmed by staff'

    def start(self, attempt, base_url=''):
        return {}


SANDBOX_SALT = 'checkout.sandbox'


def sandbox_ref(attempt):
    # one fixed reference per attempt, so paying twice in the fake bank counts once
    return f"SANDBOX-{attempt.pk}"


def sandbox_pay_path(attempt):
    return f"checkout/sandbox/pay/{signing.dumps(attempt.pk, salt=SANDBOX_SALT)}/"


class SandboxPayNow(Provider):
    """A pretend PayNow for testing the whole order flow with no bank and no money.

    The QR code opens a fake bank page (checkout/sandbox.py) with Pay, Decline and "Pay the wrong
    amount" buttons; it reports back through the same confirm_payment path a real gateway's
    notification uses. Refunds always succeed. Only works while settings.PAYMENTS_SANDBOX is on."""
    method = 'sandbox'
    label = 'PayNow (test)'
    test_mode = True

    def start(self, attempt, base_url=''):
        if not settings.PAYMENTS_SANDBOX:
            raise PaymentUnavailable("The sandbox payment method is off (PAYMENTS_SANDBOX).")
        if not attempt.provider_ref:
            attempt.provider_ref = sandbox_ref(attempt)
            attempt.save(update_fields=['provider_ref'])
        url = f"{base_url}{sandbox_pay_path(attempt)}"
        return {'qr_code': paynow.qr_png_data_url(url), 'reference': f"ORDER{attempt.order_id}",
                'pay_url': url}

    def refund(self, attempt):
        return True


from .stripe_gateway import StripeGrabPay, StripePayNow, StripeWebhooks  # noqa: E402  (they subclass Provider)

PROVIDERS = {p.method: p for p in (PayNowManual(), StaffConfirmed(), SandboxPayNow(),
                                   StripePayNow(), StripeGrabPay())}

# notification endpoints (/checkout/webhooks/<name>/) that serve more than one method
WEBHOOKS = {'stripe': StripeWebhooks()}


def get_provider(method):
    """The provider for a method customers may use, or None."""
    if method not in settings.PAYMENT_METHODS:
        return None
    if method == 'sandbox' and not settings.PAYMENTS_SANDBOX:
        return None
    return PROVIDERS.get(method)


def paynow_method():
    """The method behind the "scan to pay with PayNow" screens: settings.PAYNOW_METHOD when it's
    enabled (sandbox in development, stripe_paynow with a gateway), else the company QR code."""
    method = settings.PAYNOW_METHOD
    return method if get_provider(method) else 'paynow'
