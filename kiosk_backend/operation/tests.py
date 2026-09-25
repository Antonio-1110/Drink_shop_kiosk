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


class StockAndTemperatureLogTests(TestCase):
    def setUp(self):
        from .models import Kiosk
        self.shop = Shop.objects.create(name='Kiosk 1', address='Somewhere')
        self.kiosk = Kiosk.objects.create(shop=self.shop, machine_id='K-001')
        milk = Ingredient.objects.create(name='Milk', unit_of_measure='mL')
        self.inv = Inventory.objects.create(shop=self.shop, ingredient=milk, current_stock=D('1000'),
                                            max_safe_temp_c=D('4'))

    def test_adjust_stock_updates_and_logs(self):
        from .models import StockMovement
        self.inv.adjust_stock(D('-150'), StockMovement.Reason.ORDER)
        self.inv.adjust_stock(D('500'), StockMovement.Reason.RESTOCK, note='delivery')
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.current_stock, D('1350'))
        self.assertEqual(list(self.inv.movements.order_by('id').values_list('change', 'stock_after')),
                         [(D('-150'), D('850')), (D('500'), D('1350'))])

    def test_safe_reading_keeps_kiosk_unlocked(self):
        reading = self.inv.record_temperature(D('3.5'))
        self.assertTrue(reading.within_bounds)
        self.kiosk.refresh_from_db()
        self.assertFalse(self.kiosk.sfa_locked)

    def test_unsafe_reading_locks_kiosk(self):
        reading = self.inv.record_temperature(D('4.2'))
        self.assertFalse(reading.within_bounds)
        self.inv.refresh_from_db()
        self.assertEqual(self.inv.last_temp_c, D('4.2'))
        self.kiosk.refresh_from_db()
        self.assertTrue(self.kiosk.sfa_locked)
        self.assertIn('Milk', self.kiosk.sfa_lock_reason)
        # a safe reading afterwards does not unlock it; a person has to
        self.inv.record_temperature(D('3'))
        self.kiosk.refresh_from_db()
        self.assertTrue(self.kiosk.sfa_locked)


class DesignerTests(TestCase):
    def setUp(self):
        from .models import DesignerConfig
        L, T, O = Ingredient.Kind.LIQUID, Ingredient.Kind.TOPPING, Ingredient.Kind.OTHER
        self.tea = Ingredient.objects.create(name='Black tea', code='BT', unit_of_measure='mL', kind=L, share=3)
        self.milk = Ingredient.objects.create(name='Fresh milk', code='FM', unit_of_measure='mL', kind=L, share=2,
                                              sugar_per_100=D('4.8'), saturated_fat_per_100=D('2.3'))
        self.pearls = Ingredient.objects.create(name='Tapioca pearls', code='TP', unit_of_measure='g', kind=T,
                                                exclude_from_grade=True, designer_price=D('0.80'))
        self.jelly = Ingredient.objects.create(name='Grass jelly', code='GJ', unit_of_measure='g', kind=T)
        syrup = Ingredient.objects.create(name='Brown sugar syrup', code='BS', unit_of_measure='mL', kind=O,
                                          sugar_per_100=D('65'))
        self.config = DesignerConfig.load()
        self.config.sweetener = syrup
        self.config.save()

    def test_config_is_a_single_row(self):
        from .models import DesignerConfig
        DesignerConfig().save()
        self.assertEqual(DesignerConfig.objects.count(), 1)

    def test_amounts_share_the_cup_and_price_adds_up(self):
        lines, total = self.config.build([self.tea, self.milk, self.pearls, self.jelly], size=1, sugar_level=2)
        amounts = {i.code: a for i, a, _ in lines}
        self.assertEqual(amounts, {'BT': D('300.00'), 'FM': D('200.00'), 'TP': D('40.00'),
                                   'GJ': D('40.00'), 'BS': D('20.00')})
        # 3.40 cup + 0.50 + 0.50 liquids + 0.80 pearls override + 0.60 jelly default
        self.assertEqual(total, D('5.80'))

    def test_needs_a_liquid(self):
        with self.assertRaises(ValueError):
            self.config.build([self.pearls], size=0, sugar_level=4)

    def test_custom_order_item_is_graded_from_its_lines(self):
        from ordering.models import Order, OrderItem, OrderItemIngredient
        shop = Shop.objects.create(name='Kiosk 1', address='Somewhere')
        order = Order.objects.create(shop=shop, revenue=D('0'))
        item = OrderItem.objects.create(order=order, drink=None, size=1, sugar=2)
        lines, _ = self.config.build([self.tea, self.milk, self.pearls], size=1, sugar_level=2)
        for ingredient, amount, price in lines:
            OrderItemIngredient.objects.create(order_item=item, ingredient=ingredient, amount=amount, unit_price=price)
        result = item.apply_nutri_grade()
        # (9.6 g milk sugar + 13 g syrup) / 520 mL = 4.35 g; 4.6 g fat / 520 mL = 0.88 g
        self.assertEqual(result.sugar_g_per_100ml, D('4.35'))
        self.assertEqual(item.nutri_grade, 'B')
