import io
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from checkout.models import PaymentAttempt
from checkout.services import cancel_order, confirm_payment
from operation.models import Kiosk, Shop
from ordering.models import Order, OrderItem
from ordering.status import change_status
from ordering.tests import OrderingTestBase

from . import data


class DashboardNumbersTests(OrderingTestBase):
    def place(self, drink=None, size=OrderItem.Size.SMALL):
        res = self.order((drink or self.green_tea, size))
        self.assertEqual(res.status_code, 201, res.data)
        return Order.objects.get(pk=res.data["id"])

    def test_counts_orders_by_where_they_ended_up(self):
        collected = self.place(self.milk_tea)
        confirm_payment(collected, 'paynow', collected.revenue, provider_ref='a')
        change_status(collected, Order.Status.COLLECTED, actor='kiosk')
        paid = self.place()
        confirm_payment(paid, 'paynow', paid.revenue, provider_ref='b')
        cancel_order(self.place(), reason="Cancelled by the customer.", actor='customer')
        cancel_order(self.place(), reason="Cancelled by the kiosk idle timeout.", actor='timeout')
        self.place()  # still waiting

        n = data.build(days=7)
        today = n['daily'][-1]
        self.assertEqual((today['COLLECTED'], today['PAID'], today['CANCELLED'], today['PENDING']), (1, 1, 2, 1))
        self.assertEqual(today['revenue'], Decimal('6.00'))  # 3.50 + 2.50
        self.assertEqual(len(n['daily']), 7)
        tiles = n['tiles']
        self.assertEqual((tiles['placed'], tiles['sold'], tiles['cups']), (5, 2, 2))
        self.assertEqual(tiles['revenue'], Decimal('6.00'))
        self.assertEqual(tiles['average'], Decimal('3.00'))
        self.assertEqual(tiles['cancel_rate'], 40)
        self.assertEqual((tiles['waiting_payment'], tiles['waiting_pickup']), (1, 1))
        self.assertIsNotNone(tiles['minutes_to_pay'])
        self.assertIsNotNone(tiles['minutes_to_collect'])
        self.assertEqual(n['drinks'], [{'name': 'Green Tea', 'cups': 1}, {'name': 'Milk Tea', 'cups': 1}])
        self.assertEqual({c['who']: c['orders'] for c in n['cancellations']},
                         {'Customer': 1, 'Kiosk idle timeout': 1})
        self.assertEqual(sum(n['hourly']), 5)

    def test_stock_days_left_count_only_what_orders_kept(self):
        self.place(self.milk_tea)  # 100 mL milk, 200 tea
        cancel_order(self.place(), actor='customer')  # 300 tea, given back
        rows = {r['ingredient']: r for r in data.build(days=7)['stock']}
        self.assertEqual(rows['Milk']['per_day'], Decimal('14.3'))  # 100 / 7
        self.assertEqual(rows['Tea']['per_day'], Decimal('28.6'))  # 200 / 7
        self.assertEqual(rows['Milk']['days_left'], Decimal('3.5'))  # 50 left / 14.29

    def test_flags_orders_that_need_attention(self):
        stuck = self.place()
        late = self.place()
        cancel_order(late, actor='customer')
        self.milk_stock.adjust_stock(-self.milk_stock.current_stock, 'ADJUST')
        self.tea_stock.adjust_stock(-self.tea_stock.current_stock, 'ADJUST')
        confirm_payment(late, 'paynow', late.revenue, provider_ref='late')  # no stock left: refund
        # backdated after placing, since placing an order expires unpaid ones that ran out of time
        Order.objects.filter(pk=stuck.pk).update(time=timezone.now() - timedelta(hours=1))
        uncollected = Order.objects.create(shop=self.shop, revenue=Decimal('2.50'), status=Order.Status.PAID)
        attention = data.build(days=7)['attention']
        self.assertEqual([p['order'] for p in attention['pending']], [stuck])
        self.assertEqual([r['order'] for r in attention['refunds']], [late])
        self.assertEqual(attention['uncollected'], [])  # just paid
        Order.objects.filter(pk=uncollected.pk).update(time=timezone.now() - timedelta(hours=3))
        self.assertEqual([u['order'] for u in data.build(days=7)['attention']['uncollected']], [uncollected])

    def test_locked_and_silent_kiosks_need_attention(self):
        Kiosk.objects.create(shop=self.shop, machine_id='K1', sfa_locked=True, sfa_lock_reason='Milk at 6 C')
        other = Shop.objects.create(name="Other", address="2 Road")
        Kiosk.objects.create(shop=other, machine_id='K2', last_heartbeat=timezone.now() - timedelta(hours=1))
        Kiosk.objects.create(shop=Shop.objects.create(name="New", address="3 Road"), machine_id='K3')
        self.assertEqual([k['kiosk'].machine_id for k in data.build()['attention']['kiosks']], ['K2', 'K1'])
        self.assertEqual([k['kiosk'].machine_id for k in data.build(shop=self.shop)['kiosks']], ['K1'])

    def test_shop_filter(self):
        self.place()
        other = Shop.objects.create(name="Other", address="2 Road")
        self.assertEqual(data.build(shop=other)['tiles']['placed'], 0)
        self.assertEqual(data.build(shop=self.shop)['tiles']['placed'], 1)

    def test_temperatures_are_hourly_averages(self):
        self.milk_stock.max_safe_temp_c = Decimal('4')
        self.milk_stock.save()
        now = timezone.now().replace(minute=30)
        self.milk_stock.record_temperature('3.0', recorded_at=now - timedelta(minutes=10))
        self.milk_stock.record_temperature('5.0', recorded_at=now - timedelta(minutes=5))
        [milk] = data.build()['temperatures']
        self.assertEqual(milk['points'][-1]['temp_c'], Decimal('4.0'))
        self.assertEqual(milk['out_of_range'], 1)
        self.assertEqual(milk['max_c'], Decimal('4.0'))


class DashboardPageTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user('staff', password='pw', is_staff=True)

    def test_needs_staff_login(self):
        res = self.client.get('/admin/dashboard/')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/admin/login/', res['Location'])
        get_user_model().objects.create_user('customer', password='pw')
        self.client.login(username='customer', password='pw')
        self.assertEqual(self.client.get('/admin/dashboard/').status_code, 302)

    def test_renders_empty_and_with_demo_history(self):
        self.client.login(username='staff', password='pw')
        res = self.client.get('/admin/dashboard/?days=7')
        self.assertContains(res, 'Orders per day')
        self.assertContains(res, 'id="dash-data"')
        call_command('seed_demo', stdout=io.StringIO())
        call_command('seed_demo_history', '--days', '3', stdout=io.StringIO())
        made = Order.objects.count()
        call_command('seed_demo_history', '--days', '3', stdout=io.StringIO())  # replaces, doesn't add
        self.assertAlmostEqual(Order.objects.count(), made, delta=made // 2)
        shop = Shop.objects.get(name__startswith='Demo Kiosk')
        res = self.client.get(f'/admin/dashboard/?shop={shop.pk}&days=90')
        self.assertEqual(res.context['days'], 90)
        self.assertEqual(res.context['shop'], shop)
        self.assertGreater(res.context['n']['tiles']['placed'], 0)
        self.assertTrue(res.context['charts']['temperatures'])
        self.assertEqual(PaymentAttempt.objects.count(), 0)
        # junk filters fall back to all shops, 30 days
        res = self.client.get('/admin/dashboard/?shop=abc&days=5')
        self.assertEqual((res.context['shop'], res.context['days']), (None, 30))

    def test_admin_pages_link_to_it(self):
        self.client.login(username='staff', password='pw')
        self.assertContains(self.client.get('/admin/'), 'href="/admin/dashboard/"')
