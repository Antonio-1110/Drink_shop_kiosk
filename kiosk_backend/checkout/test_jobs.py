"""Background jobs: cancelling unpaid orders on a timer (#61) and the daily check that orders,
stock and payments add up (#62)."""
import io
from datetime import datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from operation.models import StockMovement
from ordering.management.commands.run_jobs import Jobs
from ordering.models import Order, OrderEvent
from . import audit, services
from .models import StockHold
from .tests import CheckoutTestBase

S = Order.Status


class ExpireJobTests(CheckoutTestBase):
    def test_job_cancels_an_unpaid_order_with_no_other_traffic(self):
        start = self.stock()
        order, _ = self.place(self.milk_tea)
        self.rewind(order, 5)  # its time to pay has run out, and nobody has used the kiosk since
        out = io.StringIO()
        call_command('expire_orders', stdout=out)
        order.refresh_from_db()
        self.assertEqual(order.status, S.CANCELLED)
        event = order.events.last()
        self.assertEqual((event.from_status, event.to_status, event.actor), ('PENDING', 'CANCELLED', 'system'))
        self.assertEqual(self.stock(), start)
        self.assertEqual(out.getvalue().strip(), "Cancelled 1 unpaid order(s).")

    def test_orders_still_in_time_are_left_alone(self):
        order, _ = self.place(self.milk_tea)
        call_command('expire_orders', stdout=io.StringIO())
        self.assertEqual(self.status(order), S.PENDING)


@override_settings(EXPIRE_ORDERS_EVERY_SECONDS=60, CHECK_ORDERS_AT='04:00', TIME_ZONE='Asia/Singapore')
class SchedulerTests(CheckoutTestBase):
    def at(self, hour, minute=0, second=0, day=3):
        return timezone.make_aware(datetime(2026, 10, day, hour, minute, second))

    def test_expires_every_minute_and_checks_daily(self):
        with mock.patch.object(Jobs, 'run') as run:
            jobs = Jobs(self.at(3, 58))
            self.assertEqual(jobs.run_due(self.at(3, 58)), ['expire_orders'])
            self.assertEqual(jobs.run_due(self.at(3, 58, 30)), [])
            self.assertEqual(jobs.run_due(self.at(3, 59)), ['expire_orders'])
            self.assertEqual(jobs.run_due(self.at(4, 0)), ['expire_orders', 'check_orders'])
            self.assertEqual(jobs.run_due(self.at(4, 1)), ['expire_orders'])
            self.assertEqual(jobs.next_check, self.at(4, day=4))
        run.assert_any_call('check_orders', '--email')

    def test_started_after_the_check_time_waits_for_tomorrow(self):
        self.assertEqual(Jobs(self.at(9)).next_check, self.at(4, day=4))

    def test_the_job_really_cancels_orders(self):
        order, _ = self.place(self.milk_tea)
        self.rewind(order, 5)
        Jobs(timezone.now()).run_due(timezone.now())
        self.assertEqual(self.status(order), S.CANCELLED)
        self.assertEqual(order.events.last().actor, 'system')

    def test_a_failing_job_doesnt_stop_the_loop(self):
        jobs = Jobs(self.at(4))
        with mock.patch('ordering.management.commands.run_jobs.call_command', side_effect=RuntimeError("db down")), \
                self.assertLogs('ordering.management.commands.run_jobs', 'ERROR'):
            self.assertEqual(jobs.run_due(self.at(4, 1)), ['expire_orders'])


class AuditTests(CheckoutTestBase):
    def problems(self):
        return {rule.title: rule.problems for rule in audit.check_orders()}

    def broken_ids(self, title_start):
        found = [ids for title, problems in self.problems().items() if title.startswith(title_start)
                 for ids, _ in problems]
        return sorted(i for ids in found for i in ids)

    def every_kind_of_order(self):
        # paid and collected, cancelled, paid late, waiting: all consistent
        collected, _ = self.place(self.green_tea)
        services.confirm_payment(collected, 'fake', collected.revenue, provider_ref='a')
        with override_settings(MACHINE_SIMULATOR=True):
            self.client.post("/ordering/pickup/", {'shop': self.shop.pk, 'code': collected.pickup_pin}, format='json')
        cancelled, _ = self.place(self.green_tea)
        services.cancel_order(cancelled)
        late, _ = self.place(self.green_tea)
        services.cancel_order(late)
        services.confirm_payment(late, 'fake', late.revenue, provider_ref='b')
        waiting, _ = self.place(self.green_tea)
        return collected, cancelled, late, waiting

    def test_consistent_books_report_nothing(self):
        collected, *_ = self.every_kind_of_order()
        self.assertEqual(self.status(collected), S.COLLECTED)
        self.assertEqual(self.problems(), {})
        out = io.StringIO()
        call_command('check_orders', '--email', stdout=out)
        self.assertIn("Nothing to report", out.getvalue())
        self.assertEqual(mail.outbox, [])

    def test_held_stock_on_a_cancelled_order(self):
        _, cancelled, _, _ = self.every_kind_of_order()
        StockHold.objects.filter(order=cancelled).update(status=StockHold.Status.HELD)
        self.assertEqual(self.broken_ids("Held stock"), [cancelled.pk])

    def test_paid_order_without_a_payment(self):
        collected, _, late, _ = self.every_kind_of_order()
        collected.payment_attempts.all().delete()
        self.assertEqual(self.broken_ids("Every paid order"), [collected.pk])

    def test_refund_needed_without_a_refund(self):
        collected, *_ = self.every_kind_of_order()
        Order.objects.filter(pk=collected.pk).update(status=S.REFUND_NEEDED)
        self.assertEqual(self.broken_ids("Every paid order"), [collected.pk])

    def test_history_not_ending_in_the_current_status(self):
        _, cancelled, _, waiting = self.every_kind_of_order()
        Order.objects.filter(pk=cancelled.pk).update(status=S.PAID)  # a manual database edit
        OrderEvent.objects.filter(order=waiting).delete()
        self.assertEqual(self.broken_ids("The status history"), [cancelled.pk, waiting.pk])
        text = audit.report(audit.check_orders())
        self.assertIn(f"Order {cancelled.pk} is PAID but its history ends at CANCELLED", text)
        self.assertIn(f"Order {waiting.pk} is PENDING but has no status history", text)

    def test_stock_movements_not_matching_holds(self):
        _, _, late, _ = self.every_kind_of_order()
        self.tea_stock.adjust_stock(Decimal('-5'), StockMovement.Reason.ORDER, order=late)
        self.assertEqual(self.broken_ids("Stock movements"), [late.pk])

    def test_open_orders_sharing_a_pin(self):
        collected, _, late, waiting = self.every_kind_of_order()
        Order.objects.filter(pk=waiting.pk).update(pickup_pin=late.pickup_pin)
        Order.objects.filter(pk=collected.pk).update(pickup_pin=late.pickup_pin)  # collected: not open
        self.assertEqual(self.broken_ids("No two open orders"), [late.pk, waiting.pk])

    @override_settings(STAFF_ALERT_EMAILS=['staff@example.com'])
    def test_problems_are_emailed_to_staff(self):
        _, cancelled, _, _ = self.every_kind_of_order()
        Order.objects.filter(pk=cancelled.pk).update(status=S.PAID)
        out = io.StringIO()
        call_command('check_orders', '--email', stdout=out)
        self.assertIn(f"Order {cancelled.pk}", out.getvalue())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['staff@example.com'])
        self.assertIn("problem(s) found", mail.outbox[0].subject)
        self.assertIn(f"Order {cancelled.pk}", mail.outbox[0].body)
        # without --email it only reports
        call_command('check_orders', stdout=io.StringIO())
        self.assertEqual(len(mail.outbox), 1)

    def test_says_so_when_nobody_can_be_emailed(self):
        _, cancelled, _, _ = self.every_kind_of_order()
        Order.objects.filter(pk=cancelled.pk).update(status=S.PAID)
        err = io.StringIO()
        call_command('check_orders', '--email', stdout=io.StringIO(), stderr=err)
        self.assertIn("STAFF_ALERT_EMAILS", err.getvalue())

    def test_old_and_new_problem_times(self):
        # rules look at every order, however old
        waiting = self.every_kind_of_order()[3]
        Order.objects.filter(pk=waiting.pk).update(time=timezone.now() - timedelta(days=400), status=S.CANCELLED)
        self.assertIn(waiting.pk, self.broken_ids("Held stock"))
