from decimal import Decimal

import stripe
from django.utils import timezone
from rest_framework import serializers

from be import settings
from shipper.models import Shipment

from .models import (
    Invoice,
    Payment,
)

stripe.api_key = settings.STRIPE_SECRET_KEY


class InvoiceSerializer(serializers.ModelSerializer):
    shipment_id = serializers.IntegerField(source="shipment.id", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "shipment_id",
            "invoice_number",
            "status",
            "amount",
            "driver_assist_fee",
            "total_amount",
            "created_at",
            "paid_at",
        ]
        read_only_fields = [
            "id",
            "invoice_number",
            "total_amount",
            "created_at",
            "paid_at",
        ]


class InvoiceCreateSerializer(serializers.Serializer):
    shipment_id = serializers.IntegerField()
    include_driver_assist = serializers.BooleanField(default=False)

    def validate_shipment_id(self, value):
        user = self.context["request"].user
        try:
            shipment = Shipment.objects.get(id=value, user=user)
            if hasattr(shipment, "invoice"):
                raise serializers.ValidationError(
                    "Invoice already exists for this shipment"
                )
            return value
        except Shipment.DoesNotExist:
            raise serializers.ValidationError("Shipment not found")

    def create(self, validated_data):
        user = self.context["request"].user
        shipment = Shipment.objects.get(id=validated_data["shipment_id"], user=user)
        include_driver_assist = validated_data.get("include_driver_assist", False)

        # Calculate amount from shipment
        amount = shipment.base_price or Decimal("0.00")
        driver_assist_fee = (
            Decimal("150.00") if include_driver_assist else Decimal("0.00")
        )

        invoice = Invoice.objects.create(
            shipment=shipment, amount=amount, driver_assist_fee=driver_assist_fee
        )

        return invoice


class PaymentIntentCreateSerializer(serializers.Serializer):
    shipment_id = serializers.UUIDField()  # Changed from invoice_id
    payment_method_id = serializers.CharField(
        max_length=255
    )  # Stripe PaymentMethod ID from frontend
    confirm = serializers.BooleanField(default=True)  # Whether to confirm immediately
    return_url = serializers.URLField(required=False)  # For 3D Secure redirects
    include_driver_assist = serializers.BooleanField(
        default=False
    )  # For invoice creation

    def validate_shipment_id(self, value):
        user = self.context["request"].user
        try:
            shipment = Shipment.objects.get(id=value, user=user)
            if shipment.status != "upcoming":
                raise serializers.ValidationError(
                    "Shipment must have 'upcoming' status to create payment"
                )
            if hasattr(shipment, "invoice") and shipment.invoice.status != "pending":
                raise serializers.ValidationError(
                    "Invoice must be in pending status to create payment intent"
                )
            return value
        except Shipment.DoesNotExist:
            raise serializers.ValidationError("Shipment not found")

    def create(self, validated_data):
        user = self.context["request"].user
        shipment = Shipment.objects.get(id=validated_data["shipment_id"], user=user)
        payment_method_id = validated_data["payment_method_id"]
        confirm = validated_data.get("confirm", True)
        return_url = validated_data.get(
            "return_url", "https://your-domain.com/payment-return"
        )
        include_driver_assist = validated_data.get("include_driver_assist", False)

        # Create invoice if it doesn't exist, otherwise use existing one
        if hasattr(shipment, "invoice"):
            invoice = shipment.invoice
        else:
            amount = shipment.base_price or Decimal("0.00")
            driver_assist_fee = (
                Decimal("150.00") if include_driver_assist else Decimal("0.00")
            )

            invoice = Invoice.objects.create(
                shipment=shipment,
                amount=amount,
                driver_assist_fee=driver_assist_fee,
                status="pending",  # Set status as pending
            )

        try:
            # Create Stripe customer if doesn't exist
            customer_id = None
            if hasattr(user, "stripe_customer_id") and user.stripe_customer_id:
                customer_id = user.stripe_customer_id
            else:
                customer = stripe.Customer.create(
                    email=user.email,
                    name=f"{user.first_name} {user.last_name}".strip() or user.username,
                )
                customer_id = customer.id
                # Save customer ID (you'll need to add this field to User model or UserProfile)
                user.stripe_customer_id = customer_id
                user.save()

            # Create PaymentIntent
            intent_data = {
                "amount": int(invoice.total_amount * 100),  # Convert to cents
                "currency": "usd",
                "customer": customer_id,
                "payment_method": payment_method_id,
                "metadata": {
                    "invoice_id": invoice.id,
                    "shipment_id": invoice.shipment.id,
                    "user_id": user.id,
                },
            }

            if confirm:
                intent_data.update(
                    {
                        "confirmation_method": "manual",
                        "confirm": True,
                        "return_url": return_url,
                    }
                )

            intent = stripe.PaymentIntent.create(**intent_data)

            # Create Payment record
            payment = Payment.objects.create(
                invoice=invoice,
                stripe_payment_intent_id=intent.id,
                stripe_payment_method_id=payment_method_id,
                amount=invoice.total_amount,
                status=self._map_stripe_status(intent.status),
                client_secret=intent.client_secret,
            )

            # Handle different payment intent statuses
            if intent.status == "succeeded":
                self._mark_payment_successful(payment, invoice)
            elif intent.status in ["requires_action", "requires_source_action"]:
                payment.status = "requires_action"
                payment.save()
            elif intent.status == "requires_payment_method":
                payment.status = "failed"
                payment.failure_reason = "Payment method declined"
                payment.save()

            return {
                "payment": payment,
                "client_secret": intent.client_secret,
                "status": intent.status,
                "requires_action": intent.status
                in ["requires_action", "requires_source_action"],
                "next_action": intent.next_action
                if hasattr(intent, "next_action")
                else None,
            }

        except stripe.error.StripeError as e:
            # Only delete the invoice if we just created it
            if not hasattr(shipment, "invoice") or shipment.invoice == invoice:
                invoice.delete()
            raise serializers.ValidationError(f"Payment failed: {str(e)}")

    def _mark_payment_successful(self, payment, invoice):
        """Mark payment and invoice as successful"""
        payment.status = "succeeded"
        payment.save()

        # Update invoice
        invoice.status = "paid"
        invoice.paid_at = timezone.now()
        invoice.save()

        # Update shipment status to in progress
        invoice.shipment.status = "inprogress"
        invoice.shipment.save()

    def _map_stripe_status(self, stripe_status):
        """Map Stripe status to our Payment model status"""
        status_mapping = {
            "requires_payment_method": "failed",
            "requires_confirmation": "pending",
            "requires_action": "requires_action",
            "processing": "processing",
            "succeeded": "succeeded",
            "canceled": "cancelled",
        }
        return status_mapping.get(stripe_status, "pending")


class PaymentConfirmSerializer(serializers.Serializer):
    payment_intent_id = serializers.CharField(max_length=255)

    def validate_payment_intent_id(self, value):
        user = self.context["request"].user
        try:
            Payment.objects.get(
                stripe_payment_intent_id=value, invoice__shipment__user=user
            )
            return value
        except Payment.DoesNotExist:
            raise serializers.ValidationError("Payment not found")

    def confirm_payment(self):
        user = self.context["request"].user
        payment_intent_id = self.validated_data["payment_intent_id"]

        try:
            # Confirm the PaymentIntent
            intent = stripe.PaymentIntent.confirm(payment_intent_id)

            # Update local payment record
            payment = Payment.objects.get(
                stripe_payment_intent_id=payment_intent_id, invoice__shipment__user=user
            )

            payment.status = self._map_stripe_status(intent.status)
            payment.save()

            # Handle successful payment
            if intent.status == "succeeded":
                self._mark_payment_successful(payment, payment.invoice)

            return {
                "payment": payment,
                "status": intent.status,
                "requires_action": intent.status
                in ["requires_action", "requires_source_action"],
                "next_action": intent.next_action
                if hasattr(intent, "next_action")
                else None,
            }

        except stripe.error.StripeError as e:
            raise serializers.ValidationError(f"Payment confirmation failed: {str(e)}")

    def _map_stripe_status(self, stripe_status):
        """Map Stripe status to our Payment model status"""
        status_mapping = {
            "requires_payment_method": "failed",
            "requires_confirmation": "pending",
            "requires_action": "requires_action",
            "processing": "processing",
            "succeeded": "succeeded",
            "canceled": "cancelled",
        }
        return status_mapping.get(stripe_status, "pending")

    def _mark_payment_successful(self, payment, invoice):
        """Mark payment and invoice as successful"""
        payment.status = "succeeded"
        payment.save()

        # Update invoice
        invoice.status = "paid"
        invoice.paid_at = timezone.now()
        invoice.save()

        # Update shipment status to in progress
        invoice.shipment.status = "inprogress"
        invoice.shipment.save()


class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(
        source="invoice.invoice_number", read_only=True
    )
    shipment_id = serializers.IntegerField(source="invoice.shipment.id", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "invoice_number",
            "shipment_id",
            "amount",
            "status",
            "failure_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
