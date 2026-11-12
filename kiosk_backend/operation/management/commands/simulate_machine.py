"""A pretend drink machine that talks to the backend over the real machine API, the way the edge
service will: it checks in, sends fridge temperatures, takes paid orders, "makes" them and reports
READY or FAILED. Use it to run the shop end to end with no hardware, and to try out faults.

    python manage.py kiosk_key <machine_id>     # once, for a kiosk added in the admin: prints its key
    python manage.py simulate_machine --key <key>
    python manage.py simulate_machine --key <key> --fault warm-fridge
    python manage.py simulate_machine --key <key> --fail-rate 0.3 --make-seconds 2

Faults:
    warm-fridge   probes read 7.0 C: the dairy lock comes on and milk drinks go off sale
    out-of-cups   check-ins report the cups empty: the shop stops selling and paid orders wait for a refill
    offline       stops checking in: after MACHINE_HEARTBEAT_TIMEOUT_SECONDS the shop closes
--fail-rate makes each attempt fail at random; a failed drink is retried once before it's reported.
"""
import json
import os
import random
import time
import urllib.error
import urllib.request

from django.core.management.base import BaseCommand

FAULTS = ['none', 'warm-fridge', 'out-of-cups', 'offline']
MODULES = ['cups', 'ice', 'toppings', 'liquids', 'sealer', 'pickup']


def http_sender(base_url, key):
    """send(method, path, body) -> (status code, parsed JSON or None), over HTTP."""
    def send(method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base_url.rstrip('/') + path, data=data, method=method, headers={
            'Authorization': f"Kiosk {key}", 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                raw = res.read()
                return res.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw) if raw else None
            except ValueError:
                return e.code, None
    return send


class Machine:
    def __init__(self, send, fault='none', fail_rate=0.0, make_seconds=0.0, rng=None, sleep=time.sleep, log=print):
        self.send, self.fault, self.fail_rate = send, fault, fail_rate
        self.make_seconds, self.rng, self.sleep, self.log = make_seconds, rng or random.Random(), sleep, log
        self.chilled = []

    def check_in(self, status='ONLINE'):
        """status is ONLINE, or MAINTENANCE while it's being cleaned or is shut for the night."""
        if self.fault == 'offline':
            self.log("offline: not checking in")
            return None
        modules = {m: 'ok' for m in MODULES}
        if self.fault == 'out-of-cups':
            modules['cups'] = 'empty'
        code, data = self.send('POST', '/operation/machine/heartbeat/', {'status': status, 'modules': modules})
        if code != 200:
            self.log(f"check-in refused: {code} {data}")
            return None
        self.chilled = data['chilled']
        return data

    def send_temperatures(self):
        if not self.chilled or self.fault == 'offline':
            return None
        temp = 7.0 if self.fault == 'warm-fridge' else 3.0
        readings = [{'ingredient': c['ingredient'], 'temp_c': temp} for c in self.chilled]
        code, data = self.send('POST', '/operation/machine/temperatures/', {'readings': readings})
        if code == 200 and data['sfa_locked']:
            self.log(f"dairy lock is on: {data['sfa_lock_reason']}")
        return data

    def attempt(self):
        """One try at making a drink. Returns None if it worked, else what went wrong."""
        self.sleep(self.make_seconds)
        if self.fault == 'out-of-cups':
            return "Out of cups"
        if self.rng.random() < self.fail_rate:
            return self.rng.choice(["Dose off by more than 5%", "Cup jammed", "Seal failed"])
        return None

    def take_next(self):
        """Asks for the next order to make. Returns the job (the order is now PREPARING), or None."""
        if self.fault == 'offline':
            return None
        code, job = self.send('POST', '/operation/machine/next-order/')
        if code != 200:
            return None
        names = ', '.join(i['name'] for i in job['items'])
        self.log(f"making order {job['id']}: {names}")
        return job

    def report(self, job, problem=None):
        """Tells the backend the order is READY, or FAILED with what went wrong. Returns the status
        sent and the backend's reply code."""
        to = 'FAILED' if problem else 'READY'
        code, _ = self.send('POST', f"/ordering/orders/{job['id']}/progress/", {'status': to, 'reason': problem or ''})
        self.log(f"order {job['id']}: {to}{' (' + problem + ')' if problem else ''}")
        return to, code

    def make(self, job):
        """Makes the drinks, retrying a failed one once. Returns None if it worked, else the problem."""
        problem = self.attempt()
        if problem:
            self.log(f"order {job['id']}: {problem}, retrying once with a new cup")
            problem = self.attempt()
        return problem

    def make_next(self):
        """Takes and makes one order. Returns (order id, final status), or None if there was nothing."""
        job = self.take_next()
        if job is None:
            return None
        to, _ = self.report(job, self.make(job))
        return job['id'], to

    def tick(self):
        """One cycle: check in, send temperatures, make every waiting order."""
        self.check_in()
        self.send_temperatures()
        made = []
        while (result := self.make_next()) is not None:
            made.append(result)
        return made


class Command(BaseCommand):
    help = "Pretend to be the drink machine, over the real machine API, so the shop runs without hardware."

    def add_arguments(self, parser):
        parser.add_argument('--url', default='http://127.0.0.1:8000', help="The backend (default: local dev server).")
        parser.add_argument('--key', default=os.environ.get('KIOSK_KEY', ''),
                            help="The machine's kiosk key (or set KIOSK_KEY); make one with `manage.py kiosk_key`.")
        parser.add_argument('--fault', choices=FAULTS, default='none')
        parser.add_argument('--fail-rate', type=float, default=0.0, help="Chance each attempt fails, 0 to 1.")
        parser.add_argument('--make-seconds', type=float, default=5.0, help="How long a drink takes.")
        parser.add_argument('--every', type=float, default=10.0, help="Seconds between check-ins.")
        parser.add_argument('--once', action='store_true', help="Run one cycle and stop.")

    def handle(self, *args, **options):
        if not options['key']:
            self.stderr.write("Give the machine's key with --key (make one with `manage.py kiosk_key <machine_id>`).")
            return
        machine = Machine(http_sender(options['url'], options['key']), fault=options['fault'],
                          fail_rate=options['fail_rate'], make_seconds=options['make_seconds'],
                          log=lambda line: self.stdout.write(line))
        self.stdout.write(f"Simulated machine talking to {options['url']} (fault: {options['fault']}). Ctrl-C stops.")
        while True:
            machine.tick()
            if options['once']:
                return
            time.sleep(options['every'])
