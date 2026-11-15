"""Running without staff: automatic refunds, stuck drinks, pausing a failing machine, refund retries
and staff alerts (operation/recovery.py, operation/alerts.py)."""
import io
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from checkout import services
from checkout.audit import check_orders
from checkout.models import PaymentAttempt, StockHold
from checkout.test_making import MakingTestBase
from ordering.models import Order
from .alerts import sync_alerts
from .availability import closed_reason
from .models import Alert, Inventory, Kiosk, StockMovement
from .recovery import recover

S = Order.Status
A = Alert.Kind


def later(minutes):
    return timezone.now() + timedelta(minutes=minutes)


def run_at(minutes):
    """Runs the recovery jobs as if `minutes` had passed (order history is stamped with that time too)."""
    at = later(minutes)
    with mock.patch('django.utils.timezone.now', return_value=at):
        return recover()


class RecoveryTestBase(MakingTestBase):
    def take(self, order):
        """The machine takes the order (PAID -> PREPARING) through the real endpoint."""
        res = self.client.post("/operation/machine/next-order/", HTTP_AUTHORIZATION=f"Kiosk {self.key}")
        self.assertEqual((res.status_code, res.data['id']), (200, order.pk))

    def check_in(self, **body):
        return self.client.post("/operation/machine/heartbeat/", body, format='json',
                                HTTP_AUTHORIZATION=f"Kiosk {self.key}")

    def attempts(self, order):
        return list(order.payment_attempts.values_list('status', flat=True))

    def assertBooksAddUp(self):
        self.assertEqual(check_orders(), [])


@override_settings(AUTO_REFUND_FAILED_AFTER_MINUTES=3)
class FailedDrinkRefundTests(RecoveryTestBase):
    def test_failed_drink_is_refunded_after_the_wait(self):
        order = self.paid_order()
        self.take(order)
        with self.assertLogs('ordering.views', 'ERROR'):
            self.report(order, 'FAILED', 'sealer jam')
        run_at(1)
        self.assertEqual(self.status(order), S.FAILED)  # the machine may still retry it
        run_at(4)
        self.assertEqual(self.status(order), S.REFUND_NEEDED)
        self.assertEqual(self.attempts(order), [PaymentAttempt.Status.REFUNDED])
        self.assertEqual(order.events.last().actor, 'system')
        self.assertBooksAddUp()

    def test_a_retried_drink_is_left_alone(self):
        order = self.paid_order()
        self.take(order)
        with self.assertLogs('ordering.views', 'ERROR'):
            self.report(order, 'FAILED')
        self.report(order, 'PREPARING')
        run_at(4)
        self.assertEqual(self.status(order), S.PREPARING)


@override_settings(STUCK_PREPARING_MINUTES=10, MINUTES_PER_DRINK=2, SILENT_MACHINE_WAIT_MINUTES=120,
                   AUTO_REFUND_FAILED_AFTER_MINUTES=3)
class StuckDrinkTests(RecoveryTestBase):
    def test_drink_the_machine_forgot_is_failed_then_refunded(self):
        order = self.paid_order()
        self.take(order)
        Kiosk.objects.filter(pk=self.kiosk.pk).update(last_heartbeat=later(13))  # still checking in
        run_at(11)
        self.assertEqual(self.status(order), S.PREPARING)  # 10 min + 2 for its one drink
        with self.assertLogs('operation.recovery', 'ERROR'):
            run_at(13)
        self.assertEqual(self.status(order), S.FAILED)
        self.assertIn("stopped reporting", order.events.last().reason)
        run_at(14)
        self.assertEqual(self.status(order), S.FAILED)
        run_at(17)
        self.assertEqual(self.status(order), S.REFUND_NEEDED)
        self.assertBooksAddUp()

    def test_silent_machine_gets_longer_to_come_back(self):
        order = self.paid_order()
        self.take(order)
        run_at(60)  # machine silent since the start: it may come back and finish
        self.assertEqual(self.status(order), S.PREPARING)
        with self.assertLogs('operation.recovery', 'ERROR'):
            run_at(133)
        self.assertEqual(self.status(order), S.FAILED)

    def test_a_late_ready_for_a_refunded_drink_is_refused(self):
        order = self.paid_order()
        self.take(order)
        with self.assertLogs('operation.recovery', 'ERROR'):
            run_at(133)
        run_at(140)
        self.assertEqual(self.report(order, 'READY').status_code, 409)
        self.assertEqual(self.status(order), S.REFUND_NEEDED)


@override_settings(PAID_WAIT_MAX_MINUTES=30)
class WaitingBehindClosedShopTests(RecoveryTestBase):
    def stock(self):
        return {i.pk: i.current_stock for i in Inventory.objects.filter(shop=self.shop)}

    def test_paid_order_refunded_when_shop_cant_make_it_in_time(self):
        before = self.stock()
        order = self.paid_order()
        self.check_in(modules={'cups': 'empty'})
        self.assertIsNotNone(closed_reason(self.shop))
        run_at(20)
        self.assertEqual(self.status(order), S.PAID)
        run_at(31)
        self.assertEqual(self.status(order), S.REFUND_NEEDED)
        self.assertEqual(self.attempts(order), [PaymentAttempt.Status.REFUNDED])
        self.assertIn("couldn't make drinks", order.events.last().reason)
        # never made, so its ingredients are back on sale
        self.assertEqual(self.stock(), before)
        self.assertFalse(order.stock_holds.exclude(status=StockHold.Status.RELEASED).exists())
        self.assertBooksAddUp()

    def test_open_shop_works_through_its_queue(self):
        order = self.paid_order()
        Kiosk.objects.filter(pk=self.kiosk.pk).update(last_heartbeat=later(31))
        run_at(31)
        self.assertEqual(self.status(order), S.PAID)

    def test_machine_taking_it_first_wins(self):
        order = self.paid_order()
        self.take(order)
        self.assertFalse(services.refund_unmade_order(order))
        self.assertEqual(self.status(order), S.PREPARING)


@override_settings(MACHINE_FAILURES_TO_PAUSE=3)
class FailingMachineTests(RecoveryTestBase):
    def setUp(self):
        super().setUp()
        for inv in Inventory.objects.filter(shop=self.shop):
            inv.adjust_stock(10000, StockMovement.Reason.RESTOCK)

    def fail(self):
        order = self.paid_order()
        self.take(order)
        with self.assertLogs('ordering.views', 'ERROR'):
            self.report(order, 'FAILED', 'jam')
        return order

    def test_three_failures_in_a_row_stop_sales_until_maintenance(self):
        for _ in range(3):
            self.fail()
        self.kiosk.refresh_from_db()
        self.assertEqual(self.kiosk.consecutive_failures, 3)
        self.assertEqual(closed_reason(self.shop)[1], 'machine_not_ready')
        res = self.order((self.green_tea, 0))
        self.assertEqual((res.status_code, res.data['reason']), (503, 'machine_not_ready'))
        # an order paid just before the pause waits instead of being failed too
        Kiosk.objects.filter(pk=self.kiosk.pk).update(consecutive_failures=0)
        waiting = self.paid_order()
        Kiosk.objects.filter(pk=self.kiosk.pk).update(consecutive_failures=3)
        res = self.client.post("/operation/machine/next-order/", HTTP_AUTHORIZATION=f"Kiosk {self.key}")
        self.assertEqual(res.status_code, 204)
        self.assertEqual(self.status(waiting), S.PAID)
        # a technician puts it in maintenance, fixes it, puts it back
        self.check_in(status='MAINTENANCE')
        self.check_in(status='ONLINE')
        self.assertIsNone(closed_reason(self.shop))
        self.take(waiting)

    def test_a_made_drink_resets_the_count(self):
        self.fail()
        self.fail()
        order = self.paid_order()
        self.take(order)
        self.report(order, 'READY')
        self.kiosk.refresh_from_db()
        self.assertEqual(self.kiosk.consecutive_failures, 0)

    def test_repeated_failed_report_counts_once(self):
        order = self.fail()
        self.report(order, 'FAILED', 'jam')
        self.kiosk.refresh_from_db()
        self.assertEqual(self.kiosk.consecutive_failures, 1)

    def test_dairy_lock_refusals_dont_count(self):
        Kiosk.objects.filter(pk=self.kiosk.pk).update(sfa_locked=True)
        with mock.patch('operation.machine.locked_ingredient_ids', return_value=set(
                Inventory.objects.filter(shop=self.shop).values_list('ingredient_id', flat=True))):
            order = self.paid_order()
            with self.assertLogs('operation.machine', 'ERROR'):
                self.client.post("/operation/machine/next-order/", HTTP_AUTHORIZATION=f"Kiosk {self.key}")
        self.assertEqual(self.status(order), S.FAILED)
        self.kiosk.refresh_from_db()
        self.assertEqual(self.kiosk.consecutive_failures, 0)


@override_settings(REFUND_RETRY_MINUTES=15)
class RefundRetryTests(RecoveryTestBase):
    def test_refund_turned_down_is_tried_again(self):
        order = self.paid_order()
        self.fake.refunds = False
        with self.assertLogs('checkout.services', 'ERROR'):
            services.confirm_payment(order, 'fake', order.revenue, provider_ref='second-payment')
        attempt = order.payment_attempts.get(provider_ref='second-payment')
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUND_NEEDED)
        run_at(5)
        self.assertEqual(len(self.fake.refunded), 1)  # too soon to retry
        self.fake.refunds = True
        run_at(16)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUNDED)


@override_settings(STAFF_ALERT_EMAILS=['ops@example.com'], MACHINE_OFFLINE_ALERT_MINUTES=10, ALERT_REMIND_HOURS=6,
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AlertTests(RecoveryTestBase):
    def open_kinds(self):
        return set(Alert.objects.filter(resolved_at=None).values_list('kind', flat=True))

    def sync(self, minutes=0):
        with mock.patch('operation.alerts.logger'):  # each new alert is also logged as an error
            return sync_alerts(later(minutes))

    def test_quiet_shop_has_no_alerts(self):
        self.sync()
        self.assertEqual(self.open_kinds(), set())
        self.assertEqual(mail.outbox, [])

    def test_offline_machine_alert_opens_once_reminds_and_clears(self):
        self.sync(11)
        self.assertEqual(self.open_kinds(), {A.MACHINE_OFFLINE})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Machine stopped checking in", mail.outbox[0].subject)
        self.assertIn("K-1", mail.outbox[0].body)
        self.sync(12)  # still open: no second email yet
        self.assertEqual(len(mail.outbox), 1)
        self.sync(11 + 6 * 60)  # reminder
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("Still open", mail.outbox[1].body)
        Kiosk.objects.filter(pk=self.kiosk.pk).update(last_heartbeat=later(11 + 6 * 60))
        self.sync(11 + 6 * 60)
        self.assertEqual(self.open_kinds(), set())
        self.assertEqual(mail.outbox[-1].subject, "Kiosk: problems cleared")
        self.assertEqual(Alert.objects.count(), 1)

    def test_machine_switched_off_for_maintenance_is_not_an_alert(self):
        self.check_in(status='MAINTENANCE')
        self.sync(600)
        self.assertNotIn(A.MACHINE_OFFLINE, self.open_kinds())

    def test_each_problem_opens_its_own_alert_in_one_email(self):
        self.check_in(modules={'cups': 'empty'})
        Kiosk.objects.filter(pk=self.kiosk.pk).update(sfa_locked=True, sfa_lock_reason="Fresh milk at 9 C",
                                                      consecutive_failures=5)
        inv = Inventory.objects.filter(shop=self.shop).select_related('ingredient').first()
        inv.ingredient.reorder_threshold = inv.current_stock + 1
        inv.ingredient.save()
        self.sync()
        self.assertEqual(self.open_kinds(), {A.MACHINE_NOT_READY, A.MACHINE_FAILING, A.DAIRY_LOCK, A.LOW_STOCK})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("and 3 more", mail.outbox[0].subject)
        for text in ("cups empty", "Fresh milk at 9 C", inv.ingredient.name, "5 drinks in a row"):
            self.assertIn(text, mail.outbox[0].body)

    def test_refunds_by_hand(self):
        order = self.paid_order()
        self.fake.refunds = False
        with self.assertLogs('checkout.services', 'ERROR'):
            services.confirm_payment(order, 'fake', order.revenue, provider_ref='second-payment')
        self.sync()
        alert = Alert.objects.get(kind=A.REFUND_BY_HAND)
        self.assertIn(f"orders {order.pk}", alert.message)
        PaymentAttempt.objects.filter(status=PaymentAttempt.Status.REFUND_NEEDED).update(
            status=PaymentAttempt.Status.REFUNDED)  # staff refunded it and marked it in the admin
        self.sync()
        alert.refresh_from_db()
        self.assertIsNotNone(alert.resolved_at)

    @override_settings(STAFF_ALERT_EMAILS=[])
    def test_alerts_kept_even_with_nobody_to_email(self):
        self.sync(11)
        alert = Alert.objects.get()
        self.assertIsNone(alert.notified_at)

    def test_email_failure_doesnt_stop_the_job(self):
        with mock.patch('operation.alerts.send_mail', side_effect=OSError("smtp down")), \
                self.assertLogs('operation.alerts', 'ERROR') as logs:
            sync_alerts(later(11))
        self.assertEqual(self.open_kinds(), {A.MACHINE_OFFLINE})
        self.assertIsNone(Alert.objects.get().notified_at)
        self.assertIn("Couldn't email staff", "\n".join(logs.output))


class CommandTests(RecoveryTestBase):
    def test_run_jobs_runs_recovery(self):
        from ordering.management.commands.run_jobs import Jobs
        with mock.patch.object(Jobs, 'run') as run:
            Jobs(timezone.now()).run_due(timezone.now())
        self.assertIn(mock.call('recover_shops', verbosity=0), run.call_args_list)

    def test_recover_shops_command(self):
        out = io.StringIO()
        call_command('recover_shops', stdout=out)
        self.assertIn("failed drink(s) refunded", out.getvalue())
