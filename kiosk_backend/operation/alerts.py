"""Telling staff what needs a person, so nobody has to watch the admin.

Every minute (`manage.py run_jobs`) each shop is checked for the problems below. A problem opens
an Alert; it is updated while it lasts and resolved by itself once it's gone. Staff get one email
per run listing alerts that opened, alerts still open after ALERT_REMIND_HOURS (a reminder), and
alerts that cleared. Open alerts are listed in the admin under Alerts.

- Machine stopped checking in for MACHINE_OFFLINE_ALERT_MINUTES (not when it said MAINTENANCE
  first, e.g. switched off for the night).
- A machine part is empty or faulty (cups, sealer, pickup, liquids).
- The machine failed MACHINE_FAILURES_TO_PAUSE drinks in a row and the shop stopped selling.
- The dairy lock is on: someone has to check the fridge and clear it.
- Ingredients at or below their reorder threshold.
- Refunds the payment method couldn't make (PayNow by hand, gateway errors).
"""
import logging
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from checkout.models import PaymentAttempt
from .availability import machine_failing, modules_down
from .models import Alert, Inventory, Kiosk, Shop

logger = logging.getLogger(__name__)

K = Alert.Kind


def current_problems(now):
    """{(kind, shop id): message} for everything that needs a person right now."""
    found = {}
    silent_after = timedelta(minutes=settings.MACHINE_OFFLINE_ALERT_MINUTES)
    for kiosk in Kiosk.objects.exclude(api_key_hash=''):
        if kiosk.operational_status != Kiosk.Status.MAINTENANCE and (
                kiosk.last_heartbeat is None or now - kiosk.last_heartbeat > silent_after):
            when = (f"since {timezone.localtime(kiosk.last_heartbeat):%d %b %H:%M}" if kiosk.last_heartbeat
                    else "ever")
            found[K.MACHINE_OFFLINE, kiosk.shop_id] = (
                f"Machine {kiosk.machine_id} hasn't checked in {when}. The shop is closed to new orders; "
                f"paid orders are refunded after {settings.PAID_WAIT_MAX_MINUTES} min.")
        elif down := modules_down(kiosk):
            states = ', '.join(f"{m} {kiosk.module_states.get(m)}" for m in down)
            found[K.MACHINE_NOT_READY, kiosk.shop_id] = (
                f"Machine {kiosk.machine_id} can't make drinks: {states}. The shop is closed to new orders.")
        if machine_failing(kiosk):
            found[K.MACHINE_FAILING, kiosk.shop_id] = (
                f"Machine {kiosk.machine_id} failed {kiosk.consecutive_failures} drinks in a row, so the shop "
                "stopped selling. Check the machine, then put it in maintenance and back, or set the kiosk's "
                "consecutive failures to 0 in the admin.")
        if kiosk.sfa_locked:
            found[K.DAIRY_LOCK, kiosk.shop_id] = (
                f"Dairy lock on: {kiosk.sfa_lock_reason or 'a temperature was out of range'}. Chilled drinks "
                "are off sale until someone checks the fridge and clears the lock on the kiosk in the admin.")

    low = defaultdict(list)
    for inv in (Inventory.objects.filter(ingredient__reorder_threshold__gt=0,
                                         current_stock__lte=F('ingredient__reorder_threshold'))
                .select_related('ingredient').order_by('ingredient__name')):
        low[inv.shop_id].append(f"{inv.ingredient.name} {inv.current_stock:g} {inv.ingredient.unit_of_measure}")
    for shop_id, items in low.items():
        found[K.LOW_STOCK, shop_id] = "Running low, restock soon: " + ", ".join(items) + "."

    refunds = defaultdict(list)
    for attempt in PaymentAttempt.objects.filter(status=PaymentAttempt.Status.REFUND_NEEDED).select_related('order'):
        refunds[attempt.order.shop_id].append(attempt)
    for shop_id, attempts in refunds.items():
        total = sum(a.amount for a in attempts)
        orders = ', '.join(sorted({str(a.order_id) for a in attempts}, key=int))
        found[K.REFUND_BY_HAND, shop_id] = (
            f"{len(attempts)} payment(s) totalling S${total} couldn't be refunded automatically "
            f"(orders {orders}). Refund them, then mark them refunded under Payment attempts.")
    return found


def sync_alerts(now=None):
    """Opens, updates and resolves alerts to match current_problems, then emails staff about the
    changes. Returns (opened, reminded, resolved) lists of alerts."""
    now = now or timezone.now()
    found = current_problems(now)
    opened, reminded, resolved = [], [], []
    remind_before = now - timedelta(hours=settings.ALERT_REMIND_HOURS)
    with transaction.atomic():
        open_alerts = {(a.kind, a.shop_id): a for a in Alert.objects.select_for_update().filter(resolved_at=None)}
        for key, alert in open_alerts.items():
            if key not in found:
                alert.resolved_at = now
                alert.save(update_fields=['resolved_at'])
                resolved.append(alert)
            else:
                alert.message = found[key][:500]
                if alert.notified_at is None or alert.notified_at <= remind_before:
                    reminded.append(alert)
                alert.save(update_fields=['message'])
        for (kind, shop_id), message in found.items():
            if (kind, shop_id) not in open_alerts:
                opened.append(Alert.objects.create(kind=kind, shop_id=shop_id, message=message[:500], opened_at=now))
    for alert in opened:
        logger.error("Alert at shop %s: %s", alert.shop_id, alert.message)
    if (opened or reminded or resolved) and email_staff(opened, reminded, resolved):
        Alert.objects.filter(pk__in=[a.pk for a in opened + reminded]).update(notified_at=now)
    return opened, reminded, resolved


def _line(alert, shops):
    return f"- {shops.get(alert.shop_id, alert.shop_id)}: {alert.get_kind_display()}. {alert.message}"


def email_staff(opened, reminded, resolved):
    """One email about every change. False if nobody is set to receive it or sending failed."""
    if not settings.STAFF_ALERT_EMAILS:
        return False
    shops = dict(Shop.objects.values_list('pk', 'name'))
    parts = []
    if opened:
        parts.append("Needs someone:\n" + "\n".join(_line(a, shops) for a in opened))
    if reminded:
        parts.append(f"Still open (reminder every {settings.ALERT_REMIND_HOURS} h):\n"
                     + "\n".join(_line(a, shops) for a in reminded))
    if resolved:
        parts.append("Sorted itself out:\n" + "\n".join(
            f"- {shops.get(a.shop_id, a.shop_id)}: {a.get_kind_display()}" for a in resolved))
    first = (opened or reminded or resolved)[0]
    subject = f"Kiosk: {first.get_kind_display()} at {shops.get(first.shop_id, first.shop_id)}"
    if not opened and not reminded:
        subject = "Kiosk: problems cleared"
    elif len(opened) + len(reminded) > 1:
        subject += f" and {len(opened) + len(reminded) - 1} more"
    try:
        send_mail(subject, "\n\n".join(parts) + "\n\nOpen alerts are under Alerts in the admin.",
                  None, settings.STAFF_ALERT_EMAILS)
    except Exception:
        logger.exception("Couldn't email staff about alerts")
        return False
    return True
