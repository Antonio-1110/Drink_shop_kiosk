from rest_framework import serializers
from .models import Shop, Drink, Ingredient, Inventory, DrinkIngredient

class ShopSerializer(serializers.ModelSerializer):
    # Override the model field in the serializer
    shop_type = serializers.ChoiceField(
        choices=Shop.ShopType.choices,
        source='get_shop_type_display',
        read_only=True
    )
    class Meta:
        model = Shop
        fields = "__all__"

class DrinkSerializer(serializers.ModelSerializer):
    category = serializers.ChoiceField(
        choices=Drink.Category.choices,
        source='get_category_display',
        read_only=True
    )
    class Meta:
        model = Drink
        fields = "__all__"

class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = "__all__"

class InventorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Inventory
        fields = ["current_stock"]
        read_only_field = ['shop', 'ingredient']

class DrinkIngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = DrinkIngredient
        fields = "__all__"