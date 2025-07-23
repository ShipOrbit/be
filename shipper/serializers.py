from rest_framework import serializers
from .models import (
    Shipment,
    Location,
    PriceCalculation,
    ShipmentStatusHistory,
    ShippingNeeds,
    City,
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
    """Serializer for listing shipments with pickup and dropoff info"""

    total_price = serializers.ReadOnlyField()

    # Custom fields
    pickup = serializers.SerializerMethodField()
    dropoff = serializers.SerializerMethodField()

    class Meta:
        model = Shipment
        fields = [
            "id",
            "status",
            "pickup",
            "dropoff",
            "base_price",
            "total_price",
            "miles",
            "equipment",
            "created_at",
        ]

    def get_pickup(self, obj):
        pickup = obj.locations.filter(location_type="pickup").first()
        if not pickup:
            return None
        return ListLocationSerializer(pickup).data

    def get_dropoff(self, obj):
        dropoff = obj.locations.filter(location_type="dropoff").first()
        if not dropoff:
            return None
        return ListLocationSerializer(dropoff).data


class ShipmentDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for shipment CRUD operations"""

    total_price = serializers.ReadOnlyField()
    pickup = serializers.SerializerMethodField()
    dropoff = serializers.SerializerMethodField()

    class Meta:
        model = Shipment
        fields = [
            "id",
            "status",
            "equipment",
            "pickup",
            "dropoff",
            "base_price",
            "driver_assist",
            "driver_assist_fee",
            "miles",
            "min_transit_time",
            "reference_number",
            "weight",
            "commodity",
            "packaging",
            "packaging_type",
            "total_price",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def get_pickup(self, obj):
        pickup = obj.locations.filter(location_type="pickup").first()
        if not pickup:
            return None
        return ListLocationSerializer(pickup).data

    def get_dropoff(self, obj):
        dropoff = obj.locations.filter(location_type="dropoff").first()
        if not dropoff:
            return None
        return ListLocationSerializer(dropoff).data

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


class LocationCreateSerializer(serializers.Serializer):
    city = serializers.PrimaryKeyRelatedField(queryset=City.objects.all())
    date = serializers.DateField()


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = ["id", "name", "region_code"]


class ListLocationSerializer(serializers.ModelSerializer):
    city = CitySerializer(read_only=True)  # Get full nested city details

    class Meta:
        model = Location
        exclude = ["shipment", "id", "created_at"]
        # Or: fields = "__all__" if you want everything


class ShipmentCreateSerializer(serializers.ModelSerializer):
    pickup = LocationCreateSerializer()
    dropoff = LocationCreateSerializer()

    class Meta:
        model = Shipment
        fields = ["equipment", "pickup", "dropoff"]

    def create(self, validated_data):
        pickup_data = validated_data.pop("pickup")
        dropoff_data = validated_data.pop("dropoff")
        equipment = validated_data.get("equipment")

        pickup_city = pickup_data["city"]
        dropoff_city = dropoff_data["city"]
        try:
            price_data = PriceCalculation.objects.get(
                pickup_location=pickup_city,
                dropoff_location=dropoff_city,
                equipment=equipment,
            )
        except PriceCalculation.DoesNotExist:
            raise serializers.ValidationError(
                "Price calculation for this route and equipment does not exist."
            )

        # Create Shipment
        shipment = Shipment.objects.create(
            user=self.context["request"].user,
            **validated_data,
            base_price=price_data.base_price,
            miles=price_data.miles,
            min_transit_time=price_data.min_transit_time,
        )

        # Create Pickup Location
        Location.objects.create(
            shipment=shipment,
            location_type="pickup",
            city=pickup_data["city"],
            date=pickup_data["date"],
        )

        # Create Dropoff Location
        Location.objects.create(
            shipment=shipment,
            location_type="dropoff",
            city=dropoff_data["city"],
            date=dropoff_data["date"],
        )

        return shipment


class ShipmentUpdateStep2Serializer(serializers.ModelSerializer):
    """Serializer for updating shipment with facility info (Step 2)"""

    pickup = LocationSerializer(write_only=True, required=False)
    dropoff = LocationSerializer(write_only=True, required=False)

    class Meta:
        model = Shipment
        fields = [
            "driver_assist",
            "pickup",
            "dropoff",
        ]

    def update(self, instance, validated_data):
        # Extract location data
        pickup_data = validated_data.pop("pickup", None)
        dropoff_data = validated_data.pop("dropoff", None)

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


class CityDataSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    region_code = serializers.CharField(required=False, allow_blank=True)
    country_code = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()


class DistancePriceRequestSerializer(serializers.Serializer):
    """Serializer for distance/price calculation requests"""

    pickup_location = CityDataSerializer()
    dropoff_location = CityDataSerializer()
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
