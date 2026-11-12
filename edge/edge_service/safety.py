"""The local dairy lock: food safety that holds even when the backend can't be reached.

The backend owns the real lock (it takes chilled drinks off sale until staff clear it). The edge keeps
its own copy so it never makes a dairy drink from a warm fridge, even offline:

- A reading outside an ingredient's safe range trips the lock at once.
- A probe that hasn't answered for PROBE_SILENT_SECONDS counts as out of range (hardware spec,
  "Cold storage and the dairy lock").
- Once tripped, only staff can clear it: the local lock lifts when the backend says its lock is off
  and every probe reads in range again.
"""
import logging

logger = logging.getLogger('edge.safety')
PROBE_SILENT_SECONDS = 300


def in_range(temp, chilled):
    low, high = chilled.get('min_safe_temp_c'), chilled.get('max_safe_temp_c')
    return (low is None or temp >= float(low)) and (high is None or temp <= float(high))


class DairyLock:
    def __init__(self, silent_after=PROBE_SILENT_SECONDS):
        self.silent_after = silent_after
        self.tripped, self.reason = False, ''
        self.last_heard = {}  # ingredient id -> clock time of its last reading
        self.all_in_range = True

    def trip(self, reason):
        if not self.tripped:
            logger.error("Dairy lock on: %s", reason)
        self.tripped, self.reason = True, reason

    def check(self, chilled, temps, now):
        """chilled: the backend's chilled ingredient list. temps: {ingredient id: degrees C or None}.
        Returns the readings to send: [(chilled entry, temp_c)], with a silent probe sent as out of range."""
        to_send, all_ok = [], True
        for c in chilled:
            temp = temps.get(c['ingredient'])
            if temp is not None:
                self.last_heard[c['ingredient']] = now
                to_send.append((c, temp))
                if not in_range(temp, c):
                    all_ok = False
                    self.trip(f"{c['name']} at {temp:.1f} C")
                continue
            all_ok = False
            heard = self.last_heard.setdefault(c['ingredient'], now)
            if now - heard >= self.silent_after:
                self.trip(f"{c['name']} probe silent for {int(now - heard)} s")
                # the backend asks a silent probe to be reported as an out-of-range reading
                high = c.get('max_safe_temp_c')
                to_send.append((c, float(high) + 1.0 if high is not None else 99.0))
        self.all_in_range = all_ok
        return to_send

    def sync(self, backend_locked, nothing_unsent):
        """After a check-in: follow the backend's lock, and lift ours only once staff cleared theirs,
        our readings reached them and the probes read fine."""
        if backend_locked:
            self.trip("locked by the backend")
        elif self.tripped and nothing_unsent and self.all_in_range:
            logger.warning("Dairy lock cleared by staff")
            self.tripped, self.reason = False, ''

    def blocks(self, job, chilled):
        """Names of the job's ingredients the lock stops, empty if none."""
        if not self.tripped:
            return []
        ids = {c['ingredient'] for c in chilled}
        return sorted({line['name'] for item in job['items'] for line in item['lines'] if line['ingredient'] in ids})
