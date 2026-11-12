"""The whole-day simulation, and the bugs it found: the menu hiding drinks that could still be made,
a machine out of cups still selling and failing every paid drink, and a late payment being taken
for a milk drink under the dairy lock."""
import io
import logging
from datetime import datetime
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from checkout import services
from checkout.models import PaymentAttempt
from ordering.models import Order
from ordering.tests import OrderingTestBase
from .models import Kiosk
from .simulation import SGT, Scenario, Simulation
from .test_machine import MachineTestBase

S = Order.Status


def short_day(**kwargs):
    defaults = dict(start=datetime(2026, 11, 13, tzinfo=SGT), opens='08:00', closes='11:00', orders_per_hour=20,
                    faults=[('warm-fridge', '08:30', 10), ('out-of-cups', '09:15', 10), ('offline', '09:50', 6)],
                    staff_clears_lock_after=20)
    return Scenario(**{**defaults, **kwargs})


@override_settings(MACHINE_HEARTBEAT_TIMEOUT_SECONDS=180)
class SimulatedDayTests(TestCase):
    def run_day(self, **kwargs):
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        return Simulation(short_day(**kwargs)).run()

    def test_a_morning_with_faults_adds_up(self):
        sim = self.run_day(seed=3)
        self.assertEqual(sim.problems, [])
        day = sim.days[0]
        self.assertGreater(day['orders'], 30)
        self.assertGreater(day['statuses'][S.COLLECTED], 20)
        self.assertGreater(day['statuses'][S.CANCELLED], 0)
        self.assertGreater(day['channels']['phone'], 0)
        self.assertGreater(day['outcomes']['closed'], 0)  # turned away while the machine was offline or out of cups
        self.assertEqual(len(day['lock_spans']), 1)
        self.assertFalse(Order.objects.filter(status__in=[S.PENDING, S.PAID, S.PREPARING]).exists())

    def test_two_days_with_a_restock_in_between(self):
        sim = self.run_day(seed=8, days=2, closes='09:00', faults=[])
        self.assertEqual(sim.problems, [])
        self.assertEqual(len(sim.days), 2)

    def test_reports_orders_whose_stock_doesnt_add_up(self):
        with mock.patch('checkout.services.consume_stock', lambda order: None):
            sim = self.run_day(seed=3, closes='09:00', faults=[])
        self.assertTrue(any("still holds stock" in what for _, what in sim.problems), sim.problems[:5])


class CommandTests(TestCase):
    def test_reports_the_day_and_saves_nothing(self):
        out = io.StringIO()
        call_command('simulate_day', date='2026-11-13', closes='08:40', no_faults=True, stdout=out)
        self.assertIn("Fri 13 Nov 2026", out.getvalue())
        self.assertIn("No problems", out.getvalue())
        self.assertFalse(Order.objects.exists())

    def test_fails_when_it_finds_problems(self):
        out = io.StringIO()
        with mock.patch('checkout.services.consume_stock', lambda order: None), \
                self.assertRaises(CommandError):
            call_command('simulate_day', date='2026-11-13', closes='08:40', fault=[('offline', '08:10', 5)],
                         keep=True, stdout=out)
        self.assertIn("still holds stock", out.getvalue())
        self.assertTrue(Order.objects.exists())


class MenuTests(OrderingTestBase):
    def menu(self):
        return {d['name'] for d in self.client.get(f"/ordering/drinks/?shop_id={self.shop.pk}").data}

    def test_a_drink_needing_less_of_a_low_ingredient_stays_on_the_menu(self):
        # 250 mL of tea left: green tea needs 300 so it's off, but milk tea needs only 200
        self.tea_stock.current_stock = Decimal("250")
        self.tea_stock.save()
        self.assertEqual(self.menu(), {"Milk Tea"})

    def test_a_drink_whose_ingredient_the_shop_doesnt_stock_is_off(self):
        self.milk_stock.delete()
        self.assertEqual(self.menu(), {"Green Tea"})


class OutOfCupsTests(MachineTestBase):
    def test_shop_stops_selling_and_paid_orders_wait(self):
        self.check_in()
        order = self.paid_order(self.milk_tea)
        self.check_in(modules={'cups': 'empty', 'ice': 'ok'})
        self.assertEqual(self.menu(), set())
        res = self.order((self.green_tea, 0))
        self.assertEqual((res.status_code, res.data['reason']), (503, 'machine_not_ready'))
        self.assertEqual(self.next_order().status_code, 204)
        self.assertEqual(self.status(order), S.PAID)  # waits for the refill instead of failing
        self.check_in(modules={'cups': 'ok'})
        self.assertEqual(self.next_order().data['id'], order.pk)

    def test_a_low_part_that_isnt_essential_doesnt_close_the_shop(self):
        self.check_in(modules={'ice': 'empty', 'cups': 'low'})
        self.assertIn("Milk Tea", self.menu())


class LatePaymentUnderDairyLockTests(MachineTestBase):
    def test_is_refunded_not_taken(self):
        self.check_in()
        order, _ = self.place(self.milk_tea)
        services.cancel_order(order)
        Kiosk.objects.filter(pk=self.kiosk.pk).update(sfa_locked=True, sfa_lock_reason="Milk at 7 C")
        attempt = services.confirm_payment(order, 'fake', order.revenue, 'txn-late')
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUNDED)
        self.assertEqual(self.status(order), S.CANCELLED)
