from django.urls import path
from .views import key_in_order, shops, available_drinks, check_order_availability, paynow_qr

urlpatterns = [
    path('log-order/', key_in_order, name='log-order'),
    path('shops/', shops, name='shop-list'),
    path('drinks/', available_drinks, name='available-drinks'),
    path('check-order/', check_order_availability, name='check-order'),
    path('orders/<int:order_id>/paynow-qr/', paynow_qr, name='paynow-qr'),
]