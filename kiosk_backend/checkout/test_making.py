"""Making the drink after payment (#59): PAID -> PREPARING -> READY -> COLLECTED, failures, retries
and refunds, and the endpoint the machine reports them on."""
import io
from itertools import product

from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, override_settings

from operation.kiosk_auth import new_key
from operation.models import Kiosk, Shop
from ordering.admin import OrderAdmin
from ordering.models import Order, OrderEvent
from ordering.status import TRANSITIONS, change_status
from .models import PaymentAttempt
from .tests import CheckoutTestBase
from . import services

S = Order.Status


@override_settings(MACHINE_SIMULATOR=False)
class MakingTestBase(CheckoutTestBase):
    def setUp(self):
        super().setUp()
        self.kiosk = Kiosk.objects.create(shop=self.shop, machine_id='K-1')
        self.key = new_key(self.kiosk)

    def paid_order(self):
        order, _ = self.place(self.green_tea)
        services.confirm_payment(order, 'fake', order.revenue, provider_ref=f"tx-{order.pk}")
        order.refresh_from_db()
        return order

    def report(self, order, to, reason='', key=None):
        return self.client.post(f"/ordering/orders/{order.pk}/progress/", {'status': to, 'reason': reason},
                                format='json', HTTP_AUTHORIZATION=f"Kiosk {key or self.key}")

    def collect(self, order):
        return self.client.post("/ordering/pickup/", {'shop': self.shop.pk, 'code': order.pickup_pin}, format='json')

    def history(self, order):
        return [(e.from_status, e.to_status, e.actor) for e in order.events.all()]


class StatusRuleTests(MakingTestBase):
    def test_every_move_is_allowed_or_refused_as_listed(self):
        order, _ = self.place(self.green_tea)
        for frm, to in product(S.values, S.values):
            Order.objects.filter(pk=order.pk).update(status=frm)
            events = OrderEvent.objects.filter(order=order).count()
            moved = change_status(order, to, actor='test', reason='because')
            order.refresh_from_db()
            with self.subTest(frm=frm, to=to):
                if to in TRANSITIONS[frm]:
                    self.assertTrue(moved)
                    self.assertEqual(order.status, to)
                    event = order.events.last()
                    self.assertEqual((event.from_status, event.to_status, event.actor, event.reason),
                                     (frm, to, 'test', 'because'))
                else:
                    self.assertFalse(moved)
                    self.assertEqual(order.status, frm)
                    self.assertEqual(order.events.count(), events)

    def test_the_new_moves(self):
        self.assertEqual(TRANSITIONS[S.PAID], {S.PREPARING})
        self.assertEqual(TRANSITIONS[S.PREPARING], {S.READY, S.FAILED})
        self.assertEqual(TRANSITIONS[S.READY], {S.COLLECTED})
        self.assertEqual(TRANSITIONS[S.FAILED], {S.PREPARING, S.REFUND_NEEDED})


class MachineJourneyTests(MakingTestBase):
    def test_made_then_collected(self):
        order = self.paid_order()
        for step in ('PREPARING', 'READY'):
            res = self.report(order, step)
            self.assertEqual(res.status_code, 200, res.data)
            self.assertEqual(res.data, {'id': order.pk, 'status': step})
        self.assertEqual(self.collect(order).status_code, 200)
        order.refresh_from_db()
        self.assertEqual(self.history(order)[2:], [
            ('PAID', 'PREPARING', 'machine:K-1'), ('PREPARING', 'READY', 'machine:K-1'), ('READY', 'COLLECTED', 'kiosk')])

    def test_scanning_early_says_still_being_made(self):
        order = self.paid_order()
        for status in ('PAID', 'PREPARING'):
            if status == 'PREPARING':
                self.report(order, 'PREPARING')
            res = self.collect(order)
            self.assertEqual((res.status_code, res.data['reason']), (409, 'preparing'))
            self.assertIn("still being made", res.data['error'])
            order.refresh_from_db()
            self.assertEqual(order.status, status)

    def test_failed_then_retried(self):
        order = self.paid_order()
        self.report(order, 'PREPARING')
        res = self.report(order, 'FAILED', reason="Cup jammed")
        self.assertEqual(res.data['status'], 'FAILED')
        self.assertEqual(order.events.last().reason, "Cup jammed")
        self.assertEqual(self.collect(order).data['reason'], 'failed')
        self.report(order, 'PREPARING')
        self.report(order, 'READY')
        self.assertEqual(self.collect(order).status_code, 200)

    def test_failed_then_refunded_by_staff(self):
        order = self.paid_order()
        self.report(order, 'PREPARING')
        self.report(order, 'FAILED', reason="Milk ran out mid-pour")
        staff = get_user_model().objects.create_superuser('sam', 'sam@example.com', 'pw')
        admin = OrderAdmin(Order, site)
        admin.message_user = lambda *a, **k: None
        order.refresh_from_db()
        self.assertEqual(admin.problem(order), "Milk ran out mid-pour")
        request = RequestFactory().post('/admin/')
        request.user = staff
        admin.refund_failed(request, Order.objects.filter(pk=order.pk))
        order.refresh_from_db()
        self.assertEqual(self.history(order)[-1], ('FAILED', 'REFUND_NEEDED', 'staff:sam'))
        self.assertEqual(admin.problem(order), "Milk ran out mid-pour")
        attempt = order.payment_attempts.get()
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUNDED)
        self.assertEqual(self.fake.refunded, [attempt.pk])
        self.assertEqual(self.collect(order).data['reason'], 'refunding')
        # a second refund does nothing
        self.assertFalse(services.refund_failed_order(order))

    def test_refund_left_to_staff_when_the_method_cant(self):
        self.fake.refunds = False
        order = self.paid_order()
        self.report(order, 'PREPARING')
        self.report(order, 'FAILED')
        self.assertTrue(services.refund_failed_order(order, reason="Jam"))
        attempt = order.payment_attempts.get()
        self.assertEqual((attempt.status, attempt.note), (PaymentAttempt.Status.REFUND_NEEDED, "Drink couldn't be made. Jam"))

    def test_only_failed_orders_are_refunded(self):
        order = self.paid_order()
        self.assertFalse(services.refund_failed_order(order))
        self.assertEqual(self.status(order), S.PAID)

    def test_simulator_stands_in_for_the_machine(self):
        order = self.paid_order()
        with override_settings(MACHINE_SIMULATOR=True):
            res = self.collect(order)
        self.assertEqual(res.status_code, 200, res.data)
        order.refresh_from_db()
        self.assertEqual([h[1:] for h in self.history(order)[2:]], [
            ('PREPARING', 'simulator'), ('READY', 'simulator'), ('COLLECTED', 'kiosk')])


class ProgressEndpointTests(MakingTestBase):
    def test_needs_a_kiosk_key(self):
        order = self.paid_order()
        url = f"/ordering/orders/{order.pk}/progress/"
        self.assertEqual(self.client.post(url, {'status': 'PREPARING'}, format='json').status_code, 401)
        self.assertEqual(self.report(order, 'PREPARING', key='not-a-key').status_code, 401)
        self.assertEqual(self.client.post(url, {'status': 'PREPARING'}, format='json',
                                          HTTP_AUTHORIZATION="Kiosk").status_code, 401)
        # a staff login is not a machine
        staff = get_user_model().objects.create_superuser('sam', 'sam@example.com', 'pw')
        self.client.force_login(staff)
        self.assertIn(self.client.post(url, {'status': 'PREPARING'}, format='json').status_code, (401, 403))
        self.assertEqual(self.status(order), S.PAID)

    def test_only_its_own_shops_orders(self):
        order = self.paid_order()
        other = Kiosk.objects.create(shop=Shop.objects.create(name="Other", address="2 Road"), machine_id='K-2')
        res = self.report(order, 'PREPARING', key=new_key(other))
        self.assertEqual(res.status_code, 404)
        self.assertEqual(self.status(order), S.PAID)

    def test_refuses_unknown_statuses_and_moves_out_of_order(self):
        order = self.paid_order()
        for status in ('COLLECTED', 'REFUND_NEEDED', 'PAID', 'nonsense', '', ['READY']):
            self.assertEqual(self.report(order, status).status_code, 400, status)
        res = self.report(order, 'READY')  # not started yet
        self.assertEqual((res.status_code, res.data['status']), (409, 'PAID'))
        unpaid, _ = self.place(self.green_tea)
        self.assertEqual(self.report(unpaid, 'PREPARING').status_code, 409)
        self.assertEqual(self.status(unpaid), S.PENDING)

    def test_repeated_report_is_harmless(self):
        order = self.paid_order()
        self.report(order, 'PREPARING')
        res = self.report(order, 'PREPARING')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(order.events.filter(to_status=S.PREPARING).count(), 1)

    def test_new_key_replaces_the_old_one(self):
        order = self.paid_order()
        out = io.StringIO()
        call_command('kiosk_key', 'K-1', stdout=out)
        key = out.getvalue().split()[-1]
        self.assertEqual(self.report(order, 'PREPARING').status_code, 401)  # the old key
        self.assertEqual(self.report(order, 'PREPARING', key=key).status_code, 200)
        self.kiosk.refresh_from_db()
        self.assertNotIn(key, self.kiosk.api_key_hash)
