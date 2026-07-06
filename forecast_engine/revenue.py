def calculate_revenue(farm, milk_price=None):
    if milk_price is None:
        milk_price = farm["milk_price"]

    milk_revenue = farm["milking_cows"] * farm["litres_per_cow"] * milk_price
    scheme_revenue = farm.get("biss", 0) + farm.get("acres", 0)

    return milk_revenue + scheme_revenue + farm.get("other_revenue", 0)
