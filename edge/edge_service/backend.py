"""Talks to the cloud backend's machine API with the kiosk key (`Authorization: Kiosk <key>`).

    POST /operation/machine/heartbeat/       check in, get the shop state and the chilled ingredients
    POST /operation/machine/temperatures/    probe readings (feeds the dairy lock)
    POST /operation/machine/next-order/      take the oldest paid order (moves it to PREPARING)
    POST /ordering/orders/<id>/progress/     report READY or FAILED

Network errors and 5xx replies raise BackendUnavailable, so the caller can keep the message for later.
"""
import json
import urllib.error
import urllib.request


class BackendUnavailable(Exception):
    """The backend couldn't be reached or had a server error. Try again later."""


class BackendRefused(Exception):
    """The backend answered with a 4xx: sending the same thing again won't help."""
    def __init__(self, code, data):
        super().__init__(f"{code}: {data}")
        self.code, self.data = code, data


def urllib_transport(method, url, headers, body, timeout):
    """(status code, body bytes). Raises OSError (URLError is one) if there's no answer."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class BackendClient:
    def __init__(self, base_url, key, timeout=10.0, transport=urllib_transport):
        self.base_url, self.key, self.timeout, self.transport = base_url.rstrip('/'), key, timeout, transport

    def send(self, method, path, body=None):
        """(status code, parsed JSON or None). Raises BackendUnavailable or BackendRefused."""
        data = json.dumps(body).encode() if body is not None else None
        headers = {'Authorization': f"Kiosk {self.key}", 'Content-Type': 'application/json',
                   'Accept': 'application/json'}
        try:
            code, raw = self.transport(method, self.base_url + path, headers, data, self.timeout)
        except OSError as e:  # refused, timed out, DNS, TLS
            raise BackendUnavailable(str(e)) from e
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = None
        if code >= 500:
            raise BackendUnavailable(f"{code} from {path}")
        if code >= 400:
            raise BackendRefused(code, parsed)
        return code, parsed

    def heartbeat(self, status, modules):
        return self.send('POST', '/operation/machine/heartbeat/', {'status': status, 'modules': modules})[1]

    def send_temperatures(self, readings):
        """readings: [{'ingredient': id, 'temp_c': 3.1, 'recorded_at': ISO time}]"""
        return self.send('POST', '/operation/machine/temperatures/', {'readings': readings})[1]

    def next_order(self):
        """The next order to make, or None when there's nothing."""
        code, job = self.send('POST', '/operation/machine/next-order/')
        return job if code == 200 else None

    def report_progress(self, order_id, status, reason=''):
        return self.send('POST', f"/ordering/orders/{order_id}/progress/", {'status': status, 'reason': reason})[1]
