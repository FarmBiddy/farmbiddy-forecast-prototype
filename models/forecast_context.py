class ForecastContext:
    def __init__(self, farm):
        self.farm = farm

        self.farm_name = farm["farm_name"]
        self.farm_type = farm.get("farm_type", "Dairy")

        self.milking_cows = farm["milking_cows"]
        self.litres_per_cow = farm["litres_per_cow"]
        self.milk_price = farm["milk_price"]

        self.opening_cash_balance = farm.get("opening_cash_balance", 0)

        self.biss = farm.get("biss", 0)
        self.acres = farm.get("acres", 0)
        self.scheme_payment_months = farm.get("scheme_payment_months", {})

        self.costs = {
            "feed": farm["feed"],
            "fertiliser": farm["fertiliser"],
            "vet": farm["vet"],
            "contractor": farm["contractor"],
            "labour": farm["labour"],
            "insurance": farm["insurance"],
            "loan_repayments": farm["loan_repayments"]
        }