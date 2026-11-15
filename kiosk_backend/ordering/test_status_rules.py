"""The order status rules, checked move by move, plus the pickup and menu paths that are easy to miss:
every allowed move works and is recorded, every other move changes nothing, and the lists other code
relies on (OPEN, PAID_FOR) agree with the moves."""
from itertools import product
from unittest import mock

from django.core.cache import cache
from django.db.models import ProtectedError

from . import pickup
from .models import Order, OrderEvent
from .status import OPEN, PAID_FOR, TRANSITIONS, change_status
from .tests import OrderingTestBase

S = Order.Status


class TransitionTableTests(OrderingTestBase):
    def setUp(self):
        super().setUp()
        self.tea_stock.current_stock = 100_000  # enough for one order per move
        self.tea_stock.save()

    def new_order(self, status):
        res = self.order((self.green_tea, 0))
        self.assertEqual(res.status_code, 201, res.data)
        Order.objects.filter(pk=res.data['id']).update(status=status)
        return Order.objects.get(pk=res.data['id'])

    def test_every_move_from_every_status(self):
        for current, to in product(S.values, S.values):
            with self.subTest(current=current, to=to):
                order = self.new_order(current)
                events_before = order.events.count()
                moved = change_status(order, to, actor='test', reason='table')
                order_now = Order.objects.get(pk=order.pk)
                if to in TRANSITIONS[current]:
                    self.assertTrue(moved)
                    self.assertEqual(order_now.status, to)
                    self.assertEqual(order.status, to)  # the caller's copy follows
                    event = order.events.latest('id')
                    self.assertEqual((event.from_status, event.to_status, event.actor, event.reason),
                                     (current, to, 'test', 'table'))
                else:
                    self.assertFalse(moved)
                    self.assertEqual(order_now.status, current)
                    self.assertEqual(order.events.count(), events_before)

    def test_extra_fields_are_set_only_when_the_move_happens(self):
        order = self.new_order(S.READY)
        self.assertFalse(change_status(order, S.PAID, actor='test', pickup_pin='111111'))
        self.assertNotEqual(Order.objects.get(pk=order.pk).pickup_pin, '111111')
        self.assertTrue(change_status(order, S.COLLECTED, actor='test', pickup_pin='111111'))
        self.assertEqual(Order.objects.get(pk=order.pk).pickup_pin, '111111')

    def test_orders_with_history_cannot_be_deleted(self):
        # the audit trail must survive: deleting an order is refused, not cascaded
        order = self.new_order(S.PENDING)
        with self.assertRaises(ProtectedError):
            order.delete()
        self.assertTrue(OrderEvent.objects.filter(order_id=order.pk).exists())

    def test_unknown_order_cannot_move(self):
        self.assertFalse(change_status(Order(pk=987654), S.PAID, actor='test'))
        self.assertFalse(OrderEvent.objects.filter(order_id=987654).exists())

    def test_long_actor_and_reason_are_cut_to_fit(self):
        order = self.new_order(S.PENDING)
        self.assertTrue(change_status(order, S.CANCELLED, actor='a' * 300, reason='r' * 500))
        event = order.events.latest('id')
        self.assertEqual((len(event.actor), len(event.reason)), (100, 200))


class StatusListTests(OrderingTestBase):
    """Other code (pickup PINs, dashboard, payment checks) trusts these lists, so they must match the moves."""

    def test_every_status_has_its_moves_listed(self):
        self.assertEqual(set(TRANSITIONS), set(S.values))
        for targets in TRANSITIONS.values():
            self.assertLessEqual(targets, set(S.values))

    def test_every_status_can_be_reached_from_a_new_order(self):
        seen, todo = {S.PENDING}, [S.PENDING]
        while todo:
            for nxt in TRANSITIONS[todo.pop()]:
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        self.assertEqual(seen, set(S.values))

    def test_open_orders_are_exactly_the_ones_not_finished(self):
        # finished: handed over, cancelled, or being refunded. A cancelled order can still be paid
        # late, which pickup handles by reserving its PIN for a day (see assign_pickup_codes).
        self.assertEqual(set(OPEN), set(S.values) - {S.COLLECTED, S.CANCELLED, S.REFUND_NEEDED})

    def test_paid_for_is_everything_reachable_only_by_paying(self):
        self.assertEqual(set(PAID_FOR), set(S.values) - {S.PENDING, S.CANCELLED, S.REFUND_NEEDED})
        for status in PAID_FOR:
            # no way back to unpaid once money was taken
            self.assertFalse(TRANSITIONS[status] & {S.PENDING, S.CANCELLED})

    def test_finished_statuses_go_nowhere(self):
        for status in (S.COLLECTED, S.REFUND_NEEDED):
            self.assertEqual(TRANSITIONS[status], set())

    def test_pickup_has_a_message_for_every_status_but_ready(self):
        self.assertEqual(set(pickup.NOT_READY), set(S.values) - {S.READY})


class PickupEdgeTests(OrderingTestBase):
    def setUp(self):
        super().setUp()
        cache.clear()  # the pickup rate limit counts attempts in the cache

    def place(self):
        res = self.order((self.green_tea, 0))
        self.assertEqual(res.status_code, 201, res.data)
        return Order.objects.get(pk=res.data['id'])

    def test_blank_code(self):
        for code in ('', '   ', None):
            with self.subTest(code=code), self.assertRaises(pickup.PickupError) as caught:
                pickup.collect(self.shop.pk, code)
            self.assertEqual((caught.exception.status, caught.exception.reason), (404, 'not_found'))

    def test_spaces_around_a_pin_are_ignored(self):
        order = self.place()
        Order.objects.filter(pk=order.pk).update(status=S.READY)
        self.assertEqual(pickup.collect(self.shop.pk, f"  {order.pickup_pin} \n").pk, order.pk)

    def test_open_order_wins_over_an_old_one_with_the_same_pin(self):
        old = self.place()
        Order.objects.filter(pk=old.pk).update(status=S.COLLECTED)
        new = self.place()
        Order.objects.filter(pk=new.pk).update(status=S.READY, pickup_pin=old.pickup_pin)
        self.assertEqual(pickup.collect(self.shop.pk, old.pickup_pin).pk, new.pk)

    def test_second_scan_of_the_same_drink_is_refused(self):
        order = self.place()
        Order.objects.filter(pk=order.pk).update(status=S.READY)
        pickup.collect(self.shop.pk, order.pickup_pin)
        with self.assertRaises(pickup.PickupError) as caught:
            pickup.collect(self.shop.pk, order.pickup_pin)
        self.assertEqual(caught.exception.reason, 'already_collected')
        self.assertEqual(order.events.filter(to_status=S.COLLECTED).count(), 1)

    def test_scan_that_loses_a_race_is_refused(self):
        # both scans saw READY; the other one changed the order first
        order = self.place()
        Order.objects.filter(pk=order.pk).update(status=S.READY)
        with mock.patch.object(pickup, 'change_status', return_value=False), \
                self.assertRaises(pickup.PickupError) as caught:
            pickup.collect(self.shop.pk, order.pickup_pin)
        self.assertEqual((caught.exception.status, caught.exception.reason), (409, 'already_collected'))

    def test_no_free_pin_left_is_an_error_not_a_duplicate(self):
        order = self.place()
        with mock.patch.object(pickup.secrets, 'randbelow', return_value=int(order.pickup_pin)), \
                self.assertRaises(RuntimeError):
            self.place()


class MenuErrorTests(OrderingTestBase):
    """An unexpected error must reach the logs, not the customer's screen."""

    def test_menu_hides_internal_errors(self):
        with mock.patch('ordering.views.inventory_check', side_effect=RuntimeError('db password is hunter2')), \
                self.assertLogs('ordering.views', 'ERROR'):
            res = self.client.get('/ordering/drinks/', {'shop_id': self.shop.pk})
        self.assertEqual(res.status_code, 500)
        self.assertNotIn('hunter2', str(res.data))

    def test_cart_check_hides_internal_errors(self):
        with mock.patch('ordering.views.check_cart_fulfillment', side_effect=RuntimeError('secret')), \
                self.assertLogs('ordering.views', 'ERROR'):
            res = self.client.get('/ordering/check-order/', {'shop_id': self.shop.pk, 'cart': [self.green_tea.pk]})
        self.assertEqual(res.status_code, 500)
        self.assertNotIn('secret', str(res.data))

    def test_unknown_drink_or_too_many_is_refused(self):
        too_many = [self.green_tea.pk] * 21
        for path in ('/ordering/check-order/', '/ordering/drinks/'):
            for cart in ([99999], too_many):
                with self.subTest(path=path, cart=len(cart)):
                    res = self.client.get(path, {'shop_id': self.shop.pk, 'cart': cart})
                    self.assertEqual(res.status_code, 400)
