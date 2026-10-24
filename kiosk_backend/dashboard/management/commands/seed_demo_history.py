import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from checkout.models import PaymentAttempt, StockHold
from ordering.utils import menu_needs
from operation.models import Drink, Inventory, Kiosk, Shop, StockMovement, TemperatureReading
from ordering.models import Order, OrderEvent, OrderItem

DEMO_USER = 'demo-history'
CHILLED = ('Fresh milk', 'Oat milk')
S = Order.Status


class Command(BaseCommand):
    help = ("Make up past orders and fridge readings for the demo shops seed_demo made, so the admin dashboard has "
            "something to show. Run seed_demo first. Running it again replaces the made-up history; "
            "real orders are left alone. Stock levels don't change.")

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30)
        parser.add_argument('--seed', type=int, default=7, help="same seed, same history")

    @transaction.atomic
    def handle(self, *args, days, seed, **options):
        rng = random.Random(seed)
        drinks = list(Drink.objects.filter(is_active=True))
        shops = list(Shop.objects.filter(name__startswith='Demo ', inventories__isnull=False).distinct())
        if not drinks or not shops:
            raise CommandError("No drinks or stock yet. Run `python manage.py seed_demo` first.")
        self.clear()
        now = timezone.now()
        orders = 0
        for shop in shops:
            inventories = {i.ingredient_id: i for i in shop.inventories.all()}
            for day in range(days, -1, -1):
                for _ in range(rng.randint(8, 22) if day else rng.randint(2, 6)):
                    # busier at lunch and after school/work
                    hour = rng.choice([8, 9, 11, 12, 12, 13, 13, 14, 15, 16, 16, 17, 17, 18, 19, 20, 21])
                    placed = (now - timedelta(days=day)).replace(hour=hour, minute=rng.randint(0, 59))
                    if placed < now:
                        self.make_order(rng, shop, drinks, inventories, placed, now)
                        orders += 1
            Kiosk.objects.get_or_create(shop=shop, defaults={
                'machine_id': f"DEMO-{shop.pk:03d}", 'operational_status': Kiosk.Status.ONLINE})
        readings = self.make_readings(rng, shops, now)
        self.stdout.write(self.style.SUCCESS(
            f"Made {orders} demo orders over {days} days and {readings} fridge readings. "
            "Open /admin/dashboard/ to see them."))

    def clear(self):
        demo = Order.objects.filter(user_id=DEMO_USER)
        StockMovement.objects.filter(order__in=demo).delete()
        StockHold.objects.filter(order__in=demo).delete()
        PaymentAttempt.objects.filter(order__in=demo).delete()
        OrderEvent.objects.filter(order__in=demo).delete()
        demo.delete()

    def make_order(self, rng, shop, drinks, inventories, placed, now):
        picks = [(rng.choice(drinks), rng.choice([0, 0, 1]), rng.choice([4, 4, 3, 2, 1, 0]), rng.choice([4, 4, 3, 2]))
                 for _ in range(rng.choice([1, 1, 1, 2, 2, 3]))]
        revenue = sum(d.l_price if size else d.s_price for d, size, _, _ in picks)
        # recent orders may still be open; older ones have all finished one way or another
        age = now - placed
        outcome = rng.choices(['collected', 'paid', 'cancelled', 'pending'], [80, 3, 15, 2])[0]
        if outcome == 'pending' and age > timedelta(hours=1):
            outcome = 'cancelled'
        if outcome == 'paid' and age > timedelta(hours=6):
            outcome = 'collected'
        order = Order.objects.create(shop=shop, revenue=revenue, item_quantity=len(picks), user_id=DEMO_USER,
                                     status={'collected': S.COLLECTED, 'paid': S.PAID,
                                             'cancelled': S.CANCELLED, 'pending': S.PENDING}[outcome])
        Order.objects.filter(pk=order.pk).update(time=placed)
        for drink, size, sugar, ice in picks:
            item = OrderItem(order=order, drink=drink, size=size, sugar=sugar, ice=ice,
                             unit_price=drink.l_price if size else drink.s_price)
            item.apply_nutri_grade()
            item.save()

        events = [('', S.PENDING, placed, 'customer', '')]
        if outcome in ('collected', 'paid'):
            paid = placed + timedelta(seconds=rng.randint(40, 240))
            events.append((S.PENDING, S.PAID, paid, 'payment:paynow', f"Paid {revenue} by paynow."))
            if outcome == 'collected':
                collected = paid + timedelta(seconds=rng.randint(60, 900))
                events.append((S.PAID, S.COLLECTED, collected, 'kiosk', "Collected with PIN."))
                Order.objects.filter(pk=order.pk).update(collected_at=collected)
        elif outcome == 'cancelled':
            actor, reason = rng.choices(
                [('customer', "Cancelled by the customer."), ('timeout', "Cancelled by the kiosk idle timeout."),
                 ('system', "Not paid in time.")], [5, 3, 2])[0]
            events.append((S.PENDING, S.CANCELLED, placed + timedelta(seconds=rng.randint(30, 600)), actor, reason))
        for frm, to, at, actor, reason in events:
            event = OrderEvent.objects.create(order=order, from_status=frm, to_status=to, actor=actor, reason=reason)
            OrderEvent.objects.filter(pk=event.pk).update(at=at)

        # stock history only: what the order took, and gave back if cancelled
        needs = menu_needs([(d.pk, size, sugar, ice) for d, size, sugar, ice in picks])
        for ingredient_id, amount in needs.items():
            inventory = inventories.get(ingredient_id)
            if inventory is None or not amount:
                continue
            moves = [(-amount, StockMovement.Reason.ORDER, placed)]
            if outcome == 'cancelled':
                moves.append((amount, StockMovement.Reason.RELEASE, events[-1][2]))
            for change, reason, at in moves:
                move = StockMovement.objects.create(inventory=inventory, change=change, reason=reason, order=order,
                                                    stock_after=inventory.current_stock, note="demo history")
                StockMovement.objects.filter(pk=move.pk).update(created_at=at)

    def make_readings(self, rng, shops, now):
        readings = []
        # readings are kept between runs, so a fridge that already has some is left alone
        for inventory in Inventory.objects.filter(shop__in=shops, ingredient__name__in=CHILLED,
                                                  temperature_readings__isnull=True):
            if inventory.max_safe_temp_c is None:
                inventory.max_safe_temp_c = Decimal('4.0')
                inventory.save(update_fields=['max_safe_temp_c'])
            # every 15 minutes for a week, with one door left open for a while
            spike = now - timedelta(hours=rng.randint(24, 140))
            for step in range(7 * 24 * 4):
                at = now - timedelta(minutes=15 * step)
                temp = 2.6 + rng.uniform(-0.6, 0.6) + (2.6 if timedelta(0) <= at - spike < timedelta(minutes=50) else 0)
                temp = Decimal(str(round(temp, 1)))
                readings.append(TemperatureReading(inventory=inventory, temp_c=temp, recorded_at=at,
                                                   within_bounds=inventory.temperature_ok(temp)))
            inventory.last_temp_c = readings[-7 * 24 * 4].temp_c  # the newest one, made first
            inventory.save(update_fields=['last_temp_c'])
        TemperatureReading.objects.bulk_create(readings)
        return len(readings)
