"""The kiosk screen's local web server.

- Serves the built kiosk UI (kiosk-app/dist) with a fallback to index.html for its routes.
- Forwards /api/... to the cloud backend without the /api prefix, like the Vite dev proxy, so the
  screen sees one origin. The kiosk key is not added: the screen orders like any customer.
- GET /edge/status says whether the edge is online, the dairy lock and the module states, so the
  screen can show "temporarily closed" when the edge can't reach the backend.
"""
import json
import logging
import mimetypes
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger('edge.server')

FORWARD_REQUEST = ('Content-Type', 'Accept', 'Accept-Language', 'Authorization', 'Cookie', 'X-CSRFToken')
FORWARD_REPLY = ('Content-Type', 'Set-Cookie', 'Cache-Control', 'Location', 'Retry-After')


def make_handler(backend_url, ui_dir, status=None, timeout=15.0):
    backend_url = backend_url.rstrip('/')
    ui_dir = os.path.realpath(ui_dir) if ui_dir else None

    class Handler(BaseHTTPRequestHandler):
        server_version = 'KioskEdge'

        def log_message(self, fmt, *args):
            logger.debug("%s %s", self.address_string(), fmt % args)

        def reply(self, code, body, content_type='application/json', headers=()):
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def proxy(self):
            length = int(self.headers.get('Content-Length') or 0)
            body = self.rfile.read(length) if length else None
            headers = {h: self.headers[h] for h in FORWARD_REQUEST if self.headers.get(h)}
            url = backend_url + (self.path[len('/api'):] or '/')
            req = urllib.request.Request(url, data=body, method=self.command, headers=headers)
            try:
                try:
                    res = urllib.request.urlopen(req, timeout=timeout)
                except urllib.error.HTTPError as e:
                    res = e
                with res:
                    data = res.read()
                    passed = [(h, v) for h in FORWARD_REPLY if h != 'Content-Type' for v in res.headers.get_all(h) or []]
                    self.reply(res.status, data, res.headers.get('Content-Type', 'application/octet-stream'), passed)
            except OSError as e:
                logger.warning("Backend unreachable for %s %s: %s", self.command, self.path, e)
                self.reply(502, json.dumps({'error': "The shop is offline right now. Please try again later.",
                                            'reason': 'edge_offline'}).encode())

        def static(self):
            if not ui_dir:
                return self.reply(404, b'{"error": "No kiosk UI here: build kiosk-app first."}')
            rel = self.path.split('?', 1)[0].split('#', 1)[0].lstrip('/')
            path = os.path.realpath(os.path.join(ui_dir, rel))
            if not path.startswith(ui_dir + os.sep) or not os.path.isfile(path):
                path = os.path.join(ui_dir, 'index.html')  # a screen route, e.g. /collect
            if not os.path.isfile(path):
                return self.reply(404, b'{"error": "No index.html: build kiosk-app first."}')
            with open(path, 'rb') as f:
                data = f.read()
            kind = mimetypes.guess_type(path)[0] or 'application/octet-stream'
            # hashed asset names change with each build; index.html must always be fresh
            cache = 'no-cache' if path.endswith('index.html') else 'public, max-age=31536000, immutable'
            self.reply(200, data, kind, [('Cache-Control', cache)])

        def route(self):
            if self.path == '/api' or self.path.startswith('/api/'):
                return self.proxy()
            if self.path.split('?')[0] == '/edge/status' and self.command in ('GET', 'HEAD'):
                return self.reply(200, json.dumps(status() if status else {}).encode())
            if self.command in ('GET', 'HEAD'):
                return self.static()
            self.reply(405, b'{"error": "Method not allowed."}')

        do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = route

    return Handler


def serve(host, port, backend_url, ui_dir, status=None):
    """Starts the server; call serve_forever() on the result (in a thread)."""
    return ThreadingHTTPServer((host, port), make_handler(backend_url, ui_dir, status))
