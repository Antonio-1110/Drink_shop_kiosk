from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from .health_metrics import Component, calculate_nutri_grade, grade_drink, grade_from_concentration
from .models import Drink, DrinkIngredient, Ingredient, Inventory, Shop

D = Decimal


class NutriGradeThresholdTests(SimpleTestCase):
    def test_sugar_bands_are_inclusive_at_the_upper_bound(self):
        self.assertEqual(grade_from_concentration('1', '0'), 'A')
        self.assertEqual(grade_from_concentration('1.01', '0'), 'B')
        self.assertEqual(grade_from_concentration('5', '0'), 'B')
        self.assertEqual(grade_from_concentration('5.01', '0'), 'C')
        self.assertEqual(grade_from_concentration('10', '0'), 'C')
        self.assertEqual(grade_from_concentration('10.01', '0'), 'D')

    def test_saturated_fat_bands(self):
        self.assertEqual(grade_from_concentration('0', '0.7'), 'A')
        self.assertEqual(grade_from_concentration('0', '1.2'), 'B')
        self.assertEqual(grade_from_concentration('0', '2.8'), 'C')
        self.assertEqual(grade_from_concentration('0', '2.81'), 'D')

    def test_overall_grade_is_the_poorer_of_the_two(self):
        self.assertEqual(grade_from_concentration('3', '2'), 'C')
        self.assertEqual(grade_from_concentration('11', '0.1'), 'D')

    def test_sweetener_rules_out_grade_a(self):
        self.assertEqual(grade_from_concentration('0', '0', contains_sweetener=True), 'B')
        self.assertEqual(grade_from_concentration('7', '0', contains_sweetener=True), 'C')

    def test_concentration_is_per_100ml_of_the_mix(self):
        result = calculate_nutri_grade([
            Component(volume_ml=D('300'), saturated_fat_g=D('0')),
            Component(volume_ml=D('100'), sugar_g=D('24'), saturated_fat_g=D('2')),
        ])
        self.assertEqual(result.sugar_g_per_100ml, D('6.00'))
        self.assertEqual(result.saturated_fat_g_per_100ml, D('0.50'))
        self.assertEqual(result.grade, 'C')

    def test_empty_drink_raises(self):
        with self.assertRaises(ValueError):
            calculate_nutri_grade([])


class GradeDrinkTests(TestCase):
    def setUp(self):
        self.drink = Drink.objects.create(name='Milk Tea', l_price=D('5'), s_price=D('4'))
        tea = Ingredient.objects.create(name='Black tea', unit_of_measure='mL')
        milk = Ingredient.objects.create(name='Fresh milk', unit_of_measure='mL',
                                         saturated_fat_per_100=D('2.3'))
        syrup = Ingredient.objects.create(name='Sugar syrup', unit_of_measure='mL',
                                          sugar_per_100=D('80'))
        ice = Ingredient.objects.create(name='Ice', unit_of_measure='g', density_factor=D('0.917'))
        pearls = Ingredient.objects.create(name='Pearls', unit_of_measure='g',
                                           sugar_per_100=D('30'), exclude_from_grade=True)
        S = DrinkIngredient.Scaling
        for ingredient, qty, scaling in [(tea, 300, S.FIXED), (milk, 100, S.FIXED),
                                         (syrup, 40, S.SUGAR), (ice, 100, S.ICE),
                                         (pearls, 50, S.FIXED)]:
            DrinkIngredient.objects.create(drink=self.drink, ingredient=ingredient,
                                           required_quantity=D(qty), scaling=scaling)

    def test_full_sugar(self):
        # 32 g sugar and 2.3 g sat fat in 440 mL of liquid
        result = grade_drink(self.drink, sugar_level=4)
        self.assertEqual(result.total_volume_ml, D('440'))
        self.assertEqual(result.sugar_g_per_100ml, D('7.27'))
        self.assertEqual(result.grade, 'C')

    def test_zero_sugar_is_graded_on_milk_fat(self):
        result = grade_drink(self.drink, sugar_level=0)
        self.assertEqual(result.sugar_grade, 'A')
        self.assertEqual(result.saturated_fat_grade, 'A')  # 2.3 g / 400 mL = 0.58
        self.assertEqual(result.grade, 'A')

    def test_counting_ice_dilutes(self):
        result = grade_drink(self.drink, sugar_level=2, ice_level=4, count_ice_volume=True)
        self.assertGreater(result.total_volume_ml, D('520'))
        self.assertEqual(result.grade, 'B')


class InventoryTests(TestCase):
    def test_temperature_bounds_and_reorder(self):
        shop = Shop.objects.create(name='Kiosk 1', address='Somewhere')
        milk = Ingredient.objects.create(name='Milk', unit_of_measure='mL', reorder_threshold=D('500'))
        inv = Inventory.objects.create(shop=shop, ingredient=milk, current_stock=D('400'),
                                       max_safe_temp_c=D('4'))
        self.assertTrue(inv.needs_reorder())
        self.assertTrue(inv.temperature_ok())
        inv.last_temp_c = D('4.5')
        self.assertFalse(inv.temperature_ok())
