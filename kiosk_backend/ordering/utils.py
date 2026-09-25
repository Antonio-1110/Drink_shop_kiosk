from operation.models import Drink, DrinkIngredient, Shop, Inventory
from .models import Order
from django.db import transaction
from django.db.models import F, Case, When, DecimalField
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from zoneinfo import ZoneInfo
from payments import paynow
from payments.config import paynow_config_from_settings


def qr_gen(rev, reference, expires_on=None):
    # returns the PayNow QR as a base64 PNG the frontend can put in an <img>
    payload = paynow.build_payload(paynow_config_from_settings(), amount=rev, reference=reference,
                                   expires_on=expires_on)
    return paynow.qr_png_data_url(payload)

def verify_drink_ids(incoming_drink_ids):
    valid_ids_list = [int(i) for i in incoming_drink_ids if str(i).isdigit()]
    unique_count = len(set(valid_ids_list))
    existing_drink_count = Drink.objects.filter(id__in=valid_ids_list).count()
    if existing_drink_count == unique_count:
        return True, valid_ids_list, "All drink IDs are valid."
    else:
        return False, [], "One or more drink IDs do not exist."

def aggregate_ingredients(drinks):
    a_d = {}
    x = DrinkIngredient.objects.filter(drink_id__in=drinks).values('drink','ingredient','required_quantity')
    for i in x:
        if i['ingredient'] not in a_d: a_d[i['ingredient']] = i['required_quantity'] * drinks.count(int(i['drink']))
        else:a_d[i['ingredient']] += i['required_quantity'] * drinks.count(int(i['drink']))
    return a_d

def inventory_update(shop, cart : list = []):
    # deducts the ingredients used by every drink in the cart from the shop's stock
    a_d = aggregate_ingredients(cart)
    for ingredient_id, amount in a_d.items():
        Inventory.objects.filter(shop=shop, ingredient_id=ingredient_id).update(
            current_stock=F('current_stock') - amount)
    return True

def inventory_restock(shop, cart : list = []):
    # puts back the ingredients a cancelled order had taken
    a_d = aggregate_ingredients(cart)
    for ingredient_id, amount in a_d.items():
        Inventory.objects.filter(shop=shop, ingredient_id=ingredient_id).update(
            current_stock=F('current_stock') + amount)
    return True

def cancel_order(order):
    # the status update only matches while the order is still pending, so two
    # callers racing to cancel the same order can't return its stock twice
    with transaction.atomic():
        if not Order.objects.filter(pk=order.pk, status=Order.Status.PENDING).update(
                status=Order.Status.CANCELLED):
            return False
        inventory_restock(order.shop, list(order.items.values_list('drink_id', flat=True)))
    return True

def mark_order_paid(order):
    # TBM ("to be made") is the paid state until the Order model gets a proper Paid status
    return bool(Order.objects.filter(pk=order.pk, status=Order.Status.PENDING).update(
        status=Order.Status.TBM))

def payment_deadline(order):
    return order.time + timedelta(minutes=settings.ORDER_PAYMENT_TIMEOUT_MINUTES)

def paynow_expiry_date(order):
    # PayNow expiry is a whole day, so this stops the code working after the Singapore date the
    # order expires on; the order itself is cancelled much sooner
    return payment_deadline(order).astimezone(ZoneInfo("Asia/Singapore")).date()

def expire_unpaid_orders(shop=None):
    # cancels orders left unpaid past the timeout and returns their stock
    cutoff = timezone.now() - timedelta(minutes=settings.ORDER_PAYMENT_TIMEOUT_MINUTES)
    stale = Order.objects.filter(status=Order.Status.PENDING, time__lt=cutoff)
    if shop is not None:
        stale = stale.filter(shop=shop)
    return sum(cancel_order(order) for order in stale)

def inventory_check(shop, cart : list = []):
    a_d = aggregate_ingredients(cart)
    inventories_with_reserved = Inventory.objects.filter(shop=shop).annotate(
    effective_stock=Case(
        *[When(ingredient_id=k, then=F('current_stock') - a_d[k]) for k in a_d.keys()],
        default=F('current_stock'), # here when it minus the aggregate amount it might already go negative
        output_field=DecimalField(max_digits=10, decimal_places=2)))
    failing_ingredient_ids = inventories_with_reserved.filter(
        effective_stock__lt=F('ingredient__drinkingredient__required_quantity')
    ).values_list('ingredient__id', flat=True).distinct()
    unfulfillable_drink_ids = DrinkIngredient.objects.filter(
        ingredient__id__in=failing_ingredient_ids
    ).values_list('drink__id', flat=True).distinct()
    return unfulfillable_drink_ids
    
def check_cart_fulfillment(shop, cart : list = []):
    a_d = aggregate_ingredients(cart)
    inventories_with_reserved = Inventory.objects.filter(shop=shop).annotate(
    effective_stock=Case(
        *[When(ingredient_id=k, then=F('current_stock') - a_d[k]) for k in a_d.keys()],
        default=F('current_stock'), # here when it minus the aggregate amount it might already go negative
        output_field=DecimalField(max_digits=10, decimal_places=2)))
    insufficient_inventory_qs = inventories_with_reserved.filter(effective_stock__lt=Decimal('0.00'))
    # an ingredient the shop has no inventory row for counts as out of stock
    stocked_ids = set(Inventory.objects.filter(shop=shop).values_list('ingredient_id', flat=True))
    missing_ids = [k for k in a_d.keys() if k not in stocked_ids]
    if not insufficient_inventory_qs.exists() and not missing_ids:
        return True, [], []
    failing_ingredient_ids = list(insufficient_inventory_qs.values_list('ingredient', flat=True)) + missing_ids
    affected_drink_ids = DrinkIngredient.objects.filter(drink__id__in=cart,
    ingredient__id__in=failing_ingredient_ids ).values_list('drink', flat=True).distinct()
    return False, list(affected_drink_ids), failing_ingredient_ids