"""
Singapore HPB Nutri-Grade calculation for beverages.

Thresholds per 100 mL, as published by the Health Promotion Board:
https://www.healthhub.sg/programmes/nutrition-hub/nutri-grade-mark
(see also https://www.hpb.gov.sg/healthy-living/food-and-beverage/nutri-grade/)

    Grade   Sugar (g/100mL)              Saturated fat (g/100mL)
    A       <= 1 and no sweetener        <= 0.7
    B       > 1 to 5                     > 0.7 to 1.2
    C       > 5 to 10                    > 1.2 to 2.8
    D       > 10                         > 2.8

The overall grade is the poorer of the sugar grade and the saturated fat grade.
A drink containing a non-sugar sweetener cannot be grade A.

This module has no Django dependency so the kiosk edge service can reuse it.
`grade_drink` duck-types over the operation.Drink / DrinkIngredient models.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

GRADES = ('A', 'B', 'C', 'D')

# (upper bound inclusive, grade); anything above the last bound is D
SUGAR_THRESHOLDS = ((Decimal('1'), 'A'), (Decimal('5'), 'B'), (Decimal('10'), 'C'))
SAT_FAT_THRESHOLDS = ((Decimal('0.7'), 'A'), (Decimal('1.2'), 'B'), (Decimal('2.8'), 'C'))

# OrderItem.Level stores 0..4 for 0%..100%
LEVEL_STEPS = 4


@dataclass(frozen=True)
class Component:
    """One liquid in the cup, already scaled for the customer's settings."""
    volume_ml: Decimal
    sugar_g: Decimal = Decimal('0')
    saturated_fat_g: Decimal = Decimal('0')
    contains_sweetener: bool = False


@dataclass(frozen=True)
class NutriGradeResult:
    grade: str
    sugar_grade: str
    saturated_fat_grade: str
    sugar_g_per_100ml: Decimal
    saturated_fat_g_per_100ml: Decimal
    total_volume_ml: Decimal


def _band(value: Decimal, thresholds) -> str:
    for upper, grade in thresholds:
        if value <= upper:
            return grade
    return 'D'


def _worse(*grades: str) -> str:
    return max(grades, key=GRADES.index)


def _sub_grades(sugar_g_per_100ml, saturated_fat_g_per_100ml, contains_sweetener):
    sugar = _band(Decimal(sugar_g_per_100ml), SUGAR_THRESHOLDS)
    if contains_sweetener and sugar == 'A':
        sugar = 'B'
    return sugar, _band(Decimal(saturated_fat_g_per_100ml), SAT_FAT_THRESHOLDS)


def grade_from_concentration(sugar_g_per_100ml, saturated_fat_g_per_100ml,
                             contains_sweetener: bool = False) -> str:
    return _worse(*_sub_grades(sugar_g_per_100ml, saturated_fat_g_per_100ml, contains_sweetener))


def calculate_nutri_grade(components: Iterable[Component]) -> NutriGradeResult:
    components = list(components)
    total_volume = sum((c.volume_ml for c in components), Decimal('0'))
    if total_volume <= 0:
        raise ValueError("Cannot grade a drink with no liquid volume.")
    sugar = sum((c.sugar_g for c in components), Decimal('0')) * 100 / total_volume
    fat = sum((c.saturated_fat_g for c in components), Decimal('0')) * 100 / total_volume
    sweetener = any(c.contains_sweetener for c in components)
    sugar_grade, fat_grade = _sub_grades(sugar, fat, sweetener)
    return NutriGradeResult(
        grade=_worse(sugar_grade, fat_grade),
        sugar_grade=sugar_grade,
        saturated_fat_grade=fat_grade,
        sugar_g_per_100ml=sugar.quantize(Decimal('0.01')),
        saturated_fat_g_per_100ml=fat.quantize(Decimal('0.01')),
        total_volume_ml=total_volume,
    )


def grade_drink(drink, sugar_level: int = LEVEL_STEPS, ice_level: int = LEVEL_STEPS,
                count_ice_volume: bool = False) -> NutriGradeResult:
    """
    Grade an operation.Drink as it would be dispensed.

    sugar_level / ice_level use OrderItem.Level (0..4). Recipe lines whose
    `scaling` is SUGAR or ICE are multiplied by level / 4.

    Ice is left out of the volume by default, which grades on the liquid alone
    and so never under-reports concentration. Pass count_ice_volume=True to
    grade the drink as served with ice counted as diluent.
    Ingredients flagged exclude_from_grade (e.g. toppings, whose sugar is
    declared separately on the menu) are skipped.
    """
    components = []
    for line in drink.required.select_related('ingredient'):
        ingredient = line.ingredient
        if ingredient.exclude_from_grade:
            continue
        quantity = Decimal(line.required_quantity)
        if line.scaling == line.Scaling.SUGAR:
            quantity = quantity * sugar_level / LEVEL_STEPS
        elif line.scaling == line.Scaling.ICE:
            if not count_ice_volume:
                continue
            quantity = quantity * ice_level / LEVEL_STEPS
        if quantity <= 0:
            continue
        components.append(Component(
            volume_ml=ingredient.to_millilitres(quantity),
            sugar_g=quantity * ingredient.sugar_per_100 / 100,
            saturated_fat_g=quantity * ingredient.saturated_fat_per_100 / 100,
            contains_sweetener=ingredient.contains_sweetener,
        ))
    return calculate_nutri_grade(components)
