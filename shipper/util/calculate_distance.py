from math import radians, cos, sin, sqrt, atan2


def calculate_distance(pickup, dropoff):
    """
    Calculate the distance between two cities using the Haversine formula
    Input: pickup and dropoff are dictionaries with latitude and longitude
    Returns: distance in miles
    """
    R = 3958.8  # Radius of Earth in miles

    lat1 = radians(pickup["latitude"])
    lon1 = radians(pickup["longitude"])
    lat2 = radians(dropoff["latitude"])
    lon2 = radians(dropoff["longitude"])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c
    return round(distance, 2)
