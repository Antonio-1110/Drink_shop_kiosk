from django.urls import path
from .views import key_in_order, shops, avaliable_drinks

urlpatterns = [
    path('log-order/', key_in_order, name='log-order'),
    path('shops/', shops, name='shop-list'),
    path('drinks/', avaliable_drinks, name='avaliable-drinks')
]