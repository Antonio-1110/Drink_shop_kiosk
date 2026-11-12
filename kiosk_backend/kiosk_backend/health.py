"""/healthz/ answers 200 when the web server is up and can reach the database, 503 when not.
Docker's health check, the hosting platform and uptime monitors call it. It needs no login and
says nothing about the shop.

It's a middleware at the top of the list, not a view, because health checks come from inside the
container or the platform's network: by plain HTTP and to an address that isn't in
DJANGO_ALLOWED_HOSTS. A view would answer them with an HTTPS redirect or a 400.
"""
from django.db import connection
from django.http import JsonResponse

PATH = '/healthz/'


def database_ok():
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:
        return False
    return True


class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path != PATH:
            return self.get_response(request)
        if not database_ok():
            return JsonResponse({'ok': False, 'database': 'unreachable'}, status=503)
        return JsonResponse({'ok': True})
