def calculate_feed_cost_ratio(farm, revenue):
    if revenue <= 0:
        return 0

    return farm["feed"] / revenue


def calculate_cost_ratio(costs, revenue):
    if revenue <= 0:
        return 0

    return costs / revenue


def calculate_revenue_per_cow(farm, revenue):
    cows = farm["milking_cows"]

    if cows <= 0:
        return 0

    return revenue / cows


def calculate_profit_per_cow(farm, profit):
    cows = farm["milking_cows"]

    if cows <= 0:
        return 0

    return profit / cows