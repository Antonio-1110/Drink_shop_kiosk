"""Slows down password guessing on staff accounts.

Staff sign in two ways: the admin login page (/admin/login/, also used by the dashboard) and HTTP
Basic auth on the API. Each wrong password from an address counts; after
ADMIN_LOGIN_ATTEMPTS failures within ADMIN_LOGIN_WINDOW_MINUTES, that address gets 429 for both
until the window has passed. A successful login clears the count. Customers and machines don't
use passwords, so this never gets in their way.

The counts live in the cache, which production keeps in the database (settings.CACHES) so every
web server process shares them.
"""
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

from .observability import client_ip

logger = logging.getLogger('kiosk.security')

LOGIN_PATH = '/admin/login/'


def _key(ip):
    return f'login-failures:{ip}'


class LoginLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        logging_in = request.method == 'POST' and request.path == LOGIN_PATH
        basic = request.headers.get('Authorization', '').lower().startswith('basic ')
        if not (logging_in or basic):
            return self.get_response(request)
        ip = client_ip(request)
        if cache.get(_key(ip), 0) >= settings.ADMIN_LOGIN_ATTEMPTS:
            return HttpResponse("Too many failed sign-ins. Try again later.", status=429,
                                content_type='text/plain', headers={
                                    'Retry-After': str(settings.ADMIN_LOGIN_WINDOW_MINUTES * 60)})
        response = self.get_response(request)
        # the login page answers a wrong password by showing the form again (200); a right one redirects
        # DRF answers wrong Basic credentials with 401, or 403 when session auth is listed first
        failed = (basic and response.status_code in (401, 403)) or (logging_in and response.status_code == 200)
        if failed:
            key = _key(ip)
            cache.add(key, 0, settings.ADMIN_LOGIN_WINDOW_MINUTES * 60)
            try:
                count = cache.incr(key)
            except ValueError:  # expired between add and incr
                cache.set(key, count := 1, settings.ADMIN_LOGIN_WINDOW_MINUTES * 60)
            if count == settings.ADMIN_LOGIN_ATTEMPTS:
                logger.warning("Staff sign-in blocked for %s after %d failed attempts", ip, count)
        elif logging_in and response.status_code == 302:
            cache.delete(_key(ip))
        return response
