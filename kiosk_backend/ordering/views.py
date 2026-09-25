from django.shortcuts import render
from operation.models import Shop, Drink, DrinkIngredient, Inventory
import logging
from rest_framework.decorators import api_view, permission_classes
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
from .utils import (qr_gen, inventory_check, inventory_update, verify_drink_ids, check_cart_fulfillment,
                    expire_unpaid_orders, payment_deadline)

logger = logging.getLogger(__name__)

# The kiosk screen calls these endpoints without logging in, so each one opts out of the
# staff-only default set in settings.REST_FRAMEWORK.

@extend_schema(summary="List shops", responses=ShopSerializer(many=True))
@api_view(['GET'])
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
        drink_serializer = DrinkSerializer(Drink.objects.exclude(id__in=inventory_check(shop, valid_cart)),many=True)
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
    

@extend_schema(summary="PayNow QR code for an unpaid order",
               responses={200: schema.PaynowQr, 404: schema.Error})
@api_view(['GET'])
@permission_classes([AllowAny])
def paynow_qr(request, order_id):
    expire_unpaid_orders()
    try: 
        order = Order.objects.get(pk=order_id, status='PENDING')
    except Order.DoesNotExist:
        return Response({"error": "Order not found or payment status is resolved."}, status=status.HTTP_404_NOT_FOUND)
    reference = f"ORDER{order.id}"
    qr_img = qr_gen(order.revenue, reference)
    return Response({'status': 'QR code generated', 'qr_code': qr_img, 'reference': reference,
                     'amount': str(order.revenue),
                     'expires_at': payment_deadline(order)}, status=status.HTTP_200_OK)



@extend_schema(summary="Place an order",
               description="Reserves the ingredients and creates an unpaid order. Unpaid orders are "
                           "cancelled after ORDER_PAYMENT_TIMEOUT_MINUTES and the stock is returned.",
               request=OrderSerializer, responses={201: OrderSerializer, 400: OpenApiResponse(description="Invalid order: errors keyed by field."),
                          409: schema.Unavailable})
@api_view(['POST'])
@permission_classes([AllowAny])
def key_in_order(request): # handling orders with more than one drink
    serializer = OrderSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    shop = serializer.validated_data['shop']
    # one entry per drink ordered, so two of the same drink uses stock twice
    cart = [item['drink'].id for item in serializer.validated_data['items']]
    # free up stock held by abandoned orders before checking this one
    expire_unpaid_orders(shop)
    with transaction.atomic():
        # lock this shop's stock so two kiosks can't sell the last cup at once
        list(Inventory.objects.select_for_update().filter(shop=shop))
        tf, drinks, ingredients = check_cart_fulfillment(shop, cart)
        if not tf:
            return Response(
                {'error': 'order unavailable', 'drinks': drinks, 'ingredients': ingredients},
                status=status.HTTP_409_CONFLICT)
        order = serializer.save()
        inventory_update(shop, cart)
    return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
