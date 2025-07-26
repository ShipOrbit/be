from django.urls import path

from . import views
from .views import (
    ShipmentDetailView,
    ShipmentListCreateView,
    ShipmentUpdateStep2View,
    ShipmentUpdateStep3View,
    calculate_distance_price,
)

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
    path(
        "shipper/shipments/calculate/",
        calculate_distance_price,
        name="calculate-distance-price",
    ),
]
