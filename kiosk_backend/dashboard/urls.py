from django.contrib import admin
from django.urls import path

from .views import dashboard

urlpatterns = [
    path('', admin.site.admin_view(dashboard), name='admin-dashboard'),
]
