from django.shortcuts import render
from operation.models import Shop, Drink, DrinkIngredient, Inventory
import logging
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiResponse
from . import schema
from .serializer import OrderSerializer
from operation.serializer import ShopSerializer, DrinkSerializer
from django.db.models import F, Q
from django.db import transaction
from .models import Order
from .utils import (inventory_check, verify_drink_ids, check_cart_fulfillment, check_needs, add_needs,
                    aggregate_ingredients, custom_needs)
from checkout.services import expire_unpaid_orders, hold_stock, order_token
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.decorators import throttle_classes
from . import pickup

logger = logging.getLogger(__name__)

# The kiosk screen calls these endpoints without logging in, so each one opts out of the
# staff-only default set in settings.REST_FRAMEWORK. They skip session auth too, so a staff
# login in the same browser can't trip Django's CSRF check.

@extend_schema(summary="List shops", responses=ShopSerializer(many=True))
@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def shops(request): # need to use request for membership programs
    shops = Shop.objects.all()
    serializer = ShopSerializer(shops, many=True)
    return Response(serializer.data)

@extend_schema(summary="Drinks the shop can still make",
               description="Drinks with enough stock for one more cup after everything already in the cart.",
               parameters=[schema.SHOP_ID, schema.CART],
               responses={200: DrinkSerializer(many=True), 400: schema.Error, 404: schema.Error})
@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def available_drinks(request):
    # incorporate drink category as will
    # also need to send image information
    shop_id = request.GET.get('shop_id', "default")
    cart = request.GET.getlist('cart', [])
    if not shop_id or not shop_id.isdigit():
        return Response({"error": "Invalid or missing Shop ID."}, status=status.HTTP_400_BAD_REQUEST)
    shop_id = int(shop_id)
    result, valid_cart, message = verify_drink_ids(cart)
    if not result:
        return Response(
            {"error": message}, status=status.HTTP_400_BAD_REQUEST)
    try: 
        shop = Shop.objects.get(id=shop_id)
        expire_unpaid_orders(shop)
        drink_serializer = DrinkSerializer(Drink.objects.filter(is_active=True).exclude(id__in=inventory_check(shop, valid_cart)),many=True)
        return Response(drink_serializer.data)
    except Shop.DoesNotExist:
        return Response({"error": "Shop not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception:
        # log the details for us, but don't show internal errors to customers
        logger.exception("Unexpected error for shop %s", shop_id)
        return Response({"error": "Something went wrong."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


@extend_schema(summary="Check the cart can be made", parameters=[schema.SHOP_ID, schema.CART],
               responses={200: schema.OrderOk, 400: schema.Error, 404: schema.Error, 409: schema.Unavailable})
@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def check_order_availability(request): #add data verification later
    shop_id = request.GET.get('shop_id', "default")
    cart = request.GET.getlist('cart', [])
    if not shop_id or not shop_id.isdigit():
        return Response({"error": "Invalid or missing Shop ID."}, status=status.HTTP_400_BAD_REQUEST)
    shop_id = int(shop_id)
    result, valid_cart, message = verify_drink_ids(cart)
    if not result:
        return Response(
            {"error": message}, status=status.HTTP_400_BAD_REQUEST)
    try: 
        shop = Shop.objects.get(id=shop_id)
        expire_unpaid_orders(shop)
        tf, drinks, ingredients = check_cart_fulfillment(shop, valid_cart)
        if tf:
            return Response({'status':'order is good'}, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': 'order unavailable', 'drinks': drinks, 'ingredients': ingredients},
                status=status.HTTP_409_CONFLICT)
    except Shop.DoesNotExist:
        return Response({"error": "Shop not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception:
        # log the details for us, but don't show internal errors to customers
        logger.exception("Unexpected error for shop %s", shop_id)
        return Response({"error": "Something went wrong."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

@extend_schema(summary="Place an order",
               description="Holds the ingredients and creates an unpaid order. Start paying with "
                           "POST /ordering/orders/{id}/payments/; the hold lasts as long as that payment. "
                           "Keep order_token: cancelling needs it.",
               request=OrderSerializer, responses={201: schema.OrderCreated, 400: OpenApiResponse(description="Invalid order: errors keyed by field."),
                          409: schema.Unavailable})
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def key_in_order(request): # handling orders with more than one drink
    serializer = OrderSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    shop = serializer.validated_data['shop']
    items = serializer.validated_data['items']
    # one entry per drink ordered, so two of the same drink uses stock twice
    cart = [item['drink'].id for item in items if item.get('drink')]
    needed = add_needs(aggregate_ingredients(cart),
                       *(custom_needs(item['designer_lines']) for item in items if 'designer_lines' in item))
    # free up stock held by abandoned orders before checking this one
    expire_unpaid_orders(shop)
    with transaction.atomic():
        # lock this shop's stock so two kiosks can't sell the last cup at once
        list(Inventory.objects.select_for_update().filter(shop=shop))
        short = check_needs(shop, needed)
        if short:
            drinks = list(DrinkIngredient.objects.filter(drink_id__in=cart, ingredient_id__in=short)
                          .values_list('drink', flat=True).distinct())
            options = sorted({ingredient.code for item in items for ingredient, _, _ in item.get('designer_lines', [])
                              if ingredient.pk in short})
            return Response(
                {'error': 'order unavailable', 'drinks': drinks, 'ingredients': short, 'options': options},
                status=status.HTTP_409_CONFLICT)
        order = serializer.save()
        hold_stock(order, needed)
        pickup.assign_pickup_codes(order)
    # the pickup codes and order token go only to whoever placed the order, never in other responses
    return Response({**OrderSerializer(order).data, 'order_token': order_token(order),
                     'pickup_pin': order.pickup_pin, 'pickup_qr': pickup.pickup_qr(order)},
                    status=status.HTTP_201_CREATED)


@extend_schema(summary="Collect an order at the machine",
               description="The kiosk sends the 6-digit pickup PIN the customer typed, or the token from "
                           "their scanned pickup QR code. A paid order is handed over once and becomes "
                           "COLLECTED. Limited to a few attempts a minute per machine, so PINs can't be guessed.",
               request=schema.PickupRequest,
               responses={200: OrderSerializer, 400: schema.Error, 404: schema.PickupFailed, 409: schema.PickupFailed,
                          429: OpenApiResponse(description="Too many attempts; wait a minute.")})
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([ScopedRateThrottle])
def collect_order(request):
    shop = request.data.get('shop')
    if not str(shop).isdigit():
        return Response({'error': "Invalid or missing shop."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        order = pickup.collect(int(shop), str(request.data.get('code', '')))
    except pickup.PickupError as e:
        return Response({'error': str(e), 'reason': e.reason}, status=e.status)
    return Response(OrderSerializer(order).data)


# ScopedRateThrottle reads the scope from the view; see DEFAULT_THROTTLE_RATES in settings
collect_order.cls.throttle_scope = 'pickup'
