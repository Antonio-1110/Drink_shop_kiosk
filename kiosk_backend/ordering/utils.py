from operation.models import Drink, DrinkIngredient, Shop, Inventory
from django.db.models import F, Case, When, DecimalField
from decimal import Decimal
from django.conf import settings
import base64
import io
import qrcode


def _tlv(tag, value):
    # EMVCo fields are tag + 2-digit length + value
    return f"{tag}{len(value):02d}{value}"

def _crc16(payload):
    # CRC-16/CCITT-FALSE, required as the last field of an SGQR code
    crc = 0xFFFF
    for byte in payload.encode():
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return f"{crc:04X}"

def paynow_payload(amount, reference):
    merchant = (_tlv("00", "SG.PAYNOW")
                + _tlv("01", "2")  # proxy type 2 = UEN
                + _tlv("02", settings.PAYNOW_UEN)
                + _tlv("03", "0"))  # amount is not editable
    payload = (_tlv("00", "01")
               + _tlv("01", "12")  # dynamic QR, used once per order
               + _tlv("26", merchant)
               + _tlv("52", "0000")
               + _tlv("53", "702")  # SGD
               + _tlv("54", f"{Decimal(amount):.2f}")
               + _tlv("58", "SG")
               + _tlv("59", settings.PAYNOW_MERCHANT_NAME[:25])
               + _tlv("60", "Singapore")
               + _tlv("62", _tlv("01", str(reference)[:25]))
               + "6304")
    return payload + _crc16(payload)

def qr_gen(rev, reference):
    # returns the PayNow QR as a base64 PNG the frontend can put in an <img>
    img = qrcode.make(paynow_payload(rev, reference))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def verify_drink_ids(incoming_drink_ids):
    valid_ids_list = [int(i) for i in incoming_drink_ids if str(i).isdigit()]
    unique_count = len(set(valid_ids_list))
    existing_drink_count = Drink.objects.filter(id__in=valid_ids_list, is_active=True).count()
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