"""The edge service on a bad day: a wrong kiosk key, a probe that throws, a reply it doesn't expect,
and starting it from the command line."""
import io
import logging
import os
import tempfile
import threading
import unittest
import urllib.error
from unittest import mock

from edge_service import __main__ as cli
from edge_service.backend import BackendClient, BackendRefused, urllib_transport

from fakes import FakeBackend, job
from test_edge import service


class RefusingBackend(FakeBackend):
    """The backend says no (wrong or revoked kiosk key)."""

    def heartbeat(self, status, modules):
        raise BackendRefused(401, {'detail': 'Invalid kiosk key.'})

    def next_order(self):
        raise BackendRefused(403, {'detail': 'Not this machine.'})


class RefusedTest(unittest.TestCase):
    def test_wrong_key_keeps_the_shop_closed_and_makes_nothing(self):
        backend = RefusingBackend([job(1)])
        svc, _, _ = service(backend)
        with self.assertLogs('edge.service', 'ERROR') as logs:
            self.assertEqual(svc.tick(), [])
        self.assertIn('kiosk key', logs.output[0])
        self.assertFalse(svc.online)
        self.assertFalse(svc.status()['shop_open'])
        self.assertEqual(backend.jobs, [job(1)])  # nothing taken

    def test_refused_next_order_is_skipped_without_going_offline(self):
        backend = FakeBackend([job(1)])
        backend.next_order = RefusingBackend.next_order.__get__(backend)
        svc, _, _ = service(backend)
        with self.assertLogs('edge.service', 'ERROR'):
            self.assertEqual(svc.tick(), [])
        self.assertTrue(svc.online)  # a 4xx is not a network problem


class ProbeTest(unittest.TestCase):
    def test_probe_that_throws_counts_as_silent_and_locks_dairy_after_five_minutes(self):
        backend = FakeBackend([job(1)])
        svc, hw, clock = service(backend, heartbeat_every=60, temps_every=60)
        with mock.patch.object(hw.temperatures, 'read', side_effect=OSError('i2c bus error')), \
                self.assertLogs('edge.service', 'ERROR'):
            svc.tick()
            self.assertFalse(svc.lock.tripped)  # one missed reading is not yet a reason to stop
            for _ in range(5):
                clock.now += 60
                svc.tick()
        self.assertTrue(svc.lock.tripped)
        self.assertIn('silent', svc.lock.reason)
        # the silent probe is reported to the backend as too warm, so its lock goes on too
        self.assertTrue(backend.sfa_locked)

    def test_dairy_lock_still_makes_drinks_without_milk(self):
        backend = FakeBackend([job(1, milk=False), job(2, milk=True)])
        svc, _, _ = service(backend)
        svc.check_in()
        svc.lock.trip('test')
        self.assertEqual(svc.make_next(), (1, 'READY'))
        self.assertEqual(svc.make_next()[1], 'FAILED')
        self.assertIn('dairy lock', backend.progress[-1][2])


class LoopTest(unittest.TestCase):
    def test_one_bad_tick_does_not_stop_the_machine(self):
        backend = FakeBackend()
        svc, _, _ = service(backend)
        stop = threading.Event()
        calls = []

        def tick():
            calls.append(1)
            if len(calls) == 1:
                raise KeyError('closed_reason')  # a reply missing a field
            stop.set()
        svc.tick = tick
        with self.assertLogs('edge.service', 'ERROR'):
            svc.run(stop, poll_every=0)
        self.assertEqual(len(calls), 2)


class TransportTest(unittest.TestCase):
    def test_http_errors_are_returned_not_raised(self):
        err = urllib.error.HTTPError('http://x', 409, 'Conflict', {}, io.BytesIO(b'{"status": "PAID"}'))
        with mock.patch('urllib.request.urlopen', side_effect=err):
            self.assertEqual(urllib_transport('POST', 'http://x', {}, b'', 1), (409, b'{"status": "PAID"}'))

    def test_answer_is_read(self):
        res = mock.MagicMock()
        res.__enter__.return_value.status = 200
        res.__enter__.return_value.read.return_value = b'{}'
        with mock.patch('urllib.request.urlopen', return_value=res) as urlopen:
            self.assertEqual(urllib_transport('GET', 'http://x/y', {'A': 'b'}, None, 3), (200, b'{}'))
        req = urlopen.call_args[0][0]
        self.assertEqual((req.full_url, req.get_method(), urlopen.call_args[1]['timeout']), ('http://x/y', 'GET', 3))

    def test_non_json_error_page_still_counts_as_refused(self):
        client = BackendClient('http://x/', 'k', transport=lambda *a: (403, b'<html>Forbidden</html>'))
        with self.assertRaises(BackendRefused) as caught:
            client.heartbeat('ONLINE', {})
        self.assertIsNone(caught.exception.data)


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(('EDGE_', 'KIOSK_'))}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        # main() sets up logging for the whole process; put it back afterwards
        root = logging.getLogger()
        handlers, level = root.handlers[:], root.level
        self.addCleanup(lambda: (setattr(root, 'handlers', handlers), root.setLevel(level)))

    def test_no_key_refuses_to_start(self):
        with self.assertLogs('edge', 'ERROR'):
            self.assertEqual(cli.main(['--once']), 2)

    def test_key_from_a_file(self):
        with tempfile.NamedTemporaryFile('w', suffix='.key', delete=False) as f:
            f.write('  secret-key\n')
        self.addCleanup(os.unlink, f.name)
        os.environ['KIOSK_KEY_FILE'] = f.name
        self.assertEqual(cli.read_key(cli.parse([])), 'secret-key')
        self.assertEqual(cli.read_key(cli.parse(['--key', ' flag-key '])), 'flag-key')

    def test_settings_from_the_environment_and_flags(self):
        os.environ.update({'EDGE_FAULTS': 'warm_fridge,out_of_cups', 'EDGE_PORT': '9090', 'EDGE_HEARTBEAT_SECONDS': ''})
        args = cli.parse(['--fault', 'offline', '--port', '9191'])
        self.assertEqual(args.fault, ['warm_fridge', 'out_of_cups', 'offline'])
        self.assertEqual(args.port, 9191)
        self.assertEqual(args.heartbeat_seconds, 60)  # empty means default

    def test_once_with_the_backend_down_exits_non_zero(self):
        with tempfile.TemporaryDirectory() as d, self.assertLogs('edge', 'INFO'):
            # nothing listens on port 9 (discard); the check-in fails and --once reports it
            code = cli.main(['--once', '--key', 'k', '--backend', 'http://127.0.0.1:9', '--data-dir', d,
                             '--step-seconds', '0'])
        self.assertEqual(code, 1)

    def test_once_makes_what_is_waiting(self):
        backend = FakeBackend([job(1)])
        with tempfile.TemporaryDirectory() as d, self.assertLogs('edge', 'INFO'), \
                mock.patch.object(cli, 'BackendClient', return_value=backend):
            code = cli.main(['--once', '--key', 'k', '--data-dir', d, '--step-seconds', '0'])
            self.assertTrue(os.path.isdir(d))
        self.assertEqual(code, 0)
        self.assertEqual(backend.progress[0][:2], (1, 'READY'))


if __name__ == '__main__':
    unittest.main()
