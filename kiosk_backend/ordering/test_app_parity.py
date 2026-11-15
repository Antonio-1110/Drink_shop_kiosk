"""The kiosk and the phone app preview a designed drink's recipe, price and Nutri-Grade themselves
(kiosk-app/src/designer.js, mobile-app/lib/designer.ts). The backend decides what is charged and
recorded. These tests write down what the backend does for a set of designs in
test-cases/designer.json, and the kiosk's tests (kiosk-app/src/parity.test.js) check that both
apps agree with it. test-cases/nutrigrade.json does the same for the grade thresholds.

After changing how the backend prices or grades drinks, update the file with
    UPDATE_TEST_CASES=1 python manage.py test ordering.test_app_parity
and then make the apps match it until `npm test` in kiosk-app passes.
"""
import json
import os
from decimal import Decimal
from itertools import combinations
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient

from operation.health_metrics import grade_from_concentration
from operation.models import DesignerConfig, Ingredient, Inventory, Shop
from .models import Order

CASES_DIR = Path(settings.BASE_DIR).parent / 'test-cases'
UPDATE = os.environ.get('UPDATE_TEST_CASES') == '1'
L, T, O = Ingredient.Kind.LIQUID, Ingredient.Kind.TOPPING, Ingredient.Kind.OTHER

# code, name, unit, kind, category, share, sugar, saturated fat, designer price, flags. Chosen to
# reach every rule: shares, a price override, a non-sugar sweetener, an ungraded liquid, toppings
# with sugar, and drinks near the grade limits.
INGREDIENTS = [
    ('BT', 'Black tea', 'mL', L, 'Tea', 3, 0, 0, None, {}),
    ('GT', 'Green tea', 'mL', L, 'Tea', 3, 0.4, 0, None, {}),
    ('FM', 'Fresh milk', 'mL', L, 'Milk', 2, 4.8, 2.3, '0.80', {}),
    ('OM', 'Oat milk', 'mL', L, 'Milk', 2, 4.0, 0.3, None, {}),
    ('ZS', 'Zero-sugar soda', 'mL', L, 'Fruit', 1, 0, 0, '1.10', {'contains_sweetener': True}),
    ('LM', 'Lemon', 'g', L, 'Fruit', 1, 2.5, 0, None, {}),
    ('CJ', 'Coconut jelly', 'g', T, 'Toppings', 1, 12, 0, None, {}),
    ('TP', 'Tapioca pearls', 'g', T, 'Toppings', 1, 30, 0, '0.90', {}),
    ('AV', 'Aloe vera', 'mL', L, 'Toppings', 1, 9, 0, None, {'exclude_from_grade': True}),
]
SWEETENER = ('BS', 'Brown sugar syrup', 'mL', O, '', 1, 65, 0, None, {})


class AppParityTests(TestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        cls.shop = Shop.objects.create(name='Parity Shop', address='1 Test Road')
        for code, name, unit, kind, category, share, sugar, fat, price, flags in INGREDIENTS + [SWEETENER]:
            ingredient = Ingredient.objects.create(
                name=name, unit_of_measure=unit, code=code, kind=kind, designer_category=category, share=share,
                sugar_per_100=sugar, saturated_fat_per_100=fat, offered_in_designer=kind != O,
                designer_price=Decimal(price) if price else None, **flags)
            Inventory.objects.create(shop=cls.shop, ingredient=ingredient, current_stock=Decimal('1000000'))
        config = DesignerConfig.load()
        config.sweetener = Ingredient.objects.get(code='BS')
        config.save()

    def designs(self):
        liquids = [c[0] for c in INGREDIENTS if c[3] == L]
        picks = [[code] for code in liquids]
        picks += [list(pair) for pair in combinations(liquids, 2)]
        picks += [['BT', 'FM', 'TP'], ['GT', 'OM', 'CJ', 'TP'], ['FM', 'AV'], ['LM', 'ZS', 'TP'],
                  ['BT', 'GT', 'FM', 'OM', 'LM']]
        designs = []
        for n, pick in enumerate(picks):
            # spread sizes and sugar levels over the picks, so every combination appears somewhere
            designs.append({'size': n % 2, 'sugar': n % 5, 'ice': 2, 'picks': pick})
        designs += [{'size': size, 'sugar': sugar, 'ice': 4, 'picks': ['GT', 'TP']}
                    for size in (0, 1) for sugar in range(5)]
        return designs

    def backend_result(self, design):
        res = APIClient().post('/ordering/log-order/', {'shop': self.shop.pk, 'items': [
            {'custom': design['picks'], 'size': design['size'], 'sugar': design['sugar'], 'ice': design['ice']}]},
            format='json')
        self.assertEqual(res.status_code, 201, (design, res.data))
        item = Order.objects.get(pk=res.data['id']).items.get()
        amounts = {line.ingredient.code: float(line.amount)
                   for line in item.custom_ingredients.select_related('ingredient') if line.amount > 0}
        return {'price': str(item.unit_price), 'grade': item.nutri_grade, 'amounts': amounts}

    def check_file(self, name, data):
        path = CASES_DIR / name
        text = json.dumps(data, indent=2, sort_keys=True) + '\n'
        if UPDATE:
            path.parent.mkdir(exist_ok=True)
            path.write_text(text)
        self.assertTrue(path.exists(), f"{path} is missing; run with UPDATE_TEST_CASES=1")
        self.assertEqual(json.loads(path.read_text()), json.loads(text),
                         f"{name} no longer matches the backend. If the change is intended, run "
                         "UPDATE_TEST_CASES=1 python manage.py test ordering.test_app_parity and update the apps.")

    def test_designed_drinks(self):
        options = APIClient().get('/ordering/designer/options/', {'shop_id': self.shop.pk}).json()
        cases = [{'design': d, **self.backend_result(d)} for d in self.designs()]
        grades = {c['grade'] for c in cases}
        self.assertEqual(grades, {'A', 'B', 'C', 'D'}, "the cases should reach every grade")
        self.check_file('designer.json', {
            '_about': "Backend results for designed drinks; written by kiosk_backend/ordering/test_app_parity.py, "
                      "checked against the apps by kiosk-app/src/parity.test.js. Don't edit by hand.",
            'options': options, 'cases': cases})

    def test_grade_limits(self):
        # each limit, just under and just over it, and the sweetener rule
        points = []
        for sugar in (0, 1, 1.01, 4.99, 5, 5.01, 10, 10.01, 30):
            for fat in (0, 0.7, 0.71, 1.2, 1.21, 2.8, 2.81):
                for sweetener in (False, True):
                    points.append({'sugar': sugar, 'sat_fat': fat, 'sweetener': sweetener,
                                   'grade': grade_from_concentration(Decimal(str(sugar)), Decimal(str(fat)), sweetener)})
        self.check_file('nutrigrade.json', {
            '_about': "Backend Nutri-Grade per 100 mL; written by kiosk_backend/ordering/test_app_parity.py, "
                      "checked against the apps by kiosk-app/src/parity.test.js. Don't edit by hand.",
            'cases': points})
