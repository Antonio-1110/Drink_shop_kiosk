"""Nutri-Grade as HPB's freshly prepared beverage rules need it: drinks graded without toppings, at
their default preparation, and the menu told which drinks must show the mark and their sugar %."""
import io
from decimal import Decimal

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from .health_metrics import Component, calculate_nutri_grade, grade_drink, grade_ingredient_lines
from .models import Drink, Ingredient, Shop

D = Decimal


class SugarPercentTests(SimpleTestCase):
    def grade(self, sugar_g):
        return calculate_nutri_grade([Component(volume_ml=D('100'), sugar_g=D(sugar_g))])

    def test_sugar_percent_is_rounded_to_a_whole_number(self):
        self.assertEqual(self.grade('4.49').sugar_percent, 4)
        self.assertEqual(self.grade('4.5').sugar_percent, 5)
        self.assertEqual(self.grade('0.4').sugar_percent, 0)

    def test_only_c_and_d_must_show_the_mark(self):
        self.assertEqual([self.grade(s).label_required for s in ('1', '5', '10', '11')],
                         [False, False, True, True])


class ToppingTests(TestCase):
    def setUp(self):
        self.milk = Ingredient.objects.create(name="Milk", unit_of_measure="mL", sugar_per_100=D('5'))
        self.pearls = Ingredient.objects.create(name="Pearls", unit_of_measure="g", kind=Ingredient.Kind.TOPPING,
                                                sugar_per_100=D('30'))

    def test_toppings_neither_add_sugar_nor_dilute_the_drink(self):
        with_pearls = grade_ingredient_lines([(self.milk, D('200')), (self.pearls, D('100'))])
        without = grade_ingredient_lines([(self.milk, D('200'))])
        self.assertEqual(with_pearls, without)
        self.assertEqual(with_pearls.sugar_g_per_100ml, D('5.00'))


class MenuLabelTests(TestCase):
    """The demo menu, graded as a customer would get each drink by default."""

    def setUp(self):
        call_command('seed_demo', stdout=io.StringIO())
        self.shop = Shop.objects.first()

    def test_brown_sugar_pearl_milk_is_graded_without_its_pearls(self):
        # 250 mL milk (4.8 g sugar, 2.3 g sat fat per 100) + 30 mL syrup (65 g sugar per 100):
        # 31.5 g sugar in 280 mL = 11.25 g/100 mL, so D. Counting the 60 g of pearls as liquid
        # would have watered it down to a C.
        result = grade_drink(Drink.objects.get(name="Brown Sugar Pearl Milk"))
        self.assertEqual(result.sugar_g_per_100ml, D('11.25'))
        self.assertEqual((result.grade, result.sugar_percent), ('D', 11))

    def test_menu_lists_each_drinks_grade_and_sugar(self):
        res = APIClient().get("/ordering/drinks/", {"shop_id": self.shop.id})
        self.assertEqual(res.status_code, 200)
        labels = {d['name']: d['nutri_grade'] for d in res.data}
        self.assertEqual(labels["Brown Sugar Pearl Milk"],
                         {'grade': 'D', 'sugar_percent': 11, 'label_required': True})
        self.assertEqual(labels["Iced Oolong Tea"], {'grade': 'A', 'sugar_percent': 0, 'label_required': False})
        self.assertTrue(all(label is not None for label in labels.values()))

    def test_drink_without_a_recipe_has_no_grade(self):
        Drink.objects.create(name="New", s_price=D('3'), l_price=D('4'))
        res = APIClient().get("/ordering/drinks/", {"shop_id": self.shop.id})
        self.assertIsNone(next(d for d in res.data if d['name'] == "New")['nutri_grade'])
