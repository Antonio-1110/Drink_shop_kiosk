"""Payment methods. Each one is a Provider; checkout.services does the rest the same way for all.

To add a method (GrabPay, card, a PayNow payment gateway), subclass Provider, implement what the
method supports, and add it to PROVIDERS and settings.PAYMENT_METHODS.
"""
from django.conf import settings
from payments import paynow
from payments.config import paynow_config_from_settings
from zoneinfo import ZoneInfo

SUCCEEDED, PENDING, FAILED = 'succeeded', 'pending', 'failed'


class Provider:
    method = ''
    label = ''

    @property
    def hold_minutes(self):
        # how long the customer gets to pay, which is how long the order's stock stays held
        return settings.PAYMENT_HOLD_MINUTES.get(self.method, settings.PAYMENT_HOLD_MINUTES['default'])

    def start(self, attempt):
        """Begin a payment; returns what the customer needs to pay (e.g. a QR code)."""
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
        event being SUCCEEDED or FAILED. Must verify the notification really came from the provider."""
        raise NotImplementedError


class PayNowManual(Provider):
    """A PayNow QR code paid straight into the company account. PayNow itself doesn't tell us
    when it's paid, so staff confirm the payment (admin) until a PayNow gateway is added."""
    method = 'paynow'
    label = 'PayNow'

    def start(self, attempt):
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

    def start(self, attempt):
        return {}


PROVIDERS = {p.method: p for p in (PayNowManual(), StaffConfirmed())}


def get_provider(method):
    """The provider for a method customers may use, or None."""
    if method not in settings.PAYMENT_METHODS:
        return None
    return PROVIDERS.get(method)
