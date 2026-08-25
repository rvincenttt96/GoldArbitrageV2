from adapters.goldika.client import GoldikaClient

c = GoldikaClient(
    '9362798093',
    'Rv6047484'
)

c.login()

for amount in ["0.001", "0.010", "0.100", "0.500"]:
    price = c.session.get(
        c.BASE_URL + '/api/public/price'
    ).json()['data']['price']

    r = c.session.post(
        c.BASE_URL + '/api/v1/exchanges/sell',
        json={
            'action':'sell',
            'amount':amount,
            'discount_ids':[],
            'discountIds':[],
            'priceId':price['id']
        }
    )

    print("AMOUNT:", amount)
    print("STATUS:", r.status_code)
    print(r.text)
    print("----------------")
