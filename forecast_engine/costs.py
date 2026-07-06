def calculate_costs(farm):
    return (
        farm["feed"]
        + farm["fertiliser"]
        + farm["vet"]
        + farm["contractor"]
        + farm["labour"]
        + farm["insurance"]
        + farm["loan_repayments"]
        + float(farm.get("fuel", 0))
        + float(farm.get("electricity", 0))
    )