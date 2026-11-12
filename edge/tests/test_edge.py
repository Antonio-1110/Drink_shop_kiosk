import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from edge_service.backend import BackendClient, BackendRefused, BackendUnavailable
from edge_service.hardware import Hardware, HardwareFault, load_driver
from edge_service.maker import Maker, steps
from edge_service.outbox import Outbox
from edge_service.server import serve
from edge_service.service import EdgeService

from fakes import Clock, FakeBackend, job


def service(backend, faults=(), outbox=None, **kw):
    hw = load_driver('simulator', faults=faults, sleep=lambda s: None)
    clock = Clock()
    svc = EdgeService(backend, hw, Outbox() if outbox is None else outbox, clock=clock, wall=lambda: '2026-11-12T15:00:00+00:00', **kw)
    return svc, hw, clock


class StepsTest(unittest.TestCase):
    def test_order_of_stations(self):
        plan = steps(job(1)['items'][0])
        self.assertEqual([s[0] for s in plan], ['cup', 'ice', 'topping', 'liquid', 'liquid', 'seal'])
        self.assertEqual(plan[0][2], 'Large')
        self.assertEqual(plan[1][2], 150.0)
        # zero amounts (0% sugar) are skipped
        self.assertNotIn('Brown sugar syrup', [s[1].name for s in plan if s[1]])

    def test_ice_found_by_name_whatever_its_kind(self):
        item = job(1)['items'][0]
        item['lines'][1]['kind'] = 'LIQUID'
        self.assertEqual(steps(item)[1], ('ice', None, 150.0))


class MakerTest(unittest.TestCase):
    def test_retry_once_then_fail_and_waste_cups(self):
        hw = load_driver('simulator', faults=['seal-jam'], sleep=lambda s: None)
        result = Maker(hw).make(job(7, cups=2))
        self.assertFalse(result.ok)
        self.assertIn('seal failed', result.reason)
        self.assertEqual(hw.sim.actions.count('cups: drop Large cup'), 2)  # first try + one retry
        self.assertEqual(hw.sim.actions.count('cups: cup to waste'), 2)

    def test_no_retry_when_it_cannot_help(self):
        hw = load_driver('simulator', faults=['out-of-cups'], sleep=lambda s: None)
        result = Maker(hw).make(job(7))
        self.assertFalse(result.ok)
        self.assertIn('no cups left', result.reason)

    def test_second_cup_failing_wastes_the_first(self):
        hw = load_driver('simulator', sleep=lambda s: None)
        calls = {'n': 0}
        real_seal = hw.sealer.seal

        def seal():
            calls['n'] += 1
            if calls['n'] > 1:
                raise HardwareFault('sealer', 'film out', retryable=False)
            real_seal()
        hw.sealer.seal = seal
        result = Maker(hw).make(job(3, cups=2))
        self.assertFalse(result.ok)
        self.assertIn('pickup: slot 1 to waste', hw.sim.actions)
        self.assertEqual(hw.pickup.held, {})


class ServiceTest(unittest.TestCase):
    def test_paid_order_is_made_and_reported_ready(self):
        backend = FakeBackend([job(1), job(2, milk=False)])
        svc, hw, _ = service(backend)
        made = svc.tick()
        self.assertEqual(made, [(1, 'READY'), (2, 'READY')])
        self.assertEqual([p[:2] for p in backend.progress], [(1, 'READY'), (2, 'READY')])
        self.assertEqual(backend.heartbeats[0][0], 'ONLINE')
        self.assertEqual(backend.heartbeats[0][1]['sealer'], 'ok')
        self.assertEqual(backend.readings[0]['ingredient'], 2)
        self.assertIn('liquids: 80 mL Fresh milk', hw.sim.actions)

    def test_failed_drink_reported_failed_with_reason(self):
        backend = FakeBackend([job(1)])
        svc, hw, _ = service(backend)
        hw.sim.fail_rate = 1.0
        svc.tick()
        self.assertEqual(backend.progress[0][:2], (1, 'FAILED'))
        self.assertIn('random fault', backend.progress[0][2])

    def test_out_of_cups_takes_no_orders_and_tells_the_backend_at_once(self):
        backend = FakeBackend()
        svc, hw, clock = service(backend, heartbeat_every=60)
        svc.tick()
        backend.jobs = [job(1)]
        hw.sim.faults.add('out-of-cups')
        clock.now += 1  # well before the next regular check-in
        self.assertEqual(svc.tick(), [])
        self.assertEqual(backend.heartbeats[-1][1]['cups'], 'empty')
        self.assertEqual(len(backend.jobs), 1)  # the paid order waits
        self.assertEqual(svc.status()['modules_down'], ['cups'])
        hw.sim.faults.discard('out-of-cups')  # refilled
        clock.now += 1
        self.assertEqual(svc.tick(), [(1, 'READY')])
        self.assertEqual(backend.heartbeats[-1][1]['cups'], 'ok')

    def test_full_pickup_rack_in_the_simulator_assumes_the_oldest_cup_was_taken(self):
        backend = FakeBackend([job(n, milk=False) for n in range(1, 9)])
        svc, hw, _ = service(backend)
        made = svc.tick()
        self.assertEqual([status for _, status in made], ['READY'] * 8)
        self.assertIn('pickup: slot 1 taken (assumed)', hw.sim.actions)

    def test_warm_fridge_locks_dairy_locally_but_still_makes_other_drinks(self):
        backend = FakeBackend()
        svc, _, _ = service(backend, faults=['warm-fridge'])
        svc.tick()
        self.assertTrue(svc.lock.tripped)
        self.assertTrue(backend.sfa_locked)  # the backend locked too, from our reading
        backend.jobs = [job(5), job(6, milk=False)]
        svc.tick()
        self.assertEqual(backend.progress[0][:2], (5, 'FAILED'))
        self.assertIn('dairy lock on Fresh milk', backend.progress[0][2])
        self.assertEqual(backend.progress[1][:2], (6, 'READY'))

    def test_silent_probe_locks_after_five_minutes(self):
        backend = FakeBackend()
        svc, _, clock = service(backend, faults=['probe-silent'], temps_every=60)
        svc.tick()
        self.assertFalse(svc.lock.tripped)
        clock.now += 301
        svc.tick()
        self.assertTrue(svc.lock.tripped)
        self.assertGreater(backend.readings[-1]['temp_c'], 4.0)  # sent as out of range

    def test_lock_lifts_only_after_staff_clear_it_and_fridge_is_cold(self):
        backend = FakeBackend()
        svc, hw, clock = service(backend, faults=['warm-fridge'], heartbeat_every=60, temps_every=60)
        svc.tick()
        hw.sim.faults.clear()
        clock.now += 60
        svc.tick()  # fridge cold again, but the backend lock is still on
        self.assertTrue(svc.lock.tripped)
        backend.sfa_locked = False  # staff cleared it in the admin
        clock.now += 60
        svc.tick()
        self.assertFalse(svc.lock.tripped)

    def test_backend_down_queues_reports_and_sends_them_later(self):
        backend = FakeBackend([job(1)])
        svc, _, clock = service(backend, heartbeat_every=60, temps_every=60)
        svc.check_in()
        real = backend.report_progress

        def drop_network(*args):  # the network goes while the drink is being made
            backend.down = True
            return real(*args)
        backend.report_progress = drop_network
        self.assertEqual(svc.make_next(), (1, 'READY'))
        self.assertEqual(len(svc.outbox), 1)
        self.assertFalse(svc.online)
        self.assertEqual(svc.status()['closed_reason'], 'edge_offline')
        self.assertIsNone(svc.make_next())  # no new orders while down
        backend.report_progress, backend.down = real, False
        clock.now += 60
        svc.tick()
        self.assertEqual(backend.progress[0][:2], (1, 'READY'))
        self.assertEqual(len(svc.outbox), 0)

    def test_offline_temperatures_are_kept_and_sent(self):
        backend = FakeBackend()
        svc, _, clock = service(backend, heartbeat_every=60, temps_every=60)
        svc.tick()
        backend.down = True
        for _ in range(3):
            clock.now += 60
            svc.tick()
        self.assertEqual(len(backend.readings), 1)
        backend.down = False
        clock.now += 60
        svc.tick()
        self.assertEqual(len(backend.readings), 5)

    def test_order_interrupted_by_a_restart_is_reported_failed(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'outbox.json')
            outbox = Outbox(path)
            outbox.set_current(9)
            backend = FakeBackend()
            backend.statuses[9] = 'PREPARING'
            svc, _, _ = service(backend, outbox=Outbox(path))
            svc.tick()
            self.assertEqual(backend.progress[0][:2], (9, 'FAILED'))
            self.assertIsNone(Outbox(path).current)

    def test_refused_report_is_dropped_not_retried_forever(self):
        backend = FakeBackend()
        backend.statuses[4] = 'REFUNDED'
        svc, _, _ = service(backend)
        svc.outbox.add({'kind': 'progress', 'order': 4, 'status': 'READY'})
        svc.tick()
        self.assertEqual(len(svc.outbox), 0)

    def test_maintenance_makes_nothing(self):
        backend = FakeBackend([job(1)])
        svc, _, _ = service(backend)
        svc.maintenance = True
        self.assertEqual(svc.tick(), [])
        self.assertEqual(backend.heartbeats[0][0], 'MAINTENANCE')


class DriverTest(unittest.TestCase):
    def test_unknown_fault(self):
        with self.assertRaises(ValueError):
            load_driver('simulator', faults=['on-fire'])

    def test_driver_must_build_hardware(self):
        with self.assertRaises(TypeError):
            load_driver('test_edge')  # its build() below returns the wrong thing

    def test_states(self):
        hw = load_driver('simulator', faults=['seal-jam'])
        self.assertIsInstance(hw, Hardware)
        self.assertEqual(hw.module_states()['sealer'], 'fault')


def build():  # for test_driver_must_build_hardware
    return object()


class ClientTest(unittest.TestCase):
    def client(self, code, body=b'', error=None):
        sent = []

        def transport(method, url, headers, data, timeout):
            sent.append((method, url, headers, data))
            if error:
                raise error
            return code, body
        return BackendClient('http://backend/', 'k3y', transport=transport), sent

    def test_sends_key_and_json(self):
        c, sent = self.client(200, b'{"id": 1, "status": "READY"}')
        self.assertEqual(c.report_progress(1, 'READY'), {'id': 1, 'status': 'READY'})
        method, url, headers, data = sent[0]
        self.assertEqual((method, url), ('POST', 'http://backend/ordering/orders/1/progress/'))
        self.assertEqual(headers['Authorization'], 'Kiosk k3y')
        self.assertEqual(json.loads(data), {'status': 'READY', 'reason': ''})

    def test_nothing_to_make(self):
        self.assertIsNone(self.client(204)[0].next_order())

    def test_errors(self):
        with self.assertRaises(BackendUnavailable):
            self.client(0, error=urllib.error.URLError('refused'))[0].next_order()
        with self.assertRaises(BackendUnavailable):
            self.client(502, b'<html>')[0].next_order()
        with self.assertRaises(BackendRefused):
            self.client(401, b'{"detail": "Unknown kiosk key."}')[0].heartbeat('ONLINE', {})


class ServerTest(unittest.TestCase):
    def setUp(self):
        # a tiny stand-in backend that echoes what it got
        class Echo(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers['Content-Length'] or 0))
                out = json.dumps({'path': self.path, 'body': body.decode()}).encode()
                self.send_response(201)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(out)))
                self.end_headers()
                self.wfile.write(out)
            do_GET = do_POST
        self.backend = ThreadingHTTPServer(('127.0.0.1', 0), Echo)
        self.ui = tempfile.TemporaryDirectory()
        with open(os.path.join(self.ui.name, 'index.html'), 'w') as f:
            f.write('<html>kiosk</html>')
        os.mkdir(os.path.join(self.ui.name, 'assets'))
        with open(os.path.join(self.ui.name, 'assets', 'app.js'), 'w') as f:
            f.write('console.log(1)')
        self.edge = serve('127.0.0.1', 0, f"http://127.0.0.1:{self.backend.server_port}", self.ui.name,
                          status=lambda: {'online': True})
        for s in (self.backend, self.edge):
            threading.Thread(target=s.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.edge.server_port}"

    def tearDown(self):
        for s in (self.backend, self.edge):
            s.shutdown()
            s.server_close()
        self.ui.cleanup()

    def get(self, path, data=None):
        req = urllib.request.Request(self.base + path, data=data, headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                return res.status, res.headers, res.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_proxies_api_without_prefix(self):
        code, _, body = self.get('/api/ordering/orders/', b'{"a": 1}')
        self.assertEqual(code, 201)
        self.assertEqual(json.loads(body), {'path': '/ordering/orders/', 'body': '{"a": 1}'})

    def test_serves_ui_and_falls_back_to_index(self):
        self.assertEqual(self.get('/assets/app.js')[2], b'console.log(1)')
        self.assertEqual(self.get('/collect')[2], b'<html>kiosk</html>')
        self.assertEqual(self.get('/../../etc/passwd')[2], b'<html>kiosk</html>')

    def test_status(self):
        self.assertEqual(json.loads(self.get('/edge/status')[2]), {'online': True})

    def test_backend_down_gives_502(self):
        dead = serve('127.0.0.1', 0, 'http://127.0.0.1:9', None)  # nothing listens on port 9
        threading.Thread(target=dead.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(f"http://127.0.0.1:{dead.server_port}/api/ordering/menu/", timeout=5)
            self.assertEqual(e.exception.code, 502)
            self.assertEqual(json.loads(e.exception.read())['reason'], 'edge_offline')
        finally:
            dead.shutdown()
            dead.server_close()


if __name__ == '__main__':
    unittest.main()
