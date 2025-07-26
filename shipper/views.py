from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.serializers import UserSerializer
from shipper.util.calculate_base_price import calculate_base_price
from shipper.util.calculate_distance import calculate_distance
from shipper.util.calculate_transit_time import calculate_transit_time
from shipper.util.get_or_create_city import get_or_create_city
from utils.geodb import geo_api_get

from .models import (
    PriceCalculation,
    Shipment,
)
from .serializers import (
    DistancePriceRequestSerializer,
    DistancePriceResponseSerializer,
    ShipmentCreateSerializer,
    ShipmentDetailSerializer,
    ShipmentListSerializer,
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
