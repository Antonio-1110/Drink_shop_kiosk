from django.shortcuts import render
from operation.models import Shop, Drink, DrinkIngredient, Inventory
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializer import OrderSerializer
from operation.serializer import ShopSerializer, DrinkSerializer
from django.db.models import F, Q
from django.db import transaction
from .models import Order
from .utils import qr_gen, inventory_check, inventory_update, verify_drink_ids, check_cart_fulfillment

# Create your views here.

@api_view(['GET'])
def shops(request): # need to use request for membership programs
    shops = Shop.objects.all()
    serializer = ShopSerializer(shops, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def avaliable_drinks(request):
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
        drink_serializer = DrinkSerializer(Drink.objects.filter(is_active=True).exclude(id__in=inventory_check(shop, valid_cart)),many=True)
        return Response(drink_serializer.data)
    except Shop.DoesNotExist:
        return Response({"error": "Shop not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    


@api_view(['GET'])
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
        tf, drinks, ingredients = check_cart_fulfillment(shop, valid_cart)
        if tf:
            return Response({'status':'order is good'}, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': 'order unavailable', 'drinks': drinks, 'ingredients': ingredients},
                status=status.HTTP_409_CONFLICT)
    except Shop.DoesNotExist:
        return Response({"error": "Shop not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    

@api_view(['GET'])
def paynow_qr(request, order_id):
    try: 
        order = Order.objects.get(pk=order_id, status='PENDING')
    except Order.DoesNotExist:
        return Response({"error": "Order not found or payment status is resolved."}, status=status.HTTP_404_NOT_FOUND)
    reference = f"ORDER{order.id}"
    qr_img = qr_gen(order.revenue, reference)
    return Response({'status': 'QR code generated', 'qr_code': qr_img, 'reference': reference,
                     'amount': str(order.revenue)}, status=status.HTTP_200_OK)



@api_view(['POST'])
def key_in_order(request): # handling orders with more than one drink
    serializer = OrderSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    shop = serializer.validated_data['shop']
    # one entry per drink ordered, so two of the same drink uses stock twice
    cart = [item['drink'].id for item in serializer.validated_data['items']]
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
