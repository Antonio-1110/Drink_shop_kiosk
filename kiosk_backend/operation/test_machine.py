"""The machine API that lets the shop run without staff: check-ins, temperatures, the work queue,
the dairy lock and closing when the machine goes quiet, and the simulated machine."""
import io
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from checkout import services
from checkout.tests import CheckoutTestBase
from ordering.models import Order, OrderItem
from .kiosk_auth import new_key
from .machine import mark_silent_machines_offline
from .management.commands.simulate_machine import Machine
from .models import Kiosk

S = Order.Status


@override_settings(MACHINE_SIMULATOR=False, MACHINE_HEARTBEAT_TIMEOUT_SECONDS=180)
class MachineTestBase(CheckoutTestBase):
    def setUp(self):
        super().setUp()
        self.kiosk = Kiosk.objects.create(shop=self.shop, machine_id='M-1')
        self.key = new_key(self.kiosk)
        # milk must stay at 1 to 4 C
        self.milk_stock.min_safe_temp_c, self.milk_stock.max_safe_temp_c = Decimal('1'), Decimal('4')
        self.milk_stock.save()
        self.milk_stock.adjust_stock(1000, 'RESTOCK')

    def call(self, path, body=None, key=None):
        return self.client.post(path, body or {}, format='json', HTTP_AUTHORIZATION=f"Kiosk {key or self.key}")

    def check_in(self, **body):
        return self.call('/operation/machine/heartbeat/', body)

    def temps(self, *readings):
        return self.call('/operation/machine/temperatures/', {'readings': list(readings)})

    def next_order(self):
        return self.call('/operation/machine/next-order/')

    def paid_order(self, *drinks):
        order, _ = self.place(*drinks)
        services.confirm_payment(order, 'fake', order.revenue, provider_ref=f"tx-{order.pk}")
        order.refresh_from_db()
        return order

    def menu(self):
        return {d['name'] for d in self.client.get(f"/ordering/drinks/?shop_id={self.shop.pk}").data}


class CheckInTests(MachineTestBase):
    def test_needs_the_kiosk_key(self):
        res = self.client.post('/operation/machine/heartbeat/', {}, format='json')
        self.assertIn(res.status_code, (401, 403))
        self.assertIn(self.call('/operation/machine/heartbeat/', key='wrong').status_code, (401, 403))

    def test_records_status_and_modules_and_lists_chilled_ingredients(self):
        res = self.check_in(modules={'sealer': 'ok', 'ice': 'low'})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertTrue(res.data['shop_open'])
        self.assertEqual([c['name'] for c in res.data['chilled']], ['Milk'])
        self.kiosk.refresh_from_db()
        self.assertEqual(self.kiosk.operational_status, Kiosk.Status.ONLINE)
        self.assertEqual(self.kiosk.module_states, {'sealer': 'ok', 'ice': 'low'})
        self.assertIsNotNone(self.kiosk.last_heartbeat)

    def test_refuses_bad_input(self):
        self.assertEqual(self.check_in(status='BROKEN').status_code, 400)
        self.assertEqual(self.check_in(modules=['x']).status_code, 400)


class ShopClosesWhenMachineGoesQuietTests(MachineTestBase):
    def test_closed_until_the_machine_checks_in(self):
        self.assertEqual(self.menu(), set())
        res = self.order((self.green_tea, OrderItem.Size.SMALL))
        self.assertEqual((res.status_code, res.data['reason']), (503, 'machine_offline'))
        check = self.client.get(f"/ordering/check-order/?shop_id={self.shop.pk}&cart={self.green_tea.pk}")
        self.assertEqual(check.status_code, 503)
        self.check_in()
        self.assertEqual(self.menu(), {'Milk Tea', 'Green Tea'})
        self.assertEqual(self.order((self.green_tea, OrderItem.Size.SMALL)).status_code, 201)

    def test_closes_when_check_ins_stop(self):
        self.check_in()
        Kiosk.objects.filter(pk=self.kiosk.pk).update(last_heartbeat=timezone.now() - timedelta(minutes=4))
        self.assertEqual(self.menu(), set())
        self.assertEqual(mark_silent_machines_offline(), 1)
        self.kiosk.refresh_from_db()
        self.assertEqual(self.kiosk.operational_status, Kiosk.Status.OFFLINE)
        self.assertEqual(mark_silent_machines_offline(), 0)

    def test_maintenance_closes_the_shop(self):
        self.check_in(status='MAINTENANCE')
        res = self.order((self.green_tea, OrderItem.Size.SMALL))
        self.assertEqual((res.status_code, res.data['reason']), (503, 'maintenance'))

    def test_shop_without_a_machine_key_stays_open(self):
        Kiosk.objects.filter(pk=self.kiosk.pk).update(api_key_hash='')
        self.assertEqual(self.menu(), {'Milk Tea', 'Green Tea'})

    def test_designer_shows_nothing_available_while_closed(self):
        self.milk.code, self.milk.offered_in_designer = 'MK', True
        self.milk.save()
        res = self.client.get(f"/ordering/designer/options/?shop_id={self.shop.pk}")
        self.assertFalse(res.data['ingredients'][0]['available'])
        self.check_in()
        res = self.client.get(f"/ordering/designer/options/?shop_id={self.shop.pk}")
        self.assertTrue(res.data['ingredients'][0]['available'])


class DairyLockTests(MachineTestBase):
    def setUp(self):
        super().setUp()
        self.check_in()

    def test_safe_reading_is_stored(self):
        res = self.temps({'ingredient': self.milk.pk, 'temp_c': 3.2})
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['recorded'], 1)
        self.assertFalse(res.data['sfa_locked'])
        self.assertEqual(self.milk_stock.temperature_readings.get().temp_c, Decimal('3.2'))

    def test_warm_milk_takes_milk_drinks_off_sale_only(self):
        res = self.temps({'ingredient': self.milk.pk, 'temp_c': 6.5})
        self.assertTrue(res.data['sfa_locked'])
        self.assertEqual(self.menu(), {'Green Tea'})
        res = self.order((self.milk_tea, OrderItem.Size.SMALL))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data['ingredients'], [self.milk.pk])
        check = self.client.get(f"/ordering/check-order/?shop_id={self.shop.pk}&cart={self.milk_tea.pk}")
        self.assertEqual((check.status_code, check.data['drinks']), (409, [self.milk_tea.pk]))
        self.assertEqual(self.order((self.green_tea, OrderItem.Size.SMALL)).status_code, 201)
        # cooling down again doesn't lift the lock: staff check and clear it
        self.temps({'ingredient': self.milk.pk, 'temp_c': 3})
        self.assertEqual(self.menu(), {'Green Tea'})
        Kiosk.objects.filter(pk=self.kiosk.pk).update(sfa_locked=False)
        self.assertEqual(self.menu(), {'Milk Tea', 'Green Tea'})

    def test_refuses_bad_readings_and_stores_none(self):
        for bad in ({'ingredient': 999, 'temp_c': 3}, {'ingredient': self.milk.pk}, {'ingredient': self.milk.pk, 'temp_c': 'x'},
                    {'ingredient': self.milk.pk, 'temp_c': 3, 'recorded_at': 'yesterday'}):
            with self.subTest(bad=bad):
                self.assertEqual(self.temps({'ingredient': self.milk.pk, 'temp_c': 3}, bad).status_code, 400)
        self.assertEqual(self.call('/operation/machine/temperatures/', {}).status_code, 400)
        self.assertFalse(self.milk_stock.temperature_readings.exists())


class WorkQueueTests(MachineTestBase):
    def setUp(self):
        super().setUp()
        self.check_in()

    def test_nothing_to_make(self):
        self.place(self.green_tea)  # placed but not paid
        self.assertEqual(self.next_order().status_code, 204)

    def test_oldest_paid_order_first_with_its_recipe(self):
        first = self.paid_order(self.milk_tea)
        second = self.paid_order(self.green_tea)
        res = self.next_order()
        self.assertEqual(res.status_code, 200)
        self.assertEqual((res.data['id'], res.data['status']), (first.pk, 'PREPARING'))
        # the test orders are small, 50% sugar and ice: the recipe's amounts as they are
        self.assertEqual([(line['name'], line['amount']) for line in res.data['items'][0]['lines']],
                         [('Milk', Decimal('100.00')), ('Tea', Decimal('200.00'))])
        self.assertEqual(self.next_order().data['id'], second.pk)
        self.assertEqual(self.next_order().status_code, 204)
        first.refresh_from_db()
        self.assertEqual(first.events.last().actor, 'machine:M-1')

    def test_only_its_own_shop(self):
        from operation.models import Shop
        other = Shop.objects.create(name="Other", address="2 Road")
        other_key = new_key(Kiosk.objects.create(shop=other, machine_id='M-2'))
        self.paid_order(self.green_tea)
        self.assertEqual(self.call('/operation/machine/next-order/', key=other_key).status_code, 204)

    def test_paid_order_needing_locked_milk_fails_for_a_refund(self):
        milk_order = self.paid_order(self.milk_tea)
        tea_order = self.paid_order(self.green_tea)
        self.temps({'ingredient': self.milk.pk, 'temp_c': 8})
        res = self.next_order()
        self.assertEqual(res.data['id'], tea_order.pk)
        milk_order.refresh_from_db()
        self.assertEqual(milk_order.status, S.FAILED)
        self.assertIn('dairy lock on Milk', milk_order.events.last().reason)

    def test_full_journey_to_collection(self):
        order = self.paid_order(self.green_tea)
        job = self.next_order().data
        self.call(f"/ordering/orders/{job['id']}/progress/", {'status': 'READY'})
        res = self.client.post('/ordering/pickup/', {'shop': self.shop.pk, 'code': order.pickup_pin}, format='json')
        self.assertEqual(res.data['status'], 'COLLECTED')


class SimulatedMachineTests(MachineTestBase):
    def machine(self, **kwargs):
        def send(method, path, body=None):
            res = self.call(path, body)
            return res.status_code, getattr(res, 'data', None)
        self.lines = []
        return Machine(send, rng=random.Random(1), sleep=lambda s: None, log=self.lines.append, **kwargs)

    def test_makes_every_waiting_order(self):
        self.check_in()
        a, b = self.paid_order(self.green_tea), self.paid_order(self.milk_tea)
        self.machine().tick()
        made = self.machine().tick()  # nothing left
        self.assertEqual(made, [])
        for order in (a, b):
            order.refresh_from_db()
            self.assertEqual(order.status, S.READY)
        self.assertEqual(self.milk_stock.temperature_readings.count(), 2)

    def test_out_of_cups_fails_after_one_retry(self):
        self.check_in()
        order = self.paid_order(self.green_tea)
        made = self.machine(fault='out-of-cups').tick()
        self.assertEqual(made, [(order.pk, 'FAILED')])
        self.assertTrue(any('retrying once' in line for line in self.lines))
        order.refresh_from_db()
        self.assertEqual(order.events.last().reason, 'Out of cups')

    def test_random_failures_are_retried(self):
        self.check_in()
        orders = [self.paid_order(self.green_tea) for _ in range(3)]
        made = dict(self.machine(fail_rate=0.5).tick())
        self.assertEqual(set(made), {o.pk for o in orders})
        self.assertTrue(set(made.values()) <= {'READY', 'FAILED'})

    def test_warm_fridge_turns_the_dairy_lock_on(self):
        self.machine(fault='warm-fridge').tick()
        self.kiosk.refresh_from_db()
        self.assertTrue(self.kiosk.sfa_locked)

    def test_offline_never_checks_in(self):
        self.assertEqual(self.machine(fault='offline').tick(), [])
        self.kiosk.refresh_from_db()
        self.assertIsNone(self.kiosk.last_heartbeat)

    def test_command_needs_a_key(self):
        err = io.StringIO()
        call_command('simulate_machine', key='', stderr=err)
        self.assertIn('--key', err.getvalue())

    def test_check_machines_command(self):
        out = io.StringIO()
        call_command('check_machines', stdout=out)
        self.assertIn('0 machine(s)', out.getvalue())
