from adapters.goldika.client import GoldikaClient

c = GoldikaClient(
    '9362798093',
    'Rv6047484'
)

c.login()

price = c.session.get(
    c.BASE_URL + '/api/public/price'
).json()['data']['price']

print("PRICE ID:", price['id'])

r = c.session.post(
    c.BASE_URL + '/api/v1/exchanges/sell',
    json={
        'action':'sell',
        'amount':'0.1',
        'discount_ids':[],
        'discountIds':[],
        'priceId':price['id']
    }
)

print("STATUS:", r.status_code)
print("HEADERS:", r.headers)
print("TEXT:", r.text)
