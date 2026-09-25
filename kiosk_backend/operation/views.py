from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from .serializer import InventorySerializer
from rest_framework import status
from drf_spectacular.utils import extend_schema
from django.shortcuts import get_object_or_404
from .models import Inventory
# Create your views here.

@extend_schema(summary="Set a shop's stock of an ingredient (staff only)",
               request=InventorySerializer, responses=InventorySerializer)
@api_view(['PATCH'])
@permission_classes([IsAdminUser])  # staff accounts only; kiosks will get their own credentials later
def inventory(request, shop, ingredient):
    inventory_instance = get_object_or_404(Inventory, shop=shop, ingredient=ingredient)
    serializer = InventorySerializer(inventory_instance, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
