from rest_framework import serializers
from operation.models import DesignerConfig, Ingredient
from .models import Order, Drink, OrderItem, OrderItemIngredient
from django.db import transaction

class OrderItemSerializer(serializers.ModelSerializer):
    # This field is used for input validation, ensuring the provided ID exists in the Drink table.
    # We use a PrimaryKeyRelatedField because the client will send the drink's ID (e.g., 5).
    drink = serializers.PrimaryKeyRelatedField(queryset=Drink.objects.filter(is_active=True),
                                               required=False, allow_null=True)
    # a drink the customer designed: ingredient codes from GET /ordering/designer/options/
    custom = serializers.ListField(child=serializers.CharField(max_length=4), required=False, allow_empty=False,
                                   help_text="Ingredient codes for a designer drink, instead of `drink`.")

    class Meta:
        model = OrderItem
        # Note: We exclude 'order' here because it will be set by the parent OrderSerializer's create method.
        fields = ['drink', 'custom', 'size', 'sugar', 'ice']

    def validate(self, attrs):
        codes = attrs.pop('custom', None)
        if bool(attrs.get('drink')) == bool(codes):
            raise serializers.ValidationError("Give either a menu drink or a custom drink's ingredient codes.")
        if codes:
            codes = list(dict.fromkeys(codes))  # the same ingredient twice counts once
            found = {i.code: i for i in Ingredient.objects.filter(
                code__in=codes, offered_in_designer=True,
                kind__in=[Ingredient.Kind.LIQUID, Ingredient.Kind.TOPPING])}
            unknown = [c for c in codes if c not in found]
            if unknown:
                raise serializers.ValidationError({'custom': f"Unknown ingredient codes: {', '.join(unknown)}"})
            try:
                # amounts and price are worked out here, so the stock check and the order use the same ones
                attrs['designer_lines'], attrs['designer_price'] = DesignerConfig.load().build(
                    [found[c] for c in codes], attrs.get('size', OrderItem.Size.SMALL),
                    attrs.get('sugar', OrderItem.Level.NORMAL))
            except ValueError as e:
                raise serializers.ValidationError({'custom': str(e)})
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # the codes the customer picked; the sweetener comes from the sugar level, so it's left out
        data['custom'] = (None if instance.drink_id else
                          [line.ingredient.code for line in instance.custom_ingredients.select_related('ingredient')
                           .exclude(ingredient__kind=Ingredient.Kind.OTHER).order_by('pk')])
        return data

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
            lines = item_data.pop('designer_lines', None)
            price = item_data.pop('designer_price', None)
            x = OrderItem(order=order, **item_data)
            if lines is None:
                x.unit_price = x.drink.l_price if x.size == OrderItem.Size.LARGE else x.drink.s_price
            else:
                x.unit_price = price
                x.save()
                OrderItemIngredient.objects.bulk_create(
                    OrderItemIngredient(order_item=x, ingredient=ingredient, amount=amount, unit_price=line_price)
                    for ingredient, amount, line_price in lines)
            try:
                x.apply_nutri_grade()
            except ValueError: # drink has no recipe lines to grade yet
                pass
            x.save()
            rev += x.unit_price
        order.item_quantity = len(items_data)
        order.revenue = rev
        order.save()

        return order
