"""Reports the backend hasn't received yet, kept on disk so a network drop or a restart loses nothing.

Order results and temperature readings go through here: they're saved first, then sent. When the
backend can't be reached they stay queued and go out, in order, once it's back. The file also
remembers the order being made right now, so a crash mid-drink can be reported as FAILED on restart.
"""
import json
import logging
import os
import threading

from .backend import BackendRefused, BackendUnavailable

logger = logging.getLogger('edge.outbox')


class Outbox:
    def __init__(self, path=None):
        """path=None keeps everything in memory (tests, --once runs)."""
        self.path, self.lock = path, threading.Lock()
        self.pending, self.current = [], None
        if path and os.path.exists(path):
            with open(path) as f:
                saved = json.load(f)
            self.pending, self.current = saved.get('pending', []), saved.get('current')

    def _save(self):
        if not self.path:
            return
        tmp = self.path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump({'pending': self.pending, 'current': self.current}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)  # atomic, so a power cut leaves the old file or the new one

    def add(self, message):
        with self.lock:
            self.pending.append(message)
            self._save()

    def set_current(self, order_id):
        with self.lock:
            self.current = order_id
            self._save()

    def __len__(self):
        return len(self.pending)

    def flush(self, client):
        """Sends what's queued, oldest first. Returns True when everything went, False if the backend
        is unreachable (the rest stays queued). A message the backend refuses is logged and dropped."""
        while True:
            with self.lock:
                if not self.pending:
                    return True
                message = self.pending[0]
            try:
                deliver(client, message)
            except BackendUnavailable:
                return False
            except BackendRefused as e:
                logger.error("Backend refused %s: %s %s", message, e.code, e.data)
            with self.lock:
                self.pending.pop(0)
                self._save()


def deliver(client, message):
    if message['kind'] == 'progress':
        client.report_progress(message['order'], message['status'], message.get('reason', ''))
    elif message['kind'] == 'temperatures':
        client.send_temperatures(message['readings'])
    else:
        logger.error("Dropping unknown message %s", message)
