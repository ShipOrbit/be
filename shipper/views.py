import math
from datetime import timedelta
from decimal import Decimal

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.serializers import UserSerializer
from utils.geodb import geo_api_get

from .models import Location, PriceCalculation, Shipment, ShipmentStatusHistory
from .serializers import (
    DistancePriceRequestSerializer,
    DistancePriceResponseSerializer,
    LocationSerializer,
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
    GET: List user's shipments with filtering by status
    POST: Create new shipment (Step 1)
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

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


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
@permission_classes([IsAuthenticated])
def calculate_distance_price(request):
    """
    Calculate distance and pricing between two locations
    This replaces the Google Maps API functionality from the original app
    """
    serializer = DistancePriceRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )

    pickup_location = serializer.validated_data["pickup_location"]
    dropoff_location = serializer.validated_data["dropoff_location"]
    equipment = serializer.validated_data["equipment"]

    # Check if we have a cached calculation
    cached_calculation = PriceCalculation.objects.filter(
        pickup_location=pickup_location,
        dropoff_location=dropoff_location,
        equipment=equipment,
    ).first()

    if cached_calculation:
        response_data = {
            "pickup_location": pickup_location,
            "dropoff_location": dropoff_location,
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

    # Calculate new distance and pricing
    try:
        # This would integrate with a real geocoding/distance API
        # For now, using mock calculation based on location names
        distance_miles = _calculate_mock_distance(pickup_location, dropoff_location)
        base_price = _calculate_base_price(distance_miles, equipment)
        min_transit_days = _calculate_transit_time(distance_miles)

        # Cache the calculation
        PriceCalculation.objects.create(
            pickup_location=pickup_location,
            dropoff_location=dropoff_location,
            equipment=equipment,
            miles=distance_miles,
            base_price=base_price,
            min_transit_time=min_transit_days,
        )

        response_data = {
            "pickup_location": pickup_location,
            "dropoff_location": dropoff_location,
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
            {"error": f"Unable to calculate distance and price: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def _calculate_mock_distance(pickup, dropoff):
    """
    Mock distance calculation - in production, this would use Google Maps API
    or another geocoding service
    """
    # Extract state codes for rough distance estimation
    pickup_parts = pickup.split(",")
    dropoff_parts = dropoff.split(",")

    if len(pickup_parts) < 2 or len(dropoff_parts) < 2:
        return 500  # Default distance

    pickup_state = pickup_parts[1].strip()
    dropoff_state = dropoff_parts[1].strip()

    # Very basic state-to-state distance mapping (simplified)
    state_distances = {
        ("CA", "NY"): 2900,
        ("NY", "CA"): 2900,
        ("FL", "WA"): 3100,
        ("WA", "FL"): 3100,
        ("TX", "ME"): 2100,
        ("ME", "TX"): 2100,
    }

    # Same state
    if pickup_state == dropoff_state:
        return 150

    # Check predefined distances
    key = (pickup_state, dropoff_state)
    if key in state_distances:
        return state_distances[key]

    # Default calculation based on hash of locations
    hash_value = hash(pickup + dropoff) % 2500
    return max(100, abs(hash_value))


def _calculate_base_price(miles, equipment):
    """Calculate base price based on distance and equipment type"""
    base_rate_per_mile = Decimal("2.50")

    # Equipment multiplier
    equipment_multipliers = {
        "dryVan": Decimal("1.0"),
        "refeer": Decimal("1.3"),  # Reefer costs more
    }

    multiplier = equipment_multipliers.get(equipment, Decimal("1.0"))
    base_fee = Decimal("500.00")  # Minimum fee

    calculated_price = (Decimal(miles) * base_rate_per_mile * multiplier) + base_fee
    return round(calculated_price, 2)


def _calculate_transit_time(miles):
    """Calculate minimum transit time in days based on distance"""
    # Assume average speed of 500 miles per day including stops
    days = math.ceil(miles / 500)
    return max(1, days)


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


class LocationListView(generics.ListAPIView):
    """List locations for a specific shipment"""

    permission_classes = [IsAuthenticated]
    serializer_class = LocationSerializer

    def get_queryset(self):
        shipment_id = self.kwargs["shipment_id"]
        # Ensure user owns the shipment
        shipment = get_object_or_404(Shipment, id=shipment_id, user=self.request.user)
        return Location.objects.filter(shipment=shipment)


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
        print(e)
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_cities(request, country_code):
    name_prefix = request.GET.get("namePrefix", "")
    try:
        return City.objects.get(id=city_id)
    except City.DoesNotExist:
        # Step 2: Fetch from GeoDB API
        city_data = geo_api_get(f"cities/{city_id}/locatedIn")

        # Extract required data
        name = city_data["data"]["city"]
        region_code = city_data["data"].get("regionCode", "")
        country_code = city_data["data"].get("countryCode", "")

        # Step 3: Save to DB
        city = City.objects.create(
            id=city_id,
            name=name,
            region_code=region_code,
            country_code=country_code,
        )

        return city


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def search_cities(request):
    name_prefix = request.GET.get("name_prefix", "")
    try:
        data = geo_api_get("cities", params={"namePrefix": name_prefix})
        return Response(
            data.get("data", []),
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
