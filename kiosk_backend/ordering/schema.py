# Request and response shapes for the API contract (OpenAPI schema). They describe what the
# views already return; the views don't use them to build responses.
from drf_spectacular.utils import OpenApiParameter, inline_serializer
from rest_framework import serializers

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

PaynowQr = inline_serializer('PaynowQr', {
    'status': serializers.CharField(),
    'qr_code': serializers.CharField(help_text="PNG image as a data: URL, ready for an <img> src."),
    'reference': serializers.CharField(help_text="Payment reference shown to the customer, e.g. ORDER12."),
    'amount': serializers.DecimalField(max_digits=6, decimal_places=2, coerce_to_string=True),
    'expires_at': serializers.DateTimeField(help_text="After this the order is cancelled if still unpaid."),
})
