import uuid

from django.db import models

from accounts.models import User


class City(models.Model):
    id = models.BigIntegerField(primary_key=True)
    name = models.CharField(max_length=255)
    region_code = models.CharField(max_length=20, blank=True)
    country_code = models.CharField(max_length=20, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "cities"
        verbose_name_plural = "cities"

    def __str__(self):
        return f"{self.name} ({self.region_code}, {self.country_code})"


class Company(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="company")
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=50, null=True)
    primary_ships_country = models.CharField(
        max_length=2,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "companies"
        verbose_name_plural = "companies"


class ShippingNeeds(models.Model):
    MODE_CHOICES = [
        ("FTL", "Full Truckload (FTL)"),
        ("LTL", "Less-than-Truckload (LTL)"),
    ]

    TRAILER_TYPE_CHOICES = [
        ("dryVan", "53' Dry Van"),
        ("reefer", "53' Reefer"),
        ("flatbed", "Flatbed"),
    ]

    AVERAGE_FTL_CHOICES = [
        ("1-5", "1-5"),
        ("5-10", "5-10"),
        ("15-25", "15-25"),
        ("30-45", "30-45"),
        ("50-70", "50-70"),
        ("80-100", "80-100"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="shipping_needs"
    )
    mode = models.JSONField(default=list)  # Store multiple modes as JSON array
    average_ftl = models.CharField(
        max_length=10, choices=AVERAGE_FTL_CHOICES, default="1-5"
    )
    trailer_type = models.JSONField(
        default=list
    )  # Store multiple trailer types as JSON array
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shipping_needs"
        verbose_name_plural = "shipping_needs"


class Shipment(models.Model):
    STATUS_CHOICES = [
        ("unfinished", "Unfinished"),
        ("inprogress", "In Progress"),
        ("upcoming", "Upcoming"),
        ("past", "Past"),
    ]

    EQUIPMENT_CHOICES = [
        ("dryVan", "Dry Van"),
        ("reefer", "Reefer"),
    ]

    # Basic Info
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="shipments")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="unfinished"
    )
    equipment = models.CharField(
        max_length=20, choices=EQUIPMENT_CHOICES, default="dryVan"
    )

    # Locations
    pickup_location = models.CharField(max_length=200)
    dropoff_location = models.CharField(max_length=200)

    # Dates
    pickup_date = models.DateField()
    dropoff_date = models.DateField()

    # Pricing
    base_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    driver_assist = models.BooleanField(default=False)
    driver_assist_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=150.00
    )

    # Distance and Transit
    miles = models.PositiveIntegerField(null=True, blank=True)
    min_transit_time = models.PositiveIntegerField(null=True, blank=True)  # in days

    # Shipment Details (Step 3)
    reference_number = models.CharField(max_length=500, blank=True)
    weight = models.PositiveIntegerField(null=True, blank=True)
    commodity = models.CharField(max_length=500, blank=True)
    packaging = models.PositiveIntegerField(null=True, blank=True)
    packaging_type = models.CharField(max_length=500, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Shipment {self.id} - {self.pickup_location} to {self.dropoff_location}"

    @property
    def total_price(self):
        if self.base_price:
            return self.base_price + (
                self.driver_assist_fee if self.driver_assist else 0
            )
        return 0


class Location(models.Model):
    """Store location details for pickup and dropoff"""

    shipment = models.ForeignKey(
        Shipment, on_delete=models.CASCADE, related_name="locations"
    )
    location_type = models.CharField(
        max_length=20, choices=[("pickup", "Pickup"), ("dropoff", "Dropoff")]
    )

    # Facility Info
    facility_name = models.CharField(max_length=200, blank=True)
    facility_address = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20, blank=True)

    # Contact Info
    contact_name = models.CharField(max_length=200, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    # Scheduling
    SCHEDULING_CHOICES = [
        ("first_come", "First come, first served"),
        ("already_scheduled", "Appointment already scheduled"),
        ("to_be_scheduled", "Appointment to be scheduled by ShipOrbit"),
    ]
    scheduling_preference = models.CharField(
        max_length=20, choices=SCHEDULING_CHOICES, default="first_come"
    )

    # Additional Details (Step 3)
    location_number = models.CharField(
        max_length=500, blank=True
    )  # pickup_number or dropoff_number
    additional_notes = models.TextField(max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["shipment", "location_type"]

    def __str__(self):
        return f"{self.location_type.title()} - {self.city}, {self.state}"


class PriceCalculation(models.Model):
    """Store price calculations for different routes"""

    pickup_location = models.ForeignKey(
        City, related_name="pickup_location", on_delete=models.CASCADE, null=True
    )
    dropoff_location = models.ForeignKey(
        City, related_name="dropoff_location", on_delete=models.CASCADE, null=True
    )
    equipment = models.CharField(max_length=20, choices=Shipment.EQUIPMENT_CHOICES)

    # Distance and pricing data
    miles = models.PositiveIntegerField()
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    min_transit_time = models.PositiveIntegerField()  # in days

    # Rate calculation factors
    rate_per_mile = models.DecimalField(max_digits=5, decimal_places=2, default=2.50)
    base_fee = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["pickup_location", "dropoff_location", "equipment"]
        db_table = "price_calculations"
        verbose_name_plural = "price_calculations"

    def __str__(self):
        return f"{self.pickup_location} to {self.dropoff_location} - {self.miles}mi - ${self.base_price}"


class ShipmentStatusHistory(models.Model):
    """Track status changes for shipments"""

    shipment = models.ForeignKey(
        Shipment, on_delete=models.CASCADE, related_name="status_history"
    )
    old_status = models.CharField(max_length=20, choices=Shipment.STATUS_CHOICES)
    new_status = models.CharField(max_length=20, choices=Shipment.STATUS_CHOICES)
    changed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    change_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Shipment {self.shipment.id}: {self.old_status} -> {self.new_status}"
