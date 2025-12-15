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
from .utils import qr_gen, inventory_check, verify_drink_ids, check_cart_fulfillment

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
        drink_serializer = DrinkSerializer(Drink.objects.exclude(id__in=inventory_check(shop, valid_cart)),many=True)
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
            drinks
            ingredients
            return Response({'error':'order unavailable'})
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
    qr_img = qr_gen(float(order.revenue)) # reference no.
    return Response({'status':'QR code generated', 'qr code': qr_img}, status=status.HTTP_200_OK)



@api_view(['POST'])
def key_in_order(request): # handling orders with more than one drink
    data = request.data