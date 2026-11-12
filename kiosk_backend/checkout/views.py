import logging

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiResponse, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from ordering.models import Order
from payments.paynow import PayNowError
from . import services
from django.conf import settings
from django.http import HttpResponse
from .providers import PROVIDERS, WEBHOOKS, PaymentUnavailable, get_provider, paynow_method, SUCCEEDED, FAILED

logger = logging.getLogger(__name__)

Error = inline_serializer('CheckoutError', {'error': serializers.CharField()})

PaymentStarted = inline_serializer('PaymentStarted', {
    'attempt': serializers.IntegerField(),
    'method': serializers.CharField(),
    'amount': serializers.DecimalField(max_digits=8, decimal_places=2, coerce_to_string=True),
    'expires_at': serializers.DateTimeField(help_text="The ingredients are held until then; after it the order is cancelled if unpaid."),
    'label': serializers.CharField(help_text="The method's name for customers, e.g. PayNow or GrabPay."),
    'test_mode': serializers.BooleanField(help_text="True when no real money moves (sandbox or a gateway's test keys). "
                                                    "Screens should say so."),
    'qr_code': serializers.CharField(required=False, help_text="QR code for the customer's phone, a PNG data: URL. "
                                     "PayNow: scan in a banking app. GrabPay and sandbox: opens the payment page."),
    'reference': serializers.CharField(required=False, help_text="Reference shown in the customer's bank app."),
    'pay_url': serializers.CharField(required=False, help_text="The page the QR code opens, where there is one."),
    'test_pay_url': serializers.CharField(required=False, help_text="Test mode only: a page where staff can pretend the customer paid."),
})

OrderStatus = inline_serializer('OrderPaymentStatus', {
    'status': serializers.CharField(help_text="PENDING until paid, then PAID, PREPARING (being made), READY (collect "
                                         "it now) and COLLECTED. CANCELLED if never paid; FAILED or "
                                         "REFUND_NEEDED if the drink couldn't be made."),
    'hold_expires_at': serializers.DateTimeField(allow_null=True, help_text="While PENDING: when the order is cancelled if still unpaid."),
    'payments': inline_serializer('PaymentAttemptSummary', {
        'method': serializers.CharField(), 'status': serializers.CharField(),
        'expires_at': serializers.DateTimeField()}, many=True),
})


def base_url(request):
    # where the customer's phone reaches this backend; behind the kiosk's dev proxy the request's
    # own host can be one only the kiosk sees, so PUBLIC_BASE_URL wins when set
    url = settings.PUBLIC_BASE_URL or request.build_absolute_uri('/')
    return url if url.endswith('/') else url + '/'


def start_response(request, order, method):
    provider = PROVIDERS[method]
    try:
        attempt, details = services.start_payment(order, method, base_url(request))
    except services.CheckoutError as e:
        return Response({'error': str(e)}, status=status.HTTP_409_CONFLICT)
    except (PayNowError, PaymentUnavailable) as e:
        # usually missing company PayNow settings; staff need to see why, customers don't
        logger.error("Can't start a %s payment for order %s: %s", method, order.pk, e)
        return Response({'error': "Payment is not available right now. Please ask staff."},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({'attempt': attempt.pk, 'method': method, 'label': provider.label,
                     'test_mode': bool(provider.test_mode), 'amount': str(attempt.amount),
                     'expires_at': attempt.expires_at, **details}, status=status.HTTP_200_OK)


@extend_schema(summary="Start paying for an order",
               description="Opens a payment with the chosen method (see PAYMENT_METHODS) and holds the "
                           "order's ingredients until the payment expires. Calling it again returns the "
                           "same open payment.",
               request=inline_serializer('StartPayment', {'method': serializers.CharField()}),
               responses={200: PaymentStarted, 400: Error, 404: Error, 409: Error, 503: Error})
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def start_payment(request, order_id):
    services.expire_unpaid_orders()
    order = get_object_or_404(Order, pk=order_id)
    method = request.data.get('method', '')
    if get_provider(method) is None:
        return Response({'error': f"Unknown payment method {method!r}."}, status=status.HTTP_400_BAD_REQUEST)
    return start_response(request, order, method)


@extend_schema(summary="PayNow QR code for an unpaid order",
               description="Shortcut for starting a PayNow payment: POST .../payments/ with the method set by "
                           "PAYNOW_METHOD (sandbox in development, stripe_paynow with Stripe), or plain paynow.",
               responses={200: PaymentStarted, 404: Error, 409: Error, 503: Error})
@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def paynow_qr(request, order_id):
    services.expire_unpaid_orders()
    order = get_object_or_404(Order, pk=order_id)
    method = paynow_method()
    if get_provider(method) is None:
        return Response({'error': "PayNow is not enabled."}, status=status.HTTP_404_NOT_FOUND)
    return start_response(request, order, method)


@extend_schema(summary="Payment status of an order", responses={200: OrderStatus, 404: Error})
@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def order_status(request, order_id):
    services.expire_unpaid_orders()
    order = get_object_or_404(Order, pk=order_id)
    pending = order.status == Order.Status.PENDING
    return Response({
        'status': order.status,
        'hold_expires_at': services.hold_expires_at(order) if pending else None,
        'payments': [{'method': a.method, 'status': a.status, 'expires_at': a.expires_at}
                     for a in order.payment_attempts.order_by('created_at')],
    })


@extend_schema(summary="Cancel an unpaid order",
               description="For the customer's Cancel button or the kiosk's idle timeout. Puts the "
                           "ingredients back on sale straight away. Needs the order_token from placing the order.",
               request=inline_serializer('CancelOrder', {
                   'order_token': serializers.CharField(),
                   'reason': serializers.ChoiceField(choices=['customer', 'idle_timeout'], required=False,
                                                     help_text="idle_timeout when the kiosk cancels an abandoned order.")}),
               responses={200: inline_serializer('OrderCancelled', {'status': serializers.CharField()}),
                          403: Error, 404: Error, 409: Error})
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def cancel_order(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    if not services.check_order_token(order, request.data.get('order_token')):
        return Response({'error': "Not your order."}, status=status.HTTP_403_FORBIDDEN)
    # only known values, so the history never holds free text from the request
    if request.data.get('reason') == 'idle_timeout':
        who = dict(actor="timeout", reason="Cancelled by the kiosk idle timeout.")
    else:
        who = dict(actor="customer", reason="Cancelled by the customer.")
    if not services.cancel_order(order, **who):
        return Response({'error': "Only unpaid orders can be cancelled."}, status=status.HTTP_409_CONFLICT)
    return Response({'status': Order.Status.CANCELLED})


@extend_schema(summary="Payment notification from a payment provider",
               description="Each provider posts here with its own format and signature, checked by that provider's "
                           "code. Stripe uses /checkout/webhooks/stripe/ for all its methods.",
               request=None, responses={200: OpenApiResponse(description="Processed"), 400: Error, 404: Error})
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def payment_webhook(request, method):
    provider = WEBHOOKS.get(method) or PROVIDERS.get(method)
    try:
        events = provider.parse_webhook(request) if provider else None
    except NotImplementedError:
        events = None
    except ValueError as e:
        logger.warning("Rejected %s webhook: %s", method, e)
        return Response({'error': "Invalid notification."}, status=status.HTTP_400_BAD_REQUEST)
    if events is None:
        return Response({'error': "No notifications for this payment method."}, status=status.HTTP_404_NOT_FOUND)
    for event, order_id, provider_ref, amount, *rest in events:
        paid_with = rest[0] if rest else method
        order = Order.objects.filter(pk=order_id).first()
        if order is None or paid_with not in PROVIDERS:
            logger.error("%s notification for unknown order %s or method %s (%s)",
                         method, order_id, paid_with, provider_ref)
        elif event == SUCCEEDED:
            try:
                services.confirm_payment(order, paid_with, amount, provider_ref)
            except services.CheckoutError as e:
                logger.error("Ignored %s notification: %s", method, e)
        elif event == FAILED:
            services.payment_failed(order, paid_with, provider_ref)
    return Response({'ok': True})


def payment_page_done(request):
    """Where a phone lands after paying on a gateway's page (GrabPay). The kiosk notices the payment itself."""
    return HttpResponse("<!doctype html><meta name=viewport content='width=device-width'>"
                        "<title>Payment sent</title><body style='font:18px system-ui;text-align:center;padding:3em 1em'>"
                        "<h1>Thank you</h1><p>You can go back to the kiosk now.</p>")
