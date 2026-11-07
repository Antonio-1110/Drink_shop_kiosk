"""The endpoints the drink machine's edge service calls, with its kiosk key
(`Authorization: Kiosk <key>`, see kiosk_auth.py). With these the shop runs without staff:

- heartbeat: the machine checks in about once a minute. If it stops, the shop stops taking orders
  (see availability.py) until it's back.
- temperatures: probe readings for chilled ingredients. An out-of-range reading locks dairy drinks
  until staff clear the lock.
- next-order: the machine asks for the next paid order to make and gets the recipe in each
  ingredient's unit (mL, g). Taking it moves the order to PREPARING, so two machines can't make it.

The machine then reports READY or FAILED on POST /ordering/orders/<id>/progress/.
"""
import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from ordering.models import Order
from ordering.status import change_status
from ordering.utils import menu_needs
from .availability import closed_reason, heartbeat_fresh, locked_ingredient_ids
from .kiosk_auth import IsKiosk, KioskKeyAuthentication
from .models import Ingredient, Inventory, Kiosk

logger = logging.getLogger(__name__)

S = Order.Status


def machine_view(*methods):
    """A view only a kiosk's edge service can call."""
    def wrap(view):
        view = permission_classes([IsKiosk])(view)
        view = authentication_classes([KioskKeyAuthentication])(view)
        return api_view(methods)(view)
    return wrap


def _chilled(kiosk):
    return [{'ingredient': inv.ingredient_id, 'code': inv.ingredient.code, 'name': inv.ingredient.name,
             'min_safe_temp_c': inv.min_safe_temp_c, 'max_safe_temp_c': inv.max_safe_temp_c}
            for inv in Inventory.objects.filter(shop_id=kiosk.shop_id).select_related('ingredient')
            .exclude(min_safe_temp_c=None, max_safe_temp_c=None).order_by('ingredient__name')]


def _state(kiosk):
    closed = closed_reason(kiosk.shop)
    return {'shop_open': closed is None, 'closed_reason': closed[1] if closed else None,
            'sfa_locked': kiosk.sfa_locked, 'sfa_lock_reason': kiosk.sfa_lock_reason}


_State = {
    'shop_open': serializers.BooleanField(),
    'closed_reason': serializers.CharField(allow_null=True, help_text="machine_offline or maintenance"),
    'sfa_locked': serializers.BooleanField(help_text="Dairy lock: chilled ingredients are off sale."),
    'sfa_lock_reason': serializers.CharField(),
}
_Chilled = inline_serializer('ChilledIngredient', {
    'ingredient': serializers.IntegerField(), 'code': serializers.CharField(allow_null=True),
    'name': serializers.CharField(), 'min_safe_temp_c': serializers.DecimalField(4, 1, allow_null=True),
    'max_safe_temp_c': serializers.DecimalField(4, 1, allow_null=True)}, many=True)


@extend_schema(
    summary="Machine check-in (kiosk edge service only)",
    description="Send about once a minute. ONLINE (the default) or MAINTENANCE, plus the state of each "
                "module, e.g. {\"sealer\": \"ok\", \"ice\": \"low\"}. A machine that misses check-ins for "
                "MACHINE_HEARTBEAT_TIMEOUT_SECONDS closes its shop until it's back. The reply lists the chilled "
                "ingredients to send temperature readings for.",
    request=inline_serializer('HeartbeatRequest', {
        'status': serializers.ChoiceField(choices=['ONLINE', 'MAINTENANCE'], required=False),
        'modules': serializers.DictField(required=False)}),
    responses={200: inline_serializer('HeartbeatReply', {**_State, 'chilled': _Chilled}), 400: OpenApiResponse()})
@machine_view('POST')
def heartbeat(request):
    kiosk = request.auth
    to = request.data.get('status', Kiosk.Status.ONLINE)
    modules = request.data.get('modules', {})
    if to not in (Kiosk.Status.ONLINE, Kiosk.Status.MAINTENANCE):
        return Response({'error': "status must be ONLINE or MAINTENANCE."}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(modules, dict):
        return Response({'error': "modules must be an object."}, status=status.HTTP_400_BAD_REQUEST)
    if kiosk.operational_status != to:
        logger.warning("Machine %s is now %s", kiosk.machine_id, to)
    kiosk.operational_status = to
    kiosk.module_states = modules
    kiosk.last_heartbeat = timezone.now()
    kiosk.save(update_fields=['operational_status', 'module_states', 'last_heartbeat'])
    return Response({**_state(kiosk), 'chilled': _chilled(kiosk)})


@extend_schema(
    summary="Send temperature readings (kiosk edge service only)",
    description="One reading per chilled ingredient (see the check-in reply). A reading outside the "
                "ingredient's safe range locks the shop's chilled ingredients until staff clear the lock. If a "
                "probe stops answering, the machine should send its last reading as out of range itself.",
    request=inline_serializer('TemperatureRequest', {'readings': inline_serializer('TemperatureReadingIn', {
        'ingredient': serializers.IntegerField(), 'temp_c': serializers.DecimalField(4, 1),
        'recorded_at': serializers.DateTimeField(required=False)}, many=True)}),
    responses={200: inline_serializer('TemperatureReply', {**_State, 'recorded': serializers.IntegerField()}),
               400: OpenApiResponse()})
@machine_view('POST')
def temperatures(request):
    kiosk = request.auth
    readings = request.data.get('readings')
    if not isinstance(readings, list) or not readings:
        return Response({'error': "Send readings: a list of {ingredient, temp_c}."}, status=status.HTTP_400_BAD_REQUEST)
    stock = {inv.ingredient_id: inv for inv in Inventory.objects.filter(shop_id=kiosk.shop_id)}
    parsed = []
    for r in readings:
        try:
            inv = stock[int(r['ingredient'])]
            temp = Decimal(str(r['temp_c'])).quantize(Decimal('0.1'))
            if not -50 <= temp <= 150:
                raise ValueError
            at = parse_datetime(r['recorded_at']) if r.get('recorded_at') else None
            if r.get('recorded_at') and at is None:
                raise ValueError
        except (KeyError, TypeError, ValueError, InvalidOperation):
            return Response({'error': f"Bad reading {r!r}: needs an ingredient this shop stocks and temp_c."},
                            status=status.HTTP_400_BAD_REQUEST)
        parsed.append((inv, temp, at))
    with transaction.atomic():
        for inv, temp, at in parsed:
            reading = inv.record_temperature(temp, recorded_at=at)
            if not reading.within_bounds:
                logger.error("Dairy lock at %s: %s at %s C", kiosk.machine_id, inv.ingredient, temp)
    kiosk.refresh_from_db()
    return Response({**_state(kiosk), 'recorded': len(parsed)})


def recipe(order):
    """Each item of the order with the amount of every ingredient, in the ingredient's unit."""
    items = []
    for item in order.items.select_related('drink').prefetch_related('custom_ingredients__ingredient'):
        if item.drink_id:
            amounts = menu_needs([(item.drink_id, item.size, item.sugar, item.ice)])
        else:
            amounts = {line.ingredient_id: line.amount for line in item.custom_ingredients.all()}
        ingredients = Ingredient.objects.in_bulk(amounts)
        items.append({
            'item': item.pk, 'name': item.drink.name if item.drink_id else "Custom drink",
            'size': item.get_size_display(), 'sugar': item.get_sugar_display(), 'ice': item.get_ice_display(),
            'lines': [{'ingredient': i.pk, 'code': i.code, 'name': i.name, 'kind': i.kind,
                       'unit': i.unit_of_measure, 'amount': amounts[i.pk]}
                      for i in sorted(ingredients.values(), key=lambda i: (i.kind, i.name)) if amounts[i.pk]],
        })
    return items


_Job = inline_serializer('MachineJob', {
    'id': serializers.IntegerField(), 'status': serializers.CharField(),
    'items': inline_serializer('MachineJobItem', {
        'item': serializers.IntegerField(), 'name': serializers.CharField(), 'size': serializers.CharField(),
        'sugar': serializers.CharField(), 'ice': serializers.CharField(),
        'lines': inline_serializer('MachineJobLine', {
            'ingredient': serializers.IntegerField(), 'code': serializers.CharField(allow_null=True),
            'name': serializers.CharField(), 'kind': serializers.CharField(), 'unit': serializers.CharField(),
            'amount': serializers.DecimalField(10, 2)}, many=True)}, many=True)})


@extend_schema(
    summary="Take the next order to make (kiosk edge service only)",
    description="Gives the oldest paid order at the machine's shop and moves it to PREPARING, so no other "
                "machine takes it. The reply has each drink's ingredients and amounts. 204 when there's nothing "
                "to make. A paid order that needs an ingredient under the dairy lock is failed (for a refund) "
                "instead of handed out. Report READY or FAILED on /ordering/orders/{id}/progress/.",
    request=None, responses={200: _Job, 204: OpenApiResponse(description="Nothing to make.")})
@machine_view('POST')
def next_order(request):
    kiosk = request.auth
    actor = f"machine:{kiosk.machine_id}"
    locked = locked_ingredient_ids(kiosk.shop)
    for order in Order.objects.filter(shop_id=kiosk.shop_id, status=S.PAID).order_by('time', 'pk')[:20]:
        # change_status checks the order is still PAID, so only one machine can take it
        if not change_status(order, S.PREPARING, actor=actor, reason="Taken by the machine."):
            continue
        items = recipe(order)
        unsafe = sorted({line['name'] for item in items for line in item['lines'] if line['ingredient'] in locked})
        if unsafe:
            change_status(order, S.FAILED, actor=actor,
                          reason=f"Not made: dairy lock on {', '.join(unsafe)}"[:200])
            logger.error("Order %s failed at %s: dairy lock on %s", order.pk, kiosk.machine_id, unsafe)
            continue
        return Response({'id': order.pk, 'status': order.status, 'items': items})
    return Response(status=status.HTTP_204_NO_CONTENT)


def mark_silent_machines_offline(now=None):
    """Marks machines that stopped checking in as OFFLINE (their shops are already closed to new orders).
    Returns how many changed. Run by `manage.py run_jobs`."""
    now = now or timezone.now()
    count = 0
    for kiosk in Kiosk.objects.exclude(api_key_hash='').exclude(operational_status=Kiosk.Status.OFFLINE):
        if not heartbeat_fresh(kiosk, now):
            Kiosk.objects.filter(pk=kiosk.pk).update(operational_status=Kiosk.Status.OFFLINE)
            logger.error("Machine %s stopped checking in (last %s); its shop is closed", kiosk.machine_id,
                         kiosk.last_heartbeat)
            count += 1
    return count
