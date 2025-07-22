from decimal import Decimal


def calculate_base_price(miles, equipment):
    """Calculate base price based on distance and equipment type"""
    base_rate_per_mile = Decimal("2.50")

    # Equipment multiplier
    equipment_multipliers = {
        "dryVan": Decimal("1.0"),
        "reefer": Decimal("1.3"),  # Reefer costs more
    }

    multiplier = equipment_multipliers.get(equipment, Decimal("1.0"))
    base_fee = Decimal("500.00")  # Minimum fee

    calculated_price = (Decimal(miles) * base_rate_per_mile * multiplier) + base_fee
    return round(calculated_price, 2)
