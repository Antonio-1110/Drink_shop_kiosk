from django.urls import path
from . import machine, views

urlpatterns = [
    path('inventory/shop/<int:shop>/ingredient/<int:ingredient>/', views.inventory, name='update-inventory'),
    # the drink machine's edge service (kiosk key)
    path('machine/heartbeat/', machine.heartbeat, name='machine-heartbeat'),
    path('machine/temperatures/', machine.temperatures, name='machine-temperatures'),
    path('machine/next-order/', machine.next_order, name='machine-next-order'),
]
