from unittest import mock

from django.test import TestCase, override_settings


class HealthCheckTests(TestCase):
    @override_settings(ALLOWED_HOSTS=['kiosk.example.com'], SECURE_SSL_REDIRECT=True)
    def test_answers_plain_http_to_any_host(self):
        # the container's own health check: http://localhost, not an allowed host
        response = self.client.get('/healthz/', HTTP_HOST='localhost:8000')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ok': True})

    def test_503_when_the_database_is_down(self):
        with mock.patch('kiosk_backend.health.database_ok', return_value=False):
            response = self.client.get('/healthz/')
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json()['ok'])

    @override_settings(ALLOWED_HOSTS=['kiosk.example.com'])
    def test_other_paths_still_check_the_host(self):
        self.assertEqual(self.client.get('/admin/', HTTP_HOST='evil.example').status_code, 400)
