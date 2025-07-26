from decimal import Decimal

from django.db import models


class Invoice(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    shipment = models.OneToOneField(
        "shipper.Shipment", on_delete=models.CASCADE, related_name="invoice"
    )
    invoice_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    driver_assist_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.status}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Generate invoice number
            import uuid

            self.invoice_number = f"INV-{uuid.uuid4().hex[:8].upper()}"

        # Calculate total amount
        self.total_amount = self.amount + self.driver_assist_fee
        super().save(*args, **kwargs)

    class Meta:
        db_table = "invoices"
        verbose_name_plural = "invoices"


class Payment(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("requires_action", "Requires Action"),
    ]

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="payments"
    )
    stripe_payment_intent_id = models.CharField(max_length=255, unique=True, null=True)
    stripe_payment_method_id = models.CharField(
        max_length=255, null=True
    )  # Store for reference only
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    failure_reason = models.TextField(blank=True)
    client_secret = models.CharField(
        max_length=255, blank=True
    )  # For frontend confirmation
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment {self.id} - {self.status}"

    class Meta:
        db_table = "payments"
        verbose_name_plural = "payments"
