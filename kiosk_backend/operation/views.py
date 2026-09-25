from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .serializer import  InventorySerializer
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Inventory
# Create your views here.

@api_view(['PATCH']) # limit access to known IPs only
def inventory(request, shop, ingredient):
    try:
        inventory_instance = get_object_or_404(
            Inventory, 
            shop=shop, 
            ingredient=ingredient
        )
    except Inventory.DoesNotExist:
        return Response(
            {'detail': 'Inventory item not found for the given shop and ingredient.'},
            status=status.HTTP_404_NOT_FOUND
        )
    data = request.data
    serializer = InventorySerializer(inventory_instance, data=data, partial=True)
    if serializer.is_valid():
        print(1)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)