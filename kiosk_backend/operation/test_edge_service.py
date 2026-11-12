"""The real edge service (edge/edge_service) against this backend's machine API, end to end, with the
simulator driver. The edge's HTTP calls go through Django's test client instead of the network."""
import os
import sys

from ordering.models import Order
from .models import Kiosk
from .test_machine import MachineTestBase

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'edge'))
from edge_service.backend import BackendClient  # noqa: E402
from edge_service.hardware import load_driver  # noqa: E402
from edge_service.outbox import Outbox  # noqa: E402
from edge_service.service import EdgeService  # noqa: E402

S = Order.Status


class EdgeServiceEndToEndTests(MachineTestBase):
    def edge(self, faults=(), **options):
        def transport(method, url, headers, body, timeout):
            res = self.client.generic(method, url[len('http://backend'):], data=body or b'',
                                      content_type='application/json', HTTP_AUTHORIZATION=headers['Authorization'])
            return res.status_code, res.content
        hardware = load_driver('simulator', faults=faults, sleep=lambda s: None, **options)
        return EdgeService(BackendClient('http://backend', self.key, transport=transport), hardware, Outbox())

    def test_paid_orders_are_made_and_collected(self):
        edge = self.edge()
        edge.tick()  # first check-in opens the shop
        a, b = self.paid_order(self.green_tea), self.paid_order(self.milk_tea)
        made = edge.tick()
        self.assertEqual(made, [(a.pk, 'READY'), (b.pk, 'READY')])
        b.refresh_from_db()
        self.assertEqual(b.status, S.READY)
        self.assertEqual(b.events.last().actor, 'machine:M-1')
        self.assertTrue(any('Milk' in step for step in edge.hw.sim.actions))
        self.kiosk.refresh_from_db()
        self.assertEqual(self.kiosk.operational_status, Kiosk.Status.ONLINE)
        self.assertEqual(self.kiosk.module_states['sealer'], 'ok')
        self.assertEqual(self.milk_stock.temperature_readings.count(), 1)
        res = self.client.post('/ordering/pickup/', {'shop': self.shop.pk, 'code': b.pickup_pin}, format='json')
        self.assertEqual(res.data['status'], 'COLLECTED')

    def test_failed_drink_goes_to_failed_with_the_reason(self):
        edge = self.edge(fail_rate=1.0)
        edge.tick()
        order = self.paid_order(self.green_tea)
        self.assertEqual(edge.tick(), [(order.pk, 'FAILED')])
        order.refresh_from_db()
        self.assertEqual(order.status, S.FAILED)
        self.assertIn('random fault', order.events.last().reason)

    def test_out_of_cups_closes_the_shop_and_paid_orders_wait(self):
        edge = self.edge()
        edge.tick()
        order = self.paid_order(self.green_tea)
        edge.hw.sim.faults.add('out-of-cups')
        edge.next_heartbeat = 0
        self.assertEqual(edge.tick(), [])  # its check-in said cups are empty, so it isn't given the order
        self.assertEqual(self.status(order), S.PAID)
        self.assertEqual(self.order((self.green_tea, 0)).data['reason'], 'machine_not_ready')
        edge.hw.sim.faults.discard('out-of-cups')  # refilled
        edge.next_heartbeat = 0
        self.assertEqual(edge.tick(), [(order.pk, 'READY')])

    def test_warm_fridge_locks_dairy_and_milk_orders_are_not_made(self):
        edge = self.edge()
        edge.tick()
        order = self.paid_order(self.milk_tea)
        edge.hw.sim.faults.add('warm-fridge')
        edge.next_temps = 0
        edge.tick()
        self.kiosk.refresh_from_db()
        self.assertTrue(self.kiosk.sfa_locked)
        self.assertTrue(edge.lock.tripped)
        order.refresh_from_db()
        self.assertEqual(order.status, S.FAILED)
        self.assertIn('dairy lock', order.events.last().reason)

    def test_maintenance_closes_the_shop(self):
        edge = self.edge()
        edge.maintenance = True
        edge.tick()
        self.assertEqual(self.menu(), set())
