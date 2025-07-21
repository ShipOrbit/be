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
]
