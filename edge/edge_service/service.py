"""The edge service's main loop: check in, watch the fridge, take paid orders and make them.

Each tick:
1. Send anything still queued (results and readings from while the backend was unreachable).
2. Check in (every heartbeat_every seconds) with each module's state. The reply says whether the shop
   is open, whether the dairy lock is on, and which chilled ingredients need temperature readings.
3. Read the probes (every temps_every seconds); out of range or silent trips the local dairy lock.
4. While the backend is reachable, take the next paid order and make it; report READY or FAILED.

Offline it keeps reading temperatures and queuing them, and finishes the order in hand. It can't
take new orders, and the backend closes the shop when check-ins stop.
"""
import logging
import time
from datetime import datetime, timezone

from .backend import BackendRefused, BackendUnavailable
from .hardware import Ingredient
from .maker import Maker
from .safety import DairyLock

logger = logging.getLogger('edge.service')

# parts without which no drink can be made (same list as the backend's availability.py): while one is
# down the edge takes no orders, so paid orders wait for the refill instead of failing
ESSENTIAL_MODULES = ('cups', 'sealer', 'pickup', 'liquids')
DOWN_STATES = ('empty', 'fault')


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class EdgeService:
    def __init__(self, client, hardware, outbox, heartbeat_every=60.0, temps_every=60.0, max_orders_per_tick=10,
                 clock=time.monotonic, wall=utc_now):
        self.client, self.hw, self.outbox = client, hardware, outbox
        self.maker, self.lock = Maker(hardware), DairyLock()
        self.heartbeat_every, self.temps_every, self.max_orders_per_tick = heartbeat_every, temps_every, max_orders_per_tick
        self.clock, self.wall = clock, wall
        self.next_heartbeat = self.next_temps = 0.0
        self.online, self.shop_open, self.closed_reason = False, False, None
        self.chilled = []
        self.maintenance = False
        self.offline_retry = 5.0
        self.sent_states = None  # module states in the last check-in the backend got
        self.making = None
        self.made = []  # (order id, status) of every order finished since start
        self.recover_interrupted_order()

    # --- startup ---

    def recover_interrupted_order(self):
        """An order that was being made when the edge stopped can't be finished: its cup state is unknown."""
        order_id = self.outbox.current
        if order_id is not None:
            logger.error("Order %s was being made when the edge stopped; reporting it FAILED", order_id)
            self.hw.cups.discard_cup()
            self.hw.pickup.release_to_waste(order_id)
            self.outbox.add({'kind': 'progress', 'order': order_id, 'status': 'FAILED',
                             'reason': "Edge service restarted mid-drink"})
            self.outbox.set_current(None)

    # --- talking to the backend ---

    def flush(self):
        sent = self.outbox.flush(self.client)
        self.online = self.online and sent
        return sent

    def check_in(self):
        status = 'MAINTENANCE' if self.maintenance else 'ONLINE'
        states = self.hw.module_states()
        try:
            reply = self.client.heartbeat(status, states)
        except BackendUnavailable as e:
            if self.online:
                logger.warning("Backend unreachable (%s); finishing work in hand and queuing reports", e)
            self.online = False
            return None
        except BackendRefused as e:
            logger.error("Check-in refused: %s %s (is the kiosk key right?)", e.code, e.data)
            self.online = False
            return None
        if not self.online:
            logger.info("Backend reachable; shop %s", "open" if reply['shop_open'] else f"closed ({reply['closed_reason']})")
        self.online = True
        self.sent_states = states
        self.shop_open, self.closed_reason = reply['shop_open'], reply['closed_reason']
        self.chilled = reply.get('chilled', [])
        self.lock.sync(reply['sfa_locked'], nothing_unsent=len(self.outbox) == 0)
        return reply

    def read_temperatures(self):
        if not self.chilled:
            return []
        temps = {}
        for c in self.chilled:
            try:
                temps[c['ingredient']] = self.hw.temperatures.read(_ingredient(c))
            except Exception:
                logger.exception("Probe for %s failed", c['name'])
                temps[c['ingredient']] = None
        readings = [{'ingredient': c['ingredient'], 'temp_c': round(temp, 1), 'recorded_at': self.wall()}
                    for c, temp in self.lock.check(self.chilled, temps, self.clock())]
        if readings:
            self.outbox.add({'kind': 'temperatures', 'readings': readings})
        return readings

    # --- making orders ---

    def make_next(self):
        """Takes and makes one order. Returns (order id, status), or None when there's nothing to do."""
        try:
            job = self.client.next_order()
        except BackendUnavailable:
            self.online = False
            return None
        except BackendRefused as e:
            logger.error("next-order refused: %s %s", e.code, e.data)
            return None
        if job is None:
            return None
        order_id = job['id']
        self.outbox.set_current(order_id)
        self.making = order_id
        names = ', '.join(item['name'] for item in job['items'])
        blocked = self.lock.blocks(job, self.chilled)
        if blocked:
            status, reason = 'FAILED', f"Not made: dairy lock on {', '.join(blocked)}"[:200]
        else:
            logger.info("Making order %s: %s", order_id, names)
            result = self.maker.make(job)
            status, reason = ('READY', f"Pickup slot {', '.join(map(str, result.slots))}") if result.ok \
                else ('FAILED', result.reason)
        logger.log(logging.INFO if status == 'READY' else logging.ERROR, "Order %s: %s (%s)", order_id, status, reason)
        # queue the result before forgetting the order, so it's sent even if the edge stops right here
        self.outbox.add({'kind': 'progress', 'order': order_id, 'status': status, 'reason': reason})
        self.outbox.set_current(None)
        self.making = None
        self.made.append((order_id, status))
        self.flush()
        return order_id, status

    # --- the loop ---

    def tick(self):
        now = self.clock()
        if self.online:
            self.flush()
        # a part that ran out or broke (or was fixed) is told to the backend at once, not in a minute
        if self.online and self.hw.module_states() != self.sent_states:
            self.next_heartbeat = now
        if now >= self.next_heartbeat:
            self.next_heartbeat = now + self.heartbeat_every
            if self.check_in():
                self.flush()
            else:  # try again soon, so the shop reopens quickly once the backend is back
                self.next_heartbeat = now + min(self.heartbeat_every, self.offline_retry)
        if now >= self.next_temps and self.chilled:  # the first check-in says which probes to read
            self.next_temps = now + self.temps_every
            if self.read_temperatures():
                self.flush()
        made = []
        if self.online and not self.maintenance:
            for _ in range(self.max_orders_per_tick):
                down = self.modules_down()
                if down:
                    if self.hw.module_states() != self.sent_states:
                        self.check_in()
                    logger.debug("Not taking orders: %s down", ', '.join(down))
                    break
                result = self.make_next()
                if result is None:
                    break
                made.append(result)
        return made

    def modules_down(self):
        states = self.hw.module_states()
        return [m for m in ESSENTIAL_MODULES if states.get(m) in DOWN_STATES]

    def status(self):
        """For the kiosk screen and staff: what the edge knows right now."""
        return {'online': self.online, 'shop_open': self.online and self.shop_open,
                'closed_reason': self.closed_reason if self.online else 'edge_offline',
                'dairy_lock': self.lock.tripped, 'dairy_lock_reason': self.lock.reason,
                'making': self.making, 'unsent_reports': len(self.outbox), 'modules': self.hw.module_states(),
                'modules_down': self.modules_down()}

    def run(self, stop, poll_every=3.0):
        """Ticks until stop (a threading.Event) is set."""
        while not stop.is_set():
            try:
                self.tick()
            except Exception:  # never let one bad reply stop the machine; the watchdog covers real crashes
                logger.exception("Edge tick failed")
            stop.wait(poll_every)


def _ingredient(chilled):
    return Ingredient(chilled['ingredient'], chilled.get('code'), chilled['name'])
