def calculate_costs(farm):
    return (
        farm["feed"]
        + farm["fertiliser"]
        + farm["vet"]
        + farm["contractor"]
        + farm["labour"]
        + farm["insurance"]
        + farm["loan_repayments"]
    )