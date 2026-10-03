"""How a machine's edge service proves which kiosk it is.

Each kiosk has its own secret key, made with `manage.py kiosk_key <machine_id>` and shown once.
The edge service sends it as `Authorization: Kiosk <key>`. Only a hash is stored, so a copy of
the database doesn't give anyone the keys.
"""
import hashlib
import secrets

from django.contrib.auth.models import AnonymousUser
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import authentication, exceptions, permissions

from .models import Kiosk

KEYWORD = 'Kiosk'


def hash_key(key):
    return hashlib.sha256(key.encode()).hexdigest()


def new_key(kiosk):
    """Gives the kiosk a new key (the old one stops working) and returns it."""
    key = secrets.token_urlsafe(32)
    kiosk.api_key_hash = hash_key(key)
    kiosk.save(update_fields=['api_key_hash'])
    return key


class KioskKeyAuthentication(authentication.BaseAuthentication):
    """Sets request.auth to the Kiosk whose key was sent. request.user stays anonymous: a machine
    is not a staff member."""

    def authenticate(self, request):
        parts = authentication.get_authorization_header(request).split()
        if not parts or parts[0].decode(errors='replace') != KEYWORD:
            return None
        if len(parts) != 2:
            raise exceptions.AuthenticationFailed("Send the kiosk key as 'Kiosk <key>'.")
        key = parts[1].decode(errors='replace')
        kiosk = Kiosk.objects.filter(api_key_hash=hash_key(key)).exclude(api_key_hash='').first()
        if kiosk is None:
            raise exceptions.AuthenticationFailed("Unknown kiosk key.")
        return AnonymousUser(), kiosk

    def authenticate_header(self, request):
        return KEYWORD


class IsKiosk(permissions.BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.auth, Kiosk)


class KioskKeyScheme(OpenApiAuthenticationExtension):
    target_class = KioskKeyAuthentication
    name = 'kioskKey'

    def get_security_definition(self, auto_schema):
        return {'type': 'apiKey', 'in': 'header', 'name': 'Authorization',
                'description': "`Kiosk <key>`, the machine's key from `manage.py kiosk_key`."}
