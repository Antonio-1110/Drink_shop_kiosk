# Request and response shapes for the API contract (OpenAPI schema). They describe what the
# views already return; the views don't use them to build responses.
from drf_spectacular.utils import OpenApiParameter, inline_serializer
from rest_framework import serializers
from .serializer import OrderSerializer

SHOP_ID = OpenApiParameter(
    'shop_id', int, required=True, description="The shop (kiosk) the customer is ordering from.")
CART = OpenApiParameter(
    'cart', {'type': 'array', 'items': {'type': 'integer'}}, explode=True,
    description="Drink IDs already in the cart, one per cup (repeat `cart` for each).")

Error = inline_serializer('Error', {'error': serializers.CharField()})

Unavailable = inline_serializer('OrderUnavailable', {
    'error': serializers.CharField(),
    'drinks': serializers.ListField(child=serializers.IntegerField(), help_text="Drinks in the cart that can't be made."),
    'ingredients': serializers.ListField(child=serializers.IntegerField(), help_text="Ingredients that ran short."),
    'options': serializers.ListField(child=serializers.CharField(), help_text="Designer ingredient codes that ran short."),
})

OrderOk = inline_serializer('OrderAvailable', {'status': serializers.CharField()})


class OrderCreated(OrderSerializer):
    order_token = serializers.CharField(read_only=True, help_text="Proof you placed this order; needed to cancel it.")
    pickup_pin = serializers.CharField(read_only=True, help_text="6 digits (may start with 0) to type at the machine.")
    pickup_qr = serializers.CharField(read_only=True, help_text="PNG data URL of the pickup QR code to scan at the machine.")

    class Meta(OrderSerializer.Meta):
        fields = OrderSerializer.Meta.fields + ['order_token', 'pickup_pin', 'pickup_qr']


PickupRequest = inline_serializer('PickupRequest', {
    'shop': serializers.IntegerField(help_text="The machine's shop ID."),
    'code': serializers.CharField(help_text="The pickup PIN, or the token read from the pickup QR code."),
})


_per_size = lambda name, field: inline_serializer(name, {'0': field(), '1': field()})

DesignerOptions = inline_serializer('DesignerOptions', {
    'sizes': inline_serializer('DesignerSize', {
        'value': serializers.IntegerField(), 'label': serializers.CharField(),
        'liquid_ml': serializers.FloatField(), 'topping_g': serializers.FloatField()}, many=True),
    'pricing': inline_serializer('DesignerPricing', {
        'cup': _per_size('DesignerCupPrice', serializers.CharField),
        'liquid': serializers.CharField(help_text="Default price per liquid picked."),
        'topping': serializers.CharField(help_text="Default price per topping picked."),
        'overrides': serializers.DictField(child=serializers.CharField(), help_text="Price by ingredient code, where it differs."),
    }),
    'sweetener': inline_serializer('DesignerSweetener', {
        'code': serializers.CharField(), 'name': serializers.CharField(), 'color': serializers.CharField(),
        'sugar': serializers.FloatField(help_text="g per 100 mL"), 'sat_fat': serializers.FloatField(),
        'ml': _per_size('DesignerSweetenerMl', serializers.FloatField)}, allow_null=True,
        help_text="Added at 100% sugar and scaled down with the sugar level; null if none is set."),
    'ingredients': inline_serializer('DesignerIngredient', {
        'code': serializers.CharField(), 'name': serializers.CharField(),
        'kind': serializers.ChoiceField(choices=['liquid', 'topping']), 'category': serializers.CharField(),
        'share': serializers.FloatField(help_text="Liquids split the cup by share."),
        'color': serializers.CharField(), 'available': serializers.BooleanField(),
        'sugar': serializers.FloatField(), 'sat_fat': serializers.FloatField(),
        'sweetener': serializers.BooleanField(help_text="Contains a non-sugar sweetener."),
        'exclude_from_grade': serializers.BooleanField()}, many=True),
})

PickupFailed = inline_serializer('PickupFailed', {
    'error': serializers.CharField(),
    'reason': serializers.ChoiceField(choices=['not_found', 'not_paid', 'already_collected']),
})
