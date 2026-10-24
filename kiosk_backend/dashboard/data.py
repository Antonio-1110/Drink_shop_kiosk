"""Numbers for the staff dashboard, worked out from the orders, their history, stock and fridge
readings. Everything here only reads; build() returns plain data that the page draws as charts."""
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from statistics import median

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone

from checkout.models import PaymentAttempt
from operation.models import Inventory, Kiosk, StockMovement, TemperatureReading
from ordering.models import Order, OrderEvent, OrderItem

S = Order.Status
SOLD = [S.PAID, S.COLLECTED]
PERIODS = [7, 30, 90]
# an order still in this state after this long is worth a look
STUCK_PENDING = timedelta(minutes=30)
STUCK_UNCOLLECTED = timedelta(hours=2)
HEARTBEAT_STALE = timedelta(minutes=5)
TOP_DRINKS = 8


def build(shop=None, days=30, now=None):
    now = now or timezone.now()
    tz = timezone.get_current_timezone()
    today = timezone.localdate(now, tz)
    first_day = today - timedelta(days=days - 1)
    start = timezone.make_aware(timezone.datetime.combine(first_day, timezone.datetime.min.time()), tz)

    orders = Order.objects.all()
    if shop:
        orders = orders.filter(shop=shop)
    period = orders.filter(time__gte=start, time__lte=now)

    kiosks = _kiosks(shop, now)
    return {
        'start': first_day, 'end': today, 'days': days,
        'tiles': _tiles(orders, period),
        'daily': _daily(period, first_day, days, tz),
        'hourly': _hourly(period, tz),
        'drinks': _drinks(period),
        'grades': _grades(period),
        'cancellations': _cancellations(period),
        'attention': {**_attention(orders, now), 'kiosks': [k for k in kiosks if k['locked'] or k['silent']]},
        'stock': _stock(shop, start, days),
        'kiosks': kiosks,
        'temperatures': _temperatures(shop, max(start, now - timedelta(days=7)), tz),
    }


def _tiles(orders, period):
    totals = period.aggregate(
        placed=Count('id'),
        sold=Count('id', filter=Q(status__in=SOLD)),
        cancelled=Count('id', filter=Q(status=S.CANCELLED)),
        revenue=Sum('revenue', filter=Q(status__in=SOLD)),
        cups=Sum('item_quantity', filter=Q(status__in=SOLD)),
    )
    revenue = totals['revenue'] or Decimal('0')
    return {
        'placed': totals['placed'],
        'sold': totals['sold'],
        'cups': totals['cups'] or 0,
        'revenue': revenue,
        'average': (revenue / totals['sold']).quantize(Decimal('0.01')) if totals['sold'] else None,
        'cancel_rate': round(100 * totals['cancelled'] / totals['placed']) if totals['placed'] else None,
        'minutes_to_pay': _median_minutes(period, '', S.PAID),
        'minutes_to_collect': _median_minutes(period, S.PAID, S.COLLECTED),
        # right now, whatever the period
        'waiting_payment': orders.filter(status=S.PENDING).count(),
        'waiting_pickup': orders.filter(status=S.PAID).count(),
    }


def _median_minutes(period, from_status, to_status):
    """Median time between an order reaching from_status ('' = placed) and to_status."""
    events = OrderEvent.objects.filter(order__in=period).values_list('order_id', 'from_status', 'to_status', 'at')
    began, ended = {}, {}
    for order_id, frm, to, at in events:
        if (frm == '') if from_status == '' else (to == from_status):
            began.setdefault(order_id, at)
        if to == to_status:
            ended.setdefault(order_id, at)
    gaps = [(ended[o] - began[o]).total_seconds() / 60 for o in ended if o in began and ended[o] >= began[o]]
    return round(median(gaps), 1) if gaps else None


def _daily(period, first_day, days, tz):
    rows = {first_day + timedelta(days=i): {'date': first_day + timedelta(days=i), 'revenue': Decimal('0'),
                                            **{s: 0 for s in S.values}}
            for i in range(days)}
    for row in (period.annotate(day=TruncDate('time', tzinfo=tz)).values('day', 'status')
                .annotate(n=Count('id'), revenue=Sum('revenue'))):
        day = rows.get(row['day'])
        if day is None:
            continue
        day[row['status']] += row['n']
        if row['status'] in SOLD:
            day['revenue'] += row['revenue']
    return list(rows.values())


def _hourly(period, tz):
    counts = [0] * 24
    for time in period.values_list('time', flat=True):
        counts[timezone.localtime(time, tz).hour] += 1
    return counts


def _drinks(period):
    items = (OrderItem.objects.filter(order__in=period.filter(status__in=SOLD))
             .values('drink', 'drink__name').annotate(cups=Count('id')).order_by('-cups', 'drink__name'))
    rows = [{'name': row['drink__name'] or 'Custom (drink designer)', 'cups': row['cups'], 'drink': row['drink']}
            for row in items]
    if len(rows) > TOP_DRINKS:
        rest = sum(row['cups'] for row in rows[TOP_DRINKS - 1:])
        rows = rows[:TOP_DRINKS - 1] + [{'name': f'{len(rows) - TOP_DRINKS + 1} others', 'cups': rest, 'drink': None}]
    return rows


def _grades(period):
    counts = Counter(OrderItem.objects.filter(order__in=period.filter(status__in=SOLD))
                     .values_list('nutri_grade', flat=True))
    return [{'grade': g, 'cups': counts.get(g, 0)} for g in 'ABCD'] + (
        [{'grade': 'Not graded', 'cups': counts['']}] if counts.get('') else [])


def who(actor):
    if actor.startswith('staff:'):
        return 'Staff in the admin'
    if actor.startswith('payment:'):
        return 'Payment'
    return {'customer': 'Customer', 'timeout': 'Kiosk idle timeout', 'system': 'Not paid in time',
            'kiosk': 'Kiosk'}.get(actor, actor or 'Unknown')


def _cancellations(period):
    counts = Counter(who(actor) for actor in OrderEvent.objects.filter(
        order__in=period, to_status=S.CANCELLED).values_list('actor', flat=True))
    return [{'who': name, 'orders': n} for name, n in counts.most_common()]


def _attention(orders, now):
    refunds = (PaymentAttempt.objects.filter(order__in=orders, status=PaymentAttempt.Status.REFUND_NEEDED)
               .select_related('order__shop').order_by('updated_at'))
    pending = orders.filter(status=S.PENDING, time__lt=now - STUCK_PENDING).select_related('shop').order_by('time')
    paid_at = dict(OrderEvent.objects.filter(order__in=orders.filter(status=S.PAID), to_status=S.PAID)
                   .values_list('order_id', 'at'))
    uncollected = [o for o in orders.filter(status=S.PAID).select_related('shop').order_by('time')
                   if now - paid_at.get(o.pk, o.time) > STUCK_UNCOLLECTED]
    return {
        'refunds': [{'attempt': a, 'order': a.order, 'amount': a.amount, 'method': a.method, 'since': a.updated_at,
                     'note': a.note} for a in refunds],
        'pending': [{'order': o, 'since': o.time} for o in pending],
        'uncollected': [{'order': o, 'since': paid_at.get(o.pk, o.time)} for o in uncollected],
    }


def _stock(shop, start, days):
    inventories = Inventory.objects.select_related('shop', 'ingredient').order_by('shop__name', 'ingredient__name')
    if shop:
        inventories = inventories.filter(shop=shop)
    # net stock taken by orders in the period: ORDER takes it, RELEASE gives back what cancelled orders held
    used = dict(StockMovement.objects.filter(
        inventory__in=inventories, created_at__gte=start,
        reason__in=[StockMovement.Reason.ORDER, StockMovement.Reason.RELEASE])
        .values('inventory').annotate(net=Sum('change')).values_list('inventory', 'net'))
    rows = []
    for inv in inventories:
        per_day = max(-(used.get(inv.pk) or Decimal('0')), Decimal('0')) / days
        rows.append({
            'inventory': inv, 'shop': inv.shop.name, 'ingredient': inv.ingredient.name, 'unit': inv.ingredient.unit_of_measure,
            'stock': inv.current_stock, 'reorder_at': inv.ingredient.reorder_threshold,
            'low': inv.needs_reorder(),
            'per_day': per_day.quantize(Decimal('0.1')),
            'days_left': (inv.current_stock / per_day).quantize(Decimal('0.1')) if per_day else None,
        })
    rows.sort(key=lambda r: (r['days_left'] is None, r['days_left'] or 0))
    return rows


def _kiosks(shop, now):
    kiosks = Kiosk.objects.select_related('shop').order_by('shop__name')
    if shop:
        kiosks = kiosks.filter(shop=shop)
    return [{
        'kiosk': k, 'locked': k.sfa_locked, 'lock_reason': k.sfa_lock_reason,
        'status': k.get_operational_status_display(), 'last_heartbeat': k.last_heartbeat,
        # a kiosk that has never checked in isn't flagged: there is no edge service sending check-ins yet
        'silent': k.last_heartbeat is not None and now - k.last_heartbeat > HEARTBEAT_STALE,
    } for k in kiosks]


def _temperatures(shop, since, tz):
    """Hourly average per chilled ingredient, with its safe range."""
    readings = TemperatureReading.objects.filter(recorded_at__gte=since)
    if shop:
        readings = readings.filter(inventory__shop=shop)
    series = defaultdict(list)
    out_of_range = Counter()
    for row in (readings.annotate(hour=TruncHour('recorded_at', tzinfo=tz))
                .values('inventory', 'hour').annotate(n=Count('id'), total=Sum('temp_c'),
                                                      bad=Count('id', filter=Q(within_bounds=False)))
                .order_by('hour')):
        series[row['inventory']].append({'at': row['hour'], 'temp_c': round(row['total'] / row['n'], 1)})
        out_of_range[row['inventory']] += row['bad']
    inventories = Inventory.objects.filter(pk__in=series).select_related('shop', 'ingredient')
    return [{
        'name': f"{inv.ingredient.name} ({inv.shop.name})" if not shop else inv.ingredient.name,
        'max_c': inv.max_safe_temp_c, 'min_c': inv.min_safe_temp_c, 'last_c': inv.last_temp_c,
        'out_of_range': out_of_range[inv.pk], 'points': series[inv.pk],
    } for inv in sorted(inventories, key=lambda i: (i.shop.name, i.ingredient.name))]
