from datetime import timedelta
from decimal import Decimal

import stripe
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.serializers import UserSerializer
from be import settings
from shipper.util.calculate_base_price import calculate_base_price
from shipper.util.calculate_distance import calculate_distance
from shipper.util.calculate_transit_time import calculate_transit_time
from shipper.util.get_or_create_city import get_or_create_city
from utils.geodb import geo_api_get

from .models import (
    Invoice,
    Location,
    Payment,
    PriceCalculation,
    Shipment,
    ShipmentStatusHistory,
)
from .serializers import (
    DistancePriceRequestSerializer,
    DistancePriceResponseSerializer,
    InvoiceCreateSerializer,
    InvoiceSerializer,
    LocationSerializer,
    PaymentConfirmSerializer,
    PaymentIntentCreateSerializer,
    PaymentSerializer,
    PriceCalculationSerializer,
    ShipmentCreateSerializer,
    ShipmentDetailSerializer,
    ShipmentListSerializer,
    ShipmentStatusHistorySerializer,
    ShipmentUpdateStep2Serializer,
    ShipmentUpdateStep3Serializer,
    ShippingNeedsSerializer,
)


class ShipmentListCreateView(generics.ListCreateAPIView):
    """
    GET: List user's shipments with optional filtering
    POST: Create new shipment with pickup and dropoff locations
    """

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ShipmentCreateSerializer
        return ShipmentListSerializer

    def get_queryset(self):
        queryset = Shipment.objects.filter(user=self.request.user)
        status_filter = self.request.query_params.get("status", None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        shipment = serializer.save()

        return Response(
            {"id": shipment.id},
            status=status.HTTP_201_CREATED,
        )


class ShipmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: Retrieve shipment details
    PUT/PATCH: Update shipment
    DELETE: Delete shipment
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ShipmentDetailSerializer

    def get_queryset(self):
        return Shipment.objects.filter(user=self.request.user)


class ShipmentUpdateStep2View(generics.UpdateAPIView):
    """Update shipment with facility information (Step 2)"""

    permission_classes = [IsAuthenticated]
    serializer_class = ShipmentUpdateStep2Serializer

    def get_queryset(self):
        return Shipment.objects.filter(user=self.request.user)


class ShipmentUpdateStep3View(generics.UpdateAPIView):
    """Finalize shipment with shipping details (Step 3)"""

    permission_classes = [IsAuthenticated]
    serializer_class = ShipmentUpdateStep3Serializer

    def get_queryset(self):
        return Shipment.objects.filter(user=self.request.user)


@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def calculate_distance_price(request):
    """
    Calculate distance and pricing between two locations
    """
    serializer = DistancePriceRequestSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )

    pickup_location_data = serializer.validated_data["pickup_location"]
    dropoff_location_data = serializer.validated_data["dropoff_location"]
    equipment = serializer.validated_data["equipment"]
    try:
        pickup_city = get_or_create_city(pickup_location_data)
        dropoff_city = get_or_create_city(dropoff_location_data)

        # Check if we have a cached calculation
        cached_calculation = PriceCalculation.objects.filter(
            pickup_location=pickup_city,
            dropoff_location=dropoff_city,
            equipment=equipment,
        ).first()

        if cached_calculation:
            response_data = {
                "pickup_location": pickup_city,
                "dropoff_location": dropoff_city,
                "equipment": equipment,
                "miles": cached_calculation.miles,
                "base_price": cached_calculation.base_price,
                "min_transit_time": cached_calculation.min_transit_time,
                "driver_assist_fee": Decimal("150.00"),
                "total_price_with_assist": cached_calculation.base_price
                + Decimal("150.00"),
            }
            response_serializer = DistancePriceResponseSerializer(response_data)
            return Response(response_serializer.data)

        distance_miles = calculate_distance(pickup_location_data, dropoff_location_data)
        base_price = calculate_base_price(distance_miles, equipment)
        min_transit_days = calculate_transit_time(distance_miles)

        # Cache the calculation
        PriceCalculation.objects.create(
            pickup_location=pickup_city,
            dropoff_location=dropoff_city,
            equipment=equipment,
            miles=distance_miles,
            base_price=base_price,
            min_transit_time=min_transit_days,
        )

        response_data = {
            "pickup_location": pickup_location_data,
            "dropoff_location": dropoff_location_data,
            "equipment": equipment,
            "miles": distance_miles,
            "base_price": base_price,
            "min_transit_time": min_transit_days,
            "driver_assist_fee": Decimal("150.00"),
            "total_price_with_assist": base_price + Decimal("150.00"),
        }

        response_serializer = DistancePriceResponseSerializer(response_data)
        return Response(response_serializer.data)

    except Exception as e:
        return Response(
            {"message": f"Unable to calculate distance and price: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_shipment_status(request, shipment_id):
    """Update shipment status and log the change"""
    shipment = get_object_or_404(Shipment, id=shipment_id, user=request.user)
    new_status = request.data.get("status")
    reason = request.data.get("reason", "")

    if new_status not in dict(Shipment.STATUS_CHOICES):
        return Response({"error": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST)

    old_status = shipment.status

    if old_status != new_status:
        # Log status change
        ShipmentStatusHistory.objects.create(
            shipment=shipment,
            old_status=old_status,
            new_status=new_status,
            changed_by=request.user,
            change_reason=reason,
        )

        # Update shipment
        shipment.status = new_status
        shipment.save()

    serializer = ShipmentDetailSerializer(shipment)
    return Response(serializer.data)


class ShipmentStatusHistoryView(generics.ListAPIView):
    """Get status history for a shipment"""

    permission_classes = [IsAuthenticated]
    serializer_class = ShipmentStatusHistorySerializer

    def get_queryset(self):
        shipment_id = self.kwargs["shipment_id"]
        # Ensure user owns the shipment
        shipment = get_object_or_404(Shipment, id=shipment_id, user=self.request.user)
        return ShipmentStatusHistory.objects.filter(shipment=shipment)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def shipment_dashboard(request):
    """Get dashboard data for user's shipments"""
    user_shipments = Shipment.objects.filter(user=request.user)

    # Count by status
    status_counts = {
        "unfinished": user_shipments.filter(status="unfinished").count(),
        "upcoming": user_shipments.filter(status="upcoming").count(),
        "inprogress": user_shipments.filter(status="inprogress").count(),
        "past": user_shipments.filter(status="past").count(),
    }

    # Recent shipments
    recent_shipments = user_shipments[:5]
    recent_serializer = ShipmentListSerializer(recent_shipments, many=True)

    # Upcoming shipments (next 30 days)
    upcoming_date = timezone.now().date() + timedelta(days=30)
    upcoming_shipments = user_shipments.filter(
        status__in=["upcoming", "inprogress"], pickup_date__lte=upcoming_date
    ).order_by("pickup_date")[:5]
    upcoming_serializer = ShipmentListSerializer(upcoming_shipments, many=True)

    return Response(
        {
            "status_counts": status_counts,
            "total_shipments": user_shipments.count(),
            "recent_shipments": recent_serializer.data,
            "upcoming_shipments": upcoming_serializer.data,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def save_draft_shipment(request, shipment_id):
    """Save shipment as draft to finish later"""
    shipment = get_object_or_404(Shipment, id=shipment_id, user=request.user)

    # Update any provided fields
    serializer = ShipmentDetailSerializer(shipment, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Draft saved successfully"})

    return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def price_calculation_history(request):
    """Get user's price calculation history"""
    calculations = PriceCalculation.objects.all().order_by("-created_at")[:20]
    serializer = PriceCalculationSerializer(calculations, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_regions(request):
    serializer = UserSerializer(request.user)
    country_code = serializer.data["company"]["primary_ships_country"]
    name_prefix = request.GET.get("name", "")
    try:
        data = geo_api_get(
            f"countries/{country_code}/regions", params={"namePrefix": name_prefix}
        )
        return Response(
            data.get("data", []),
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def search_cities(request):
    name_prefix = request.GET.get("name_prefix", "")
    try:
        response = geo_api_get("cities", params={"namePrefix": name_prefix})
        raw_data = response.get("data", [])

        # Transform the data
        transformed_data = []
        for item in raw_data:
            transformed_item = {
                "id": item.get("id"),
                "name": item.get("name"),
                "city": item.get("city"),
                "country_code": item.get("countryCode"),
                "region_code": item.get("regionCode"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
            }
            transformed_data.append(transformed_item)

        return Response(transformed_data)

    except Exception as e:
        return Response(
            {"message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def createShippingNeeds(request):
    """
    Handle shipping needs registration (step 2)
    """
    serializer = ShippingNeedsSerializer(
        data=request.data, context={"request": request}
    )
    if serializer.is_valid():
        serializer.save()

        return Response(
            {
                "message": "Shipping needs saved successfully",
                "redirect_to_verification": True,
            },
            status=status.HTTP_201_CREATED,
        )

    return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


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
