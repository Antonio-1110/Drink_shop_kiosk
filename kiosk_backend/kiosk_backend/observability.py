"""Request logging for a shop that runs with nobody on site: each request gets an id, and one log
line says what was asked, the answer, how long it took and how many database queries it ran.

- The id comes back in the X-Request-ID header and is added to every log line written while the
  request runs, so a customer's or a machine's complaint can be matched to the logs. A kiosk or
  proxy may send its own X-Request-ID (letters, digits, - and _ only) to tie the two sides together.
- Requests slower than SLOW_REQUEST_MS, or running more than SLOW_REQUEST_QUERIES queries, are
  logged as warnings, so a slow page shows up before customers notice.
- LOG_FORMAT=json writes each log line as one JSON object (for a log service); the default is
  plain text.
"""
import json
import logging
import re
import time
import uuid
from contextvars import ContextVar

from django.conf import settings
from django.db import connection

logger = logging.getLogger('kiosk.requests')

request_id = ContextVar('request_id', default='-')
VALID_ID = re.compile(r'^[A-Za-z0-9_-]{8,64}$')
# polled constantly by Docker and uptime monitors; logging them would drown everything else
QUIET_PATHS = ('/healthz/',)


class RequestIdFilter(logging.Filter):
    """Puts the current request's id on every log record as record.request_id."""
    def filter(self, record):
        if not hasattr(record, 'request_id'):  # the request log line brings its own
            record.request_id = request_id.get()
        return True


class JsonFormatter(logging.Formatter):
    # LogRecord attributes that aren't extra fields passed with logger.info(..., extra={})
    STANDARD = set(vars(logging.LogRecord('', 0, '', 0, '', None, None))) | {'message', 'asctime', 'request_id'}

    def format(self, record):
        entry = {'time': self.formatTime(record, '%Y-%m-%dT%H:%M:%S%z'), 'level': record.levelname,
                 'logger': record.name, 'message': record.getMessage(),
                 'request_id': getattr(record, 'request_id', '-')}
        entry.update({k: v for k, v in vars(record).items() if k not in self.STANDARD})
        if record.exc_info:
            entry['exception'] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def client_ip(request):
    """The visitor's address. Behind Caddy or a platform's load balancer that is the last
    X-Forwarded-For entry the proxies added (NUM_PROXIES in settings.REST_FRAMEWORK, the same rule
    the rate limits use); anything before it the visitor could have made up."""
    num_proxies = settings.REST_FRAMEWORK.get('NUM_PROXIES') or 0
    forwarded = [a.strip() for a in request.META.get('HTTP_X_FORWARDED_FOR', '').split(',') if a.strip()]
    if num_proxies and forwarded:
        return forwarded[-min(num_proxies, len(forwarded))]
    return request.META.get('REMOTE_ADDR', '')


class QueryCounter:
    def __init__(self):
        self.count = 0

    def __call__(self, execute, sql, params, many, context):
        self.count += 1
        return execute(sql, params, many, context)


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get('X-Request-ID', '')
        rid = incoming if VALID_ID.match(incoming) else uuid.uuid4().hex
        token = request_id.set(rid)
        counter = QueryCounter()
        start = time.monotonic()
        try:
            with connection.execute_wrapper(counter):
                response = self.get_response(request)
        finally:
            request_id.reset(token)
        ms = round((time.monotonic() - start) * 1000)
        response['X-Request-ID'] = rid
        if request.path not in QUIET_PATHS:
            slow = ms >= settings.SLOW_REQUEST_MS or counter.count >= settings.SLOW_REQUEST_QUERIES
            level = (logging.ERROR if response.status_code >= 500
                     else logging.WARNING if slow else logging.INFO)
            logger.log(level, "%s %s %s %dms %d queries", request.method, request.path,
                       response.status_code, ms, counter.count,
                       extra={'request_id': rid, 'method': request.method, 'path': request.path,
                              'ip': client_ip(request),
                              'status': response.status_code, 'duration_ms': ms,
                              'queries': counter.count, 'slow': slow})
        return response
