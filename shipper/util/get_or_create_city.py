from shipper.models import City


def get_or_create_city(city_data):
    city_id = city_data["id"]

    try:
        return City.objects.get(id=city_id)
    except City.DoesNotExist:
        # Extract required fields
        name = city_data["name"]
        region_code = city_data.get("regionCode", "")
        country_code = city_data.get("countryCode", "")
        latitude = city_data.get("latitude")
        longitude = city_data.get("longitude")

        # Create city in DB
        return City.objects.create(
            id=city_id,
            name=name,
            region_code=region_code,
            country_code=country_code,
            latitude=latitude,
            longitude=longitude,
        )
