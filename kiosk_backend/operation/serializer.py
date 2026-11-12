from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field, inline_serializer
from .health_metrics import grade_drink
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

NutriGradeLabel = inline_serializer('NutriGradeLabel', {
    'grade': serializers.ChoiceField(choices=['A', 'B', 'C', 'D']),
    'sugar_percent': serializers.IntegerField(help_text="Sugar per 100 mL, whole number, shown on the mark."),
    'label_required': serializers.BooleanField(
        help_text="C and D: the menu must show the mark next to this drink. A and B may."),
})


class DrinkSerializer(serializers.ModelSerializer):
    category = label_field(Drink.Category, 'get_category_display')
    nutri_grade = serializers.SerializerMethodField(
        help_text="HPB Nutri-Grade of the drink as it comes by default (100% sugar, no toppings); "
                  "graded from the nutrition data set on each ingredient in the admin. null for a drink with no recipe yet.")

    class Meta:
        model = Drink
        fields = "__all__"

    @extend_schema_field(NutriGradeLabel)
    def get_nutri_grade(self, drink):
        try:
            result = grade_drink(drink)
        except ValueError:  # no recipe lines with a volume yet
            return None
        return {'grade': result.grade, 'sugar_percent': result.sugar_percent,
                'label_required': result.label_required}

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