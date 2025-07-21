import requests
from django.conf import settings


def geo_api_get(endpoint, params=None):
    url = f"{settings.GEODB_BASE_URL}/{endpoint}"
    headers = {
        "X-RapidAPI-Key": settings.GEODB_API_KEY,
        "X-RapidAPI-Host": settings.GEODB_API_HOST,
    }
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()
