import math


def calculate_transit_time(miles):
    """Calculate minimum transit time in days based on distance"""
    # Assume average speed of 500 miles per day including stops
    days = math.ceil(miles / 500)
    return max(1, days)
