from django.contrib import admin
from django.urls import path

from .actions import act
from .views import dashboard

urlpatterns = [
    path('', admin.site.admin_view(dashboard), name='admin-dashboard'),
    path('act/', admin.site.admin_view(act), name='admin-dashboard-act'),
]
