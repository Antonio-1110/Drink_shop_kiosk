"""GET /ordering/designer/options/: what the drink designer offers at a shop, and at what price.

Amounts and prices themselves are worked out by operation.models.DesignerConfig.build, which the
order endpoint also uses, so the apps' preview and the charged price come from the same rules.
"""
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from operation.models import DesignerConfig, Ingredient, Inventory, Shop
from . import schema
from .models import OrderItem

SIZES = [(OrderItem.Size.SMALL, 'Small'), (OrderItem.Size.LARGE, 'Large')]


def _ml(config, field, size):
    return float(getattr(config, f"{field}_{'large' if size == OrderItem.Size.LARGE else 'small'}"))


@extend_schema(summary="Drink designer options",
               description="Sizes, prices and the ingredients a customer can build a drink from at this shop. "
                           "`available` means the shop has enough of the ingredient for the most a large cup "
                           "could use. Order a designed drink by sending its ingredient codes as `custom` in "
                           "POST /ordering/log-order/.",
               parameters=[OpenApiParameter('shop_id', int, required=True)],
               responses={200: schema.DesignerOptions, 400: schema.Error, 404: schema.Error})
@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def designer_options(request):
    shop_id = request.GET.get('shop_id', '')
    if not shop_id.isdigit():
        return Response({"error": "Invalid or missing Shop ID."}, status=status.HTTP_400_BAD_REQUEST)
    if not Shop.objects.filter(pk=shop_id).exists():
        return Response({"error": "Shop not found"}, status=status.HTTP_404_NOT_FOUND)
    config = DesignerConfig.load()
    ingredients = list(Ingredient.objects.filter(
        offered_in_designer=True, kind__in=[Ingredient.Kind.LIQUID, Ingredient.Kind.TOPPING],
    ).exclude(code=None).order_by('designer_category', 'name'))
    stock = dict(Inventory.objects.filter(shop_id=shop_id).values_list('ingredient_id', 'current_stock'))

    def most_a_large_cup_uses(ingredient):
        # a liquid on its own fills the whole cup; a topping on its own gets all the topping weight
        return (config.liquid_ml_large if ingredient.kind == Ingredient.Kind.LIQUID else config.topping_g_large)

    sweetener = config.sweetener
    return Response({
        'sizes': [{'value': value, 'label': label, 'liquid_ml': _ml(config, 'liquid_ml', value),
                   'topping_g': _ml(config, 'topping_g', value)} for value, label in SIZES],
        'pricing': {
            'cup': {'0': str(config.cup_price_small), '1': str(config.cup_price_large)},
            'liquid': str(config.default_liquid_price),
            'topping': str(config.default_topping_price),
            'overrides': {i.code: str(i.designer_price) for i in ingredients if i.designer_price is not None},
        },
        'sweetener': None if sweetener is None else {
            'code': sweetener.code, 'name': sweetener.name, 'color': sweetener.display_color,
            'sugar': float(sweetener.sugar_per_100), 'sat_fat': float(sweetener.saturated_fat_per_100),
            'ml': {'0': _ml(config, 'sweetener_ml', 0), '1': _ml(config, 'sweetener_ml', 1)},
        },
        'ingredients': [{
            'code': i.code, 'name': i.name, 'kind': i.kind.lower(), 'category': i.designer_category,
            'share': float(i.share), 'color': i.display_color,
            'available': stock.get(i.pk, 0) >= most_a_large_cup_uses(i),
            'sugar': float(i.sugar_per_100), 'sat_fat': float(i.saturated_fat_per_100),
            'sweetener': i.contains_sweetener, 'exclude_from_grade': i.exclude_from_grade,
        } for i in ingredients],
    })
