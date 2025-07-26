from django.urls import path
from . import views
from .views import (
    ShipmentListCreateView,
    ShipmentDetailView,
    ShipmentUpdateStep2View,
    ShipmentUpdateStep3View,
    calculate_distance_price,
    update_shipment_status,
    ShipmentStatusHistoryView,
    shipment_dashboard,
    save_draft_shipment,
    LocationListView,
    price_calculation_history,
)

# App URLs (accounts/urls.py)
app_name = "shipper"

urlpatterns = [
    path(
        "shipper/shipping-needs/",
        views.createShippingNeeds,
        name="create_shipping_needs",
    ),
    path(
        "shipper/cities/",
        views.search_cities,
        name="search_cities",
    ),
    path(
        "shipper/country-regions/",
        views.get_regions,
        name="get_country_regions",
    ),
    path(
        "shipper/distance-price/",
        views.calculate_distance_price,
        name="get_distance_price",
    ),
    path(
        "shipper/shipments/",
        ShipmentListCreateView.as_view(),
        name="shipment_list_create",
    ),
    path(
        "shipper/shipments/<str:pk>/",
        ShipmentDetailView.as_view(),
        name="shipment-detail",
    ),
    # Multi-step shipment creation
    path(
        "shipper/shipments/<str:pk>/appointment/",
        ShipmentUpdateStep2View.as_view(),
        name="shipment-step2",
    ),
    path(
        "shipper/shipments/<str:pk>/finalizing/",
        ShipmentUpdateStep3View.as_view(),
        name="shipment-step3",
    ),
    # Distance and price calculation
    path(
        "shipper/shipments/calculate/",
        calculate_distance_price,
        name="calculate-distance-price",
    ),
    # Update status
    path(
        "shipper/shipments/<int:shipment_id>/status/",
        update_shipment_status,
        name="update-shipment-status",
    ),
    # Status history
    path(
        "shipper/shipments/<int:shipment_id>/history/",
        ShipmentStatusHistoryView.as_view(),
        name="shipment-status-history",
    ),
    # Dashboard
    path("shipper/shipments/dashboard/", shipment_dashboard, name="shipment-dashboard"),
    path("invoices/", views.InvoiceListCreateView.as_view(), name="invoices"),
    path(
        "invoices/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice-detail"
    ),
    # Payments
    path(
        "payments/create-intent/",
        views.create_payment_intent,
        name="create-payment-intent",
    ),
    path(
        "payments/confirm/", views.confirm_payment_intent, name="confirm-payment-intent"
    ),
    path(
        "payments/status/<str:payment_intent_id>/",
        views.payment_status,
        name="payment-status",
    ),
    path("payments/history/", views.payment_history, name="payment-history"),
    # Stripe Webhook
    path("webhooks/stripe/", views.stripe_webhook, name="stripe-webhook"),
]
