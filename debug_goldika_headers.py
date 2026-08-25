from adapters.goldika.client import GoldikaClient

c = GoldikaClient(
    '9362798093',
    'Rv6047484'
)

c.login()

print(c.session.headers)

print(
    c.session.post(
        c.BASE_URL + '/api/v1/exchanges/sell',
        json={
            'action':'sell',
            'amount':0.1,
            'discount_ids':[],
            'discountIds':[],
            'priceId':413035
        }
    ).request.headers
)
