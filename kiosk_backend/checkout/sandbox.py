"""A fake bank for the sandbox payment method: try the whole order flow with no money.

The sandbox PayNow QR code opens /checkout/sandbox/pay/<token>/ on your phone; the buttons there
do what a customer's bank (and a payment gateway's notification) would. /checkout/sandbox/ lists
the payments waiting, for testing from a computer. Both only exist while PAYMENTS_SANDBOX is on.
"""
from decimal import Decimal

from django.conf import settings
from django.core import signing
from django.http import Http404, HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect
from django.utils.html import format_html, format_html_join
from django.views.decorators.http import require_http_methods

from . import services
from .models import PaymentAttempt
from .providers import SANDBOX_SALT, sandbox_pay_path, sandbox_ref

METHOD = 'sandbox'

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>
:root {{ --bg:#f7f2e8; --card:#fffdf8; --ink:#2d2a26; --muted:#6f6a62; --green:#3f6b4f; --red:#9c3d33; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:17px/1.45 system-ui, sans-serif; }}
main {{ max-width:30rem; margin:0 auto; padding:1.5rem 1rem; }}
.banner {{ background:#f1d98a; border-radius:.5rem; padding:.5rem .75rem; font-size:.9rem; }}
.card {{ background:var(--card); border-radius:.75rem; padding:1.25rem; margin:1rem 0; box-shadow:0 1px 3px #0001; }}
.amount {{ font-size:2.2rem; font-weight:700; }} .muted {{ color:var(--muted); }}
button {{ width:100%; font:inherit; padding:.85rem; border-radius:.6rem; border:0; margin-top:.6rem; cursor:pointer; }}
.pay {{ background:var(--green); color:#fff; }} .alt {{ background:#e9e2d4; color:var(--ink); }}
.decline {{ background:transparent; color:var(--red); }}
ul {{ padding-left:1.1rem; }} a {{ color:var(--green); }}
</style></head><body><main>
<p class="banner">Test bank. Nothing here moves real money.</p>
{body}
</main></body></html>"""


def page(title, body):
    return HttpResponse(PAGE.format(title=title, body=body))


def require_sandbox():
    if not settings.PAYMENTS_SANDBOX:
        raise Http404("The sandbox is off.")


def index(request):
    require_sandbox()
    waiting = (PaymentAttempt.objects.filter(method=METHOD, status=PaymentAttempt.Status.OPEN)
               .select_related('order').order_by('-created_at')[:20])
    recent = (PaymentAttempt.objects.filter(method=METHOD).exclude(status=PaymentAttempt.Status.OPEN)
              .order_by('-updated_at')[:10])
    rows = format_html_join('', '<li><a href="/{}">Order {} · S${}</a> <span class="muted">until {}</span></li>',
                            ((sandbox_pay_path(a), a.order_id, a.amount, a.expires_at.strftime('%H:%M:%S'))
                             for a in waiting))
    done = format_html_join('', '<li><a href="/{}">Order {}</a>: {}</li>',
                            ((sandbox_pay_path(a), a.order_id, a.get_status_display()) for a in recent))
    body = format_html('<h1>Payments waiting</h1><div class="card"><ul>{}</ul>{}</div>'
                       '<h2>Recent</h2><div class="card"><ul>{}</ul></div>',
                       rows, '' if waiting else format_html('<p class="muted">None. Place an order on the kiosk first.</p>'),
                       done)
    return page("Test bank", body)


@require_http_methods(['GET', 'POST'])
def pay(request, token):
    require_sandbox()
    try:
        attempt_id = signing.loads(token, salt=SANDBOX_SALT)
    except signing.BadSignature:
        raise Http404("Unknown payment.") from None
    attempt = PaymentAttempt.objects.select_related('order').filter(pk=attempt_id, method=METHOD).first()
    if attempt is None:
        raise Http404("Unknown payment.") from None
    order = attempt.order

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'pay':
            services.confirm_payment(order, METHOD, attempt.amount, sandbox_ref(attempt))
        elif action == 'wrong_amount':
            # a separate transfer of the wrong amount; it can't pay the order, so it's refunded
            wrong = max(attempt.amount - Decimal('0.10'), Decimal('0.01'))
            services.confirm_payment(order, METHOD, wrong, f"{sandbox_ref(attempt)}-WRONG")
        elif action == 'decline':
            services.payment_failed(order, METHOD, sandbox_ref(attempt))
        return redirect(request.path)

    attempt.refresh_from_db()
    order.refresh_from_db()
    others = order.payment_attempts.exclude(pk=attempt.pk).filter(method=METHOD).order_by('created_at')
    history = format_html_join('', '<li>S${}: {}{}</li>', (
        (a.amount, a.get_status_display(), f" ({a.note})" if a.note else '') for a in others))
    buttons = format_html(
        '<form method="post"><input type="hidden" name="csrfmiddlewaretoken" value="{}">'
        '<button class="pay" name="action" value="pay">Pay S${}</button>'
        '<button class="alt" name="action" value="wrong_amount">Pay the wrong amount</button>'
        '<button class="decline" name="action" value="decline">Decline</button></form>',
        get_token(request), attempt.amount)
    body = format_html(
        '<div class="card"><div class="muted">Pay to {}</div><div class="amount">S${}</div>'
        '<div class="muted">Reference ORDER{}</div></div>'
        '<div class="card"><div>This payment: <strong>{}</strong>{}</div>'
        '<div>Order: <strong>{}</strong></div>{}</div>{}'
        '<p class="muted">Paying after the order was cancelled tries the late-payment path: the order '
        'goes through if the ingredients are still there, and is refunded if not. Pressing Pay twice '
        'counts once. <a href="/checkout/sandbox/">All test payments</a></p>',
        settings.PAYNOW_MERCHANT_NAME, attempt.amount, order.pk,
        attempt.get_status_display(), f" ({attempt.note})" if attempt.note else '',
        order.get_status_display(),
        format_html('<ul class="muted">{}</ul>', history) if others else '',
        buttons)
    return page(f"Pay order {order.pk}", body)
