from django.urls import path
from . import views

# App URLs (accounts/urls.py)
app_name = "shipper"

urlpatterns = [
    path(
        "shipper/shipping-needs/",
        views.createShippingNeeds,
        name="create_shipping_needs",
    ),
    path(
        "shipper/country-regions/",
        views.get_regions,
        name="create_shipping_needs",
    ),
]
