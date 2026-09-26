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
from .providers import PROVIDERS, get_provider, SUCCEEDED, FAILED

logger = logging.getLogger(__name__)

Error = inline_serializer('CheckoutError', {'error': serializers.CharField()})

PaymentStarted = inline_serializer('PaymentStarted', {
    'attempt': serializers.IntegerField(),
    'method': serializers.CharField(),
    'amount': serializers.DecimalField(max_digits=8, decimal_places=2, coerce_to_string=True),
    'expires_at': serializers.DateTimeField(help_text="The ingredients are held until then; after it the order is cancelled if unpaid."),
    'qr_code': serializers.CharField(required=False, help_text="PayNow: PNG image as a data: URL."),
    'reference': serializers.CharField(required=False, help_text="PayNow: reference shown in the customer's bank app."),
})

OrderStatus = inline_serializer('OrderPaymentStatus', {
    'status': serializers.CharField(help_text="PENDING until paid; then the paid status, or CANCELLED."),
    'hold_expires_at': serializers.DateTimeField(allow_null=True, help_text="While PENDING: when the order is cancelled if still unpaid."),
    'payments': inline_serializer('PaymentAttemptSummary', {
        'method': serializers.CharField(), 'status': serializers.CharField(),
        'expires_at': serializers.DateTimeField()}, many=True),
})


def start_response(order, method):
    try:
        attempt, details = services.start_payment(order, method)
    except services.CheckoutError as e:
        return Response({'error': str(e)}, status=status.HTTP_409_CONFLICT)
    except PayNowError as e:
        # usually missing company PayNow settings; staff need to see why, customers don't
        logger.error("Can't start a %s payment for order %s: %s", method, order.pk, e)
        return Response({'error': "Payment is not available right now. Please ask staff."},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({'attempt': attempt.pk, 'method': method, 'amount': str(attempt.amount),
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
    return start_response(order, method)


@extend_schema(summary="PayNow QR code for an unpaid order",
               description="Shortcut for starting a PayNow payment; same as POST .../payments/ with method paynow.",
               responses={200: PaymentStarted, 404: Error, 409: Error, 503: Error})
@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def paynow_qr(request, order_id):
    services.expire_unpaid_orders()
    order = get_object_or_404(Order, pk=order_id)
    if get_provider('paynow') is None:
        return Response({'error': "PayNow is not enabled."}, status=status.HTTP_404_NOT_FOUND)
    return start_response(order, 'paynow')


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
               request=inline_serializer('CancelOrder', {'order_token': serializers.CharField()}),
               responses={200: inline_serializer('OrderCancelled', {'status': serializers.CharField()}),
                          403: Error, 404: Error, 409: Error})
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def cancel_order(request, order_id):
    order = get_object_or_404(Order, pk=order_id)
    if not services.check_order_token(order, request.data.get('order_token')):
        return Response({'error': "Not your order."}, status=status.HTTP_403_FORBIDDEN)
    if not services.cancel_order(order, reason="Cancelled by customer."):
        return Response({'error': "Only unpaid orders can be cancelled."}, status=status.HTTP_409_CONFLICT)
    return Response({'status': Order.Status.CANCELLED})


@extend_schema(summary="Payment notification from a payment provider",
               description="Each provider posts here with its own format and signature, checked by that provider's code.",
               request=None, responses={200: OpenApiResponse(description="Processed"), 400: Error, 404: Error})
@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def payment_webhook(request, method):
    provider = PROVIDERS.get(method)
    try:
        events = provider.parse_webhook(request) if provider else None
    except NotImplementedError:
        events = None
    except ValueError as e:
        logger.warning("Rejected %s webhook: %s", method, e)
        return Response({'error': "Invalid notification."}, status=status.HTTP_400_BAD_REQUEST)
    if events is None:
        return Response({'error': "No notifications for this payment method."}, status=status.HTTP_404_NOT_FOUND)
    for event, order_id, provider_ref, amount in events:
        order = Order.objects.filter(pk=order_id).first()
        if order is None:
            logger.error("%s notification for unknown order %s (%s)", method, order_id, provider_ref)
        elif event == SUCCEEDED:
            services.confirm_payment(order, method, amount, provider_ref)
        elif event == FAILED:
            services.payment_failed(order, method, provider_ref)
    return Response({'ok': True})
