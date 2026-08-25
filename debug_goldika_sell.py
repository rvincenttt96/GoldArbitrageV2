from adapters.goldika.client import GoldikaClient

c = GoldikaClient(
    '9362798093',
    'Rv6047484'
)

c.login()

price = c.get_price("sell")

print("PRICE:")
print(price)

r = c.session.post(
    c.BASE_URL + '/api/v1/exchanges/sell',
    json={
        'action':'sell',
        'amount':0.1,
        'discount_ids':[],
        'discountIds':[],
        'priceId':price.price_id
    }
)

print("STATUS:", r.status_code)
print("RESPONSE:")
print(r.text)
