from django.urls import path
from .designer import designer_options
from .views import (key_in_order, shops, available_drinks, check_order_availability, collect_order,
                    report_progress)

urlpatterns = [
    path('log-order/', key_in_order, name='log-order'),
    path('shops/', shops, name='shop-list'),
    path('drinks/', available_drinks, name='available-drinks'),
    path('designer/options/', designer_options, name='designer-options'),
    path('pickup/', collect_order, name='collect-order'),
    path('orders/<int:order_id>/progress/', report_progress, name='report-progress'),
    path('check-order/', check_order_availability, name='check-order'),
]