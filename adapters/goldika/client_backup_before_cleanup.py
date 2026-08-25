import requests
from datetime import datetime
from core.models import Quote, Order


class GoldikaClient:

    BASE_URL = 'https://api.goldika.ir'


    def __init__(self, username, password):

        self.username = username
        self.password = password

        self.session = requests.Session()

        self.session.headers.update({
            'Accept':'application/json',
            'Content-Type':'application/json',
            'X-PLATFORM':'web',
            'X-VERSION':'2.4.13',
            'Origin':'https://goldika.ir',
            'Referer':'https://goldika.ir/'
        })


    def login(self):

        r = self.session.post(
            self.BASE_URL + '/api/auth/user/login/password',
            json={
                'username': self.username,
                'password': self.password
            }
        )

        print("LOGIN STATUS:", r.status_code)

        data = r.json()

        print("LOGIN RESPONSE:")
        print(data)

        if "token" not in data:

            raise Exception(
                f"Login failed: {data}"
            )

        self.session.headers.update({
            'Authorization':'Bearer ' + data['token']
        })

        return data


    def get_price(self, side):

        data = self.session.get(
            self.BASE_URL + '/api/public/price'
        ).json()['data']['price']


        price_id = data['id']

        price = data['buy'] if side == "buy" else data['sell']


        return Quote(
            platform="goldika",
            symbol="GLD_18C_750TMN",
            side=side,
            price=int(price / 10),
            price_id=price_id,
            expires_at=datetime.now(),
            ttl=30,
            timestamp=datetime.now()
        )


    def buy(self, amount):

        price = self.get_price("buy")

        r = self.session.post(
            self.BASE_URL + '/api/v1/exchanges/buy',
            json={
                'action':'buy',
                'amount':int(amount*100),
                'total':int(amount*100*price.price),
                'discount_ids':[],
                'discountIds':[],
                'priceId':price.price_id,
                'total':int(price.price*int(amount*100)//10)
            }
        )

        return r.json()


    def sell(self, amount):

        price = self.get_price("sell")

        r = self.session.post(
            self.BASE_URL + '/api/v1/exchanges/sell',
            json={
                'action':'sell',
                'amount':int(amount*100),
                'total':int(amount*100*price.price),
                'discount_ids':[],
                'discountIds':[],
                'priceId':price.price_id,
                'total':int(price.price*int(amount*100)//10)
            }
        )

        return r.json()

