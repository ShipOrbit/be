import stripe
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from be import settings

from .models import (
    Invoice,
    Payment,
)
from .serializers import (
    InvoiceCreateSerializer,
    InvoiceSerializer,
    PaymentConfirmSerializer,
    PaymentIntentCreateSerializer,
    PaymentSerializer,
)


class InvoiceListCreateView(generics.ListCreateAPIView):
    """
    GET: List user's invoices
    POST: Create new invoice for a shipment
    """

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return InvoiceCreateSerializer
        return InvoiceSerializer

    def get_queryset(self):
        return Invoice.objects.filter(shipment__user=self.request.user).select_related(
            "shipment"
        )


class InvoiceDetailView(generics.RetrieveAPIView):
    """
    GET: Retrieve invoice details
    """

    permission_classes = [IsAuthenticated]
    serializer_class = InvoiceSerializer

    def get_queryset(self):
        return Invoice.objects.filter(shipment__user=self.request.user)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_payment_intent(request):
    """
    Create a PaymentIntent for an invoice using Stripe PaymentMethod ID
    """
    serializer = PaymentIntentCreateSerializer(
        data=request.data, context={"request": request}
    )

    if serializer.is_valid():
        result = serializer.save()
        payment_serializer = PaymentSerializer(result["payment"])

        return Response(
            {
                "payment": payment_serializer.data,
                "client_secret": result["client_secret"],
                "status": result["status"],
                "requires_action": result["requires_action"],
                "next_action": result.get("next_action"),
                "message": "Payment intent created successfully",
            },
            status=status.HTTP_201_CREATED,
        )

    return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_payment_intent(request):
    """
    Confirm a PaymentIntent that requires additional action
    """
    serializer = PaymentConfirmSerializer(
        data=request.data, context={"request": request}
    )

    if serializer.is_valid():
        result = serializer.confirm_payment()
        payment_serializer = PaymentSerializer(result["payment"])

        return Response(
            {
                "payment": payment_serializer.data,
                "status": result["status"],
                "requires_action": result["requires_action"],
                "next_action": result.get("next_action"),
                "message": "Payment confirmed successfully",
            }
        )

    return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_history(request):
    """
    Get user's payment history
    """
    payments = (
        Payment.objects.filter(invoice__shipment__user=request.user)
        .select_related("invoice", "invoice__shipment")
        .order_by("-created_at")
    )

    serializer = PaymentSerializer(payments, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def payment_status(request, payment_intent_id):
    """
    Get payment status from Stripe
    """
    try:
        payment = Payment.objects.get(
            stripe_payment_intent_id=payment_intent_id,
            invoice__shipment__user=request.user,
        )

        # Get latest status from Stripe
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)

        # Update local status if different
        stripe_status_map = {
            "requires_payment_method": "failed",
            "requires_confirmation": "pending",
            "requires_action": "requires_action",
            "processing": "processing",
            "succeeded": "succeeded",
            "canceled": "cancelled",
        }

        new_status = stripe_status_map.get(intent.status, "pending")
        if payment.status != new_status:
            payment.status = new_status
            payment.save()

            # Handle successful payment
            if new_status == "succeeded" and payment.invoice.status != "paid":
                payment.invoice.status = "paid"
                payment.invoice.paid_at = timezone.now()
                payment.invoice.save()

                payment.invoice.shipment.status = "inprogress"
                payment.invoice.shipment.save()

        return Response(
            {
                "payment_intent_id": payment_intent_id,
                "status": intent.status,
                "local_status": payment.status,
                "requires_action": intent.status
                in ["requires_action", "requires_source_action"],
            }
        )

    except Payment.DoesNotExist:
        return Response(
            {"error": "Payment not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except stripe.error.StripeError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
def stripe_webhook(request):
    """
    Handle Stripe webhooks for payment status updates
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        return Response({"error": "Invalid payload"}, status=400)
    except stripe.error.SignatureVerificationError:
        return Response({"error": "Invalid signature"}, status=400)

    # Handle the event
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]

        try:
            payment = Payment.objects.get(stripe_payment_intent_id=payment_intent["id"])
            payment.status = "succeeded"
            payment.save()

            # Update invoice and shipment
            invoice = payment.invoice
            invoice.status = "paid"
            invoice.paid_at = timezone.now()
            invoice.save()

            invoice.shipment.status = "inprogress"
            invoice.shipment.save()

        except Payment.DoesNotExist:
            pass

    elif event["type"] == "payment_intent.payment_failed":
        payment_intent = event["data"]["object"]

        try:
            payment = Payment.objects.get(stripe_payment_intent_id=payment_intent["id"])
            payment.status = "failed"
            payment.failure_reason = payment_intent.get("last_payment_error", {}).get(
                "message", "Unknown error"
            )
            payment.save()

        except Payment.DoesNotExist:
            pass

    elif event["type"] == "payment_intent.requires_action":
        payment_intent = event["data"]["object"]

        try:
            payment = Payment.objects.get(stripe_payment_intent_id=payment_intent["id"])
            payment.status = "requires_action"
            payment.save()

        except Payment.DoesNotExist:
            pass

    return Response({"status": "success"})
