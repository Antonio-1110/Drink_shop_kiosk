from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from .serializer import InventorySerializer
from rest_framework import status
from drf_spectacular.utils import extend_schema
from django.shortcuts import get_object_or_404
from .models import Inventory, StockMovement
# Create your views here.

@extend_schema(summary="Set a shop's stock of an ingredient (staff only)",
               request=InventorySerializer, responses=InventorySerializer)
@api_view(['PATCH'])
@permission_classes([IsAdminUser])  # staff accounts only; kiosks will get their own credentials later
def inventory(request, shop, ingredient):
    inventory_instance = get_object_or_404(Inventory, shop=shop, ingredient=ingredient)
    serializer = InventorySerializer(inventory_instance, data=request.data, partial=True)
    if serializer.is_valid():
        new_stock = serializer.validated_data.get('current_stock')
        if new_stock is not None:
            # a stock count sets the level; log it as the difference, like every other stock change
            inventory_instance.adjust_stock(new_stock - inventory_instance.current_stock,
                                            StockMovement.Reason.ADJUSTMENT, user=request.user)
        return Response(InventorySerializer(inventory_instance).data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
