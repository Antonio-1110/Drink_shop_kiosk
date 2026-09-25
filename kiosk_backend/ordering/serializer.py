from rest_framework import serializers
from .models import Order, Drink, OrderItem
from django.db import transaction

class OrderItemSerializer(serializers.ModelSerializer):
    # This field is used for input validation, ensuring the provided ID exists in the Drink table.
    # We use a PrimaryKeyRelatedField because the client will send the drink's ID (e.g., 5).
    drink = serializers.PrimaryKeyRelatedField(queryset=Drink.objects.all())

    class Meta:
        model = OrderItem
        # Note: We exclude 'order' here because it will be set by the parent OrderSerializer's create method.
        fields = ['drink', 'size', 'sugar', 'ice']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, allow_empty=False)

    class Meta:
        model = Order
        fields = ['id', 'shop', 'items', 'revenue', 'time', 'item_quantity', 'user_id', 'status']
        read_only_fields = ['id', 'revenue', 'time', 'item_quantity', 'status'] # Ensure these cannot be manipulated on POST

    # --- Overriding the Create Method ---
    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = Order.objects.create(revenue=0, **validated_data)
        rev = 0
        for item_data in items_data:
            x = OrderItem.objects.create(order=order, **item_data)
            rev += x.drink.l_price if x.size == OrderItem.Size.LARGE else x.drink.s_price
        order.item_quantity = len(items_data)
        order.revenue = rev
        order.save()

        return order
