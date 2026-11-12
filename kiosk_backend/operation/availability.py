"""Whether a shop can sell right now, given what its machine last told us.

Two things stop sales without anyone on site:

- The machine went quiet. A shop whose kiosk has a key (so a real machine is connected) stops
  taking orders when the machine hasn't sent a heartbeat within MACHINE_HEARTBEAT_TIMEOUT_SECONDS,
  or when it says it's in maintenance. Shops with no machine key yet are never closed this way, so
  development and demos keep working.
- The machine says it can't make drinks. A check-in that reports an essential part (cups, sealer,
  pickup, liquids) as empty or faulty closes the shop, and paid orders wait instead of being handed
  to the machine and failed, until a later check-in says the part is fine again.
- The dairy lock. While the kiosk is food-safety locked (sfa_locked, set when a temperature
  reading is out of range), every ingredient with a safe temperature range is off sale until staff
  check it and clear the lock in the admin. Drinks without chilled ingredients keep selling.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import Inventory, Kiosk


def heartbeat_fresh(kiosk, now=None):
    if kiosk.last_heartbeat is None:
        return False
    now = now or timezone.now()
    return now - kiosk.last_heartbeat <= timedelta(seconds=settings.MACHINE_HEARTBEAT_TIMEOUT_SECONDS)


# parts of the machine without which no drink can be made, and the states that mean they can't work
ESSENTIAL_MODULES = ('cups', 'sealer', 'pickup', 'liquids')
DOWN_STATES = ('empty', 'fault', 'error', 'jammed')


def modules_down(kiosk):
    """The essential parts the machine's last check-in said are empty or faulty."""
    states = kiosk.module_states if isinstance(kiosk.module_states, dict) else {}
    return [m for m in ESSENTIAL_MODULES if str(states.get(m, '')).strip().lower() in DOWN_STATES]


def closed_reason(shop):
    """None if the shop can take orders, else (message for the customer, reason code)."""
    kiosk = Kiosk.objects.filter(shop=shop).first()
    if kiosk is None or not kiosk.api_key_hash:
        return None
    if kiosk.operational_status == Kiosk.Status.MAINTENANCE:
        return "This shop is closed for maintenance right now.", "maintenance"
    if not heartbeat_fresh(kiosk):
        return "This shop is closed right now. Please try again later.", "machine_offline"
    if modules_down(kiosk):
        return "This shop can't make drinks right now. Please try again later.", "machine_not_ready"
    return None


def locked_ingredient_ids(shop):
    """Ingredients off sale because of the dairy lock."""
    if not Kiosk.objects.filter(shop=shop, sfa_locked=True).exists():
        return set()
    chilled = Inventory.objects.filter(shop=shop).exclude(min_safe_temp_c=None, max_safe_temp_c=None)
    return set(chilled.values_list('ingredient_id', flat=True))
