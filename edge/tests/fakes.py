"""A pretend backend for the edge tests: same replies as the real machine API, kept in memory."""
from edge_service.backend import BackendRefused, BackendUnavailable

MILK = {'ingredient': 2, 'code': 'FM', 'name': 'Fresh milk', 'min_safe_temp_c': '0.0', 'max_safe_temp_c': '4.0'}


def job(order_id, milk=True, cups=1):
    lines = [{'ingredient': 1, 'code': 'BT', 'name': 'Black tea', 'kind': 'LIQUID', 'unit': 'mL', 'amount': '250.00'},
             {'ingredient': 4, 'code': None, 'name': 'Ice', 'kind': 'OTHER', 'unit': 'g', 'amount': '150.00'},
             {'ingredient': 5, 'code': 'TP', 'name': 'Tapioca pearls', 'kind': 'TOPPING', 'unit': 'g', 'amount': '60.00'},
             {'ingredient': 6, 'code': 'BS', 'name': 'Brown sugar syrup', 'kind': 'LIQUID', 'unit': 'mL', 'amount': '0.00'}]
    if milk:
        lines.append({'ingredient': 2, 'code': 'FM', 'name': 'Fresh milk', 'kind': 'LIQUID', 'unit': 'mL', 'amount': '80.00'})
    items = [{'item': order_id * 10 + n, 'name': 'Milk Tea' if milk else 'Black Tea', 'size': 'Large',
              'sugar': '0%', 'ice': 'Normal', 'lines': lines} for n in range(cups)]
    return {'id': order_id, 'status': 'PREPARING', 'items': items}


class FakeBackend:
    def __init__(self, jobs=(), chilled=(MILK,)):
        self.jobs, self.chilled = list(jobs), list(chilled)
        self.down = False
        self.sfa_locked = False
        self.heartbeats, self.readings, self.progress = [], [], []
        self.statuses = {}

    def _check(self):
        if self.down:
            raise BackendUnavailable("connection refused")

    def _state(self):
        return {'shop_open': True, 'closed_reason': None, 'sfa_locked': self.sfa_locked, 'sfa_lock_reason': ''}

    def heartbeat(self, status, modules):
        self._check()
        self.heartbeats.append((status, modules))
        return {**self._state(), 'chilled': self.chilled}

    def send_temperatures(self, readings):
        self._check()
        self.readings.extend(readings)
        for r in readings:
            c = next(c for c in self.chilled if c['ingredient'] == r['ingredient'])
            if not float(c['min_safe_temp_c']) <= r['temp_c'] <= float(c['max_safe_temp_c']):
                self.sfa_locked = True
        return {**self._state(), 'recorded': len(readings)}

    def next_order(self):
        self._check()
        if not self.jobs:
            return None
        taken = self.jobs.pop(0)
        self.statuses[taken['id']] = 'PREPARING'
        return taken

    def report_progress(self, order_id, status, reason=''):
        self._check()
        if self.statuses.get(order_id) not in ('PREPARING', status):
            raise BackendRefused(409, {'status': self.statuses.get(order_id)})
        self.statuses[order_id] = status
        self.progress.append((order_id, status, reason))
        return {'id': order_id, 'status': status}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now
