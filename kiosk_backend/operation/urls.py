from django.urls import path
from . import views

urlpatterns = [
    path('inventory/shop/<int:shop>/ingredient/<int:ingredient>/', views.inventory, name='update-inventory')
]