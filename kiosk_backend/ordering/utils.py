from operation.models import Drink, DrinkIngredient, Shop, Inventory
from django.db.models import F, Case, When, DecimalField
from decimal import Decimal


def qr_gen(rev):
    return rev

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

def inventory_update(shop_id, cart : list = []):
    return False

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
    if not insufficient_inventory_qs.exists():
        return True, [], []
    failing_ingredient_ids = insufficient_inventory_qs.values_list('ingredient', flat=True)
    affected_drink_ids = DrinkIngredient.objects.filter(drink__id__in=cart,
    ingredient__id__in=failing_ingredient_ids ).values_list('drink', flat=True).distinct()
    return False, affected_drink_ids, failing_ingredient_ids