from adapters.goldika.client import GoldikaClient

c = GoldikaClient(
    '9362798093',
    'Rv6047484'
)

c.login()

price = c.session.get(
    c.BASE_URL + '/api/public/price'
).json()['data']['price']

payload = {
    'action':'sell',
    'amount':'0.1',
    'discount_ids':[],
    'discountIds':[],
    'priceId':price['id']
}

print("PRICE:")
print(price)

print("PAYLOAD:")
print(payload)

r = c.session.post(
    c.BASE_URL + '/api/v1/exchanges/sell',
    json=payload
)

print("STATUS:", r.status_code)
print("TEXT:")
print(r.text)
