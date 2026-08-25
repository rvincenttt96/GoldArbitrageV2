from services.opportunity_finder import OpportunityFinder

f = OpportunityFinder()

price = 21376000

for amount in [
    0.1,
    0.2,
    0.5,
    1.0,
    2.0
]:
    buy_fee = f.get_buy_fee(
        "miligold",
        amount,
        price
    )

    sell_fee = f.get_sell_fee(
        "miligold",
        amount,
        price
    )

    print(
        amount,
        "g | BUY FEE TMN =",
        buy_fee,
        "| SELL FEE TMN =",
        sell_fee
    )
