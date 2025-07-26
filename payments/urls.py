from django.urls import path

from . import views


# App URLs (accounts/urls.py)
app_name = "payments"

urlpatterns = [
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
