from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import Shop, Drink, Ingredient, Inventory, DrinkIngredient

def label_field(choices, source):
    # sends the choice's label ("Milk Tea") rather than its stored number, and says so in the API contract
    @extend_schema_field({'type': 'string', 'enum': list(choices.labels)})
    class LabelField(serializers.CharField):
        pass
    return LabelField(source=source, read_only=True)

class ShopSerializer(serializers.ModelSerializer):
    shop_type = label_field(Shop.ShopType, 'get_shop_type_display')
    class Meta:
        model = Shop
        fields = "__all__"

class DrinkSerializer(serializers.ModelSerializer):
    category = label_field(Drink.Category, 'get_category_display')
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