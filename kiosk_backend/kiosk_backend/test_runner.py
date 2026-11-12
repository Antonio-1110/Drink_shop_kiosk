"""Test runner: the whole suite places far more orders a minute than the order rate limit allows
(they all come from 127.0.0.1), so the limit is lifted while tests run. The test for the limit
itself puts it back (ordering.tests.OrderLimitTests)."""
from django.test.runner import DiscoverRunner
from rest_framework.throttling import ScopedRateThrottle

UNLIMITED = '100000/min'


class Runner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        ScopedRateThrottle.THROTTLE_RATES = {**ScopedRateThrottle.THROTTLE_RATES, 'orders': UNLIMITED}
