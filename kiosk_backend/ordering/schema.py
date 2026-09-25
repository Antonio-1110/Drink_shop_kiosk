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
