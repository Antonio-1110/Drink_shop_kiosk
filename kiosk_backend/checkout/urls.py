from django.urls import path
from . import sandbox, views

urlpatterns = [
    path('ordering/orders/<int:order_id>/payments/', views.start_payment, name='start-payment'),
    path('ordering/orders/<int:order_id>/paynow-qr/', views.paynow_qr, name='paynow-qr'),
    path('ordering/orders/<int:order_id>/status/', views.order_status, name='order-status'),
    path('ordering/orders/<int:order_id>/cancel/', views.cancel_order, name='cancel-order'),
    path('checkout/webhooks/<str:method>/', views.payment_webhook, name='payment-webhook'),
    path('checkout/paid/', views.payment_page_done, name='payment-page-done'),
    path('checkout/sandbox/', sandbox.index, name='sandbox-bank'),
    path('checkout/sandbox/pay/<str:token>/', sandbox.pay, name='sandbox-pay'),
]
