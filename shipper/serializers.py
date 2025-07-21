from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Shipment,
    Location,
    PriceCalculation,
    ShipmentStatusHistory,
    ShippingNeeds,
)
import re


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = [
            "id",
            "location_type",
            "facility_name",
            "facility_address",
            "city",
            "state",
            "zip_code",
            "contact_name",
            "phone_number",
            "email",
            "scheduling_preference",
            "location_number",
            "additional_notes",
            "created_at",
        ]

    def validate_phone_number(self, value):
        if value:
            # Basic phone number validation
            phone_pattern = r"^\(?(\d{3})\)?[-.\s]?(\d{3})[-.\s]?(\d{4})$"
            if not re.match(phone_pattern, value):
                raise serializers.ValidationError("Invalid phone number format")
        return value

    def validate_zip_code(self, value):
        if value:
            # US ZIP code validation
            zip_pattern = r"^\d{5}(?:[-\s]\d{4})?$"
            if not re.match(zip_pattern, value):
                raise serializers.ValidationError("Invalid ZIP code format")
        return value


class ShipmentListSerializer(serializers.ModelSerializer):
    """Serializer for shipment list view"""

    total_price = serializers.ReadOnlyField()

    class Meta:
        model = Shipment
        fields = [
            "id",
            "status",
            "pickup_location",
            "dropoff_location",
            "pickup_date",
            "dropoff_date",
            "base_price",
            "total_price",
            "miles",
            "equipment",
            "created_at",
        ]


class ShipmentDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for shipment CRUD operations"""

    locations = LocationSerializer(many=True, read_only=True)
    total_price = serializers.ReadOnlyField()
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Shipment
        fields = [
            "id",
            "user",
            "status",
            "equipment",
            "pickup_location",
            "dropoff_location",
            "pickup_date",
            "dropoff_date",
            "base_price",
            "driver_assist",
            "driver_assist_fee",
            "miles",
            "min_transit_time",
            "covid_relief",
            "reference_number",
            "weight",
            "commodity",
            "packaging",
            "packaging_type",
            "total_price",
            "locations",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def validate(self, data):
        """Cross-field validation"""
        pickup_date = data.get("pickup_date")
        dropoff_date = data.get("dropoff_date")

        if pickup_date and dropoff_date:
            if pickup_date >= dropoff_date:
                raise serializers.ValidationError(
                    "Dropoff date must be after pickup date"
                )

        return data


class ShipmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new shipments (Step 1)"""

    class Meta:
        model = Shipment
        fields = [
            "equipment",
            "pickup_location",
            "dropoff_location",
            "pickup_date",
            "dropoff_date",
        ]

    def validate_pickup_location(self, value):
        # Validate format: "City, State"
        location_pattern = r"^[a-zA-Z\s\.]{1,50},\s*[a-zA-Z\s]{2,}$"
        if not re.match(location_pattern, value.strip()):
            raise serializers.ValidationError(
                "Location must be in format: 'City, State'"
            )
        return value.strip()

    def validate_dropoff_location(self, value):
        # Same validation as pickup_location
        location_pattern = r"^[a-zA-Z\s\.]{1,50},\s*[a-zA-Z\s]{2,}$"
        if not re.match(location_pattern, value.strip()):
            raise serializers.ValidationError(
                "Location must be in format: 'City, State'"
            )
        return value.strip()


class ShipmentUpdateStep2Serializer(serializers.ModelSerializer):
    """Serializer for updating shipment with facility info (Step 2)"""

    pickup_location_data = LocationSerializer(write_only=True, required=False)
    dropoff_location_data = LocationSerializer(write_only=True, required=False)

    class Meta:
        model = Shipment
        fields = [
            "covid_relief",
            "driver_assist",
            "pickup_location_data",
            "dropoff_location_data",
        ]

    def update(self, instance, validated_data):
        # Extract location data
        pickup_data = validated_data.pop("pickup_location_data", None)
        dropoff_data = validated_data.pop("dropoff_location_data", None)

        # Update shipment fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update or create location objects
        if pickup_data:
            pickup_data["location_type"] = "pickup"
            pickup_location, created = Location.objects.update_or_create(
                shipment=instance, location_type="pickup", defaults=pickup_data
            )

        if dropoff_data:
            dropoff_data["location_type"] = "dropoff"
            dropoff_location, created = Location.objects.update_or_create(
                shipment=instance, location_type="dropoff", defaults=dropoff_data
            )

        return instance


class ShipmentUpdateStep3Serializer(serializers.ModelSerializer):
    """Serializer for finalizing shipment details (Step 3)"""

    pickup_number = serializers.CharField(write_only=True, required=False)
    pickup_notes = serializers.CharField(write_only=True, required=False)
    dropoff_number = serializers.CharField(write_only=True, required=False)
    dropoff_notes = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Shipment
        fields = [
            "reference_number",
            "weight",
            "commodity",
            "packaging",
            "packaging_type",
            "pickup_number",
            "pickup_notes",
            "dropoff_number",
            "dropoff_notes",
        ]

    def validate_weight(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("Weight must be at least 1")
        return value

    def validate_packaging(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError("Packaging count must be at least 1")
        return value

    def update(self, instance, validated_data):
        # Extract location-specific data
        pickup_number = validated_data.pop("pickup_number", None)
        pickup_notes = validated_data.pop("pickup_notes", None)
        dropoff_number = validated_data.pop("dropoff_number", None)
        dropoff_notes = validated_data.pop("dropoff_notes", None)

        # Update shipment fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Mark as in progress if all required fields are filled
        if all(
            [
                instance.reference_number,
                instance.weight,
                instance.commodity,
                instance.packaging,
                instance.packaging_type,
            ]
        ):
            instance.status = "upcoming"

        instance.save()

        # Update location details
        if pickup_number or pickup_notes:
            Location.objects.filter(shipment=instance, location_type="pickup").update(
                location_number=pickup_number or "", additional_notes=pickup_notes or ""
            )

        if dropoff_number or dropoff_notes:
            Location.objects.filter(shipment=instance, location_type="dropoff").update(
                location_number=dropoff_number or "",
                additional_notes=dropoff_notes or "",
            )

        return instance


class PriceCalculationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceCalculation
        fields = "__all__"


class DistancePriceRequestSerializer(serializers.Serializer):
    """Serializer for distance/price calculation requests"""

    pickup_location = serializers.CharField(max_length=200)
    dropoff_location = serializers.CharField(max_length=200)
    equipment = serializers.ChoiceField(
        choices=Shipment.EQUIPMENT_CHOICES, default="dryVan"
    )


class DistancePriceResponseSerializer(serializers.Serializer):
    """Serializer for distance/price calculation response"""

    pickup_location = serializers.CharField()
    dropoff_location = serializers.CharField()
    equipment = serializers.CharField()
    miles = serializers.IntegerField()
    base_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    min_transit_time = serializers.IntegerField()
    driver_assist_fee = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_price_with_assist = serializers.DecimalField(max_digits=10, decimal_places=2)


class ShipmentStatusHistorySerializer(serializers.ModelSerializer):
    changed_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = ShipmentStatusHistory
        fields = "__all__"
        read_only_fields = ["changed_by", "created_at"]


class ShippingNeedsSerializer(serializers.ModelSerializer):
    company_location = serializers.CharField(write_only=True)
    mode = serializers.ListField(child=serializers.CharField())
    trailer_type = serializers.ListField(child=serializers.CharField())

    class Meta:
        model = ShippingNeeds
        fields = ["mode", "average_ftl", "trailer_type", "company_location"]

    def create(self, validated_data):
        user = self.context["request"].user
        company_location = validated_data.pop("company_location")

        # Update company location
        company = user.company
        company.location = company_location
        company.save()

        # Create shipping needs
        shipping_needs = ShippingNeeds.objects.create(
            user=user,
            mode=validated_data["mode"],
            average_ftl=validated_data["average_ftl"],
            trailer_type=validated_data["trailer_type"],
        )

        return shipping_needs
