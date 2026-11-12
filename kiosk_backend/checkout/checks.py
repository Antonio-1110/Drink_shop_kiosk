from django.conf import settings
from django.core.checks import Error, Warning, register


@register(deploy=True)
def sandbox_off_in_production(app_configs, **kwargs):
    if settings.PAYMENTS_SANDBOX and not settings.DEBUG:
        return [Warning(
            "PAYMENTS_SANDBOX is on: anyone can pay orders with the fake test bank.",
            hint="Unset PAYMENTS_SANDBOX on a shop that takes real orders.", id='checkout.W001')]
    return []


@register()
def stripe_settings(app_configs, **kwargs):
    if not any(m.startswith('stripe_') for m in settings.PAYMENT_METHODS):
        return []
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_WEBHOOK_SECRET:
        return [Error(
            "A Stripe payment method is enabled but STRIPE_SECRET_KEY or STRIPE_WEBHOOK_SECRET is missing.",
            hint="See docs/payments.md.", id='checkout.E001')]
    if '_live_' in settings.STRIPE_SECRET_KEY and not settings.STRIPE_LIVE:
        return [Error(
            "STRIPE_SECRET_KEY is a live key, which moves real money, but STRIPE_LIVE is off.",
            hint="Set STRIPE_LIVE=1 when you mean to take real payments.", id='checkout.E002')]
    return []
