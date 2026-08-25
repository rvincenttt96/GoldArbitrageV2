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
            json={'username':self.username,'password':self.password}
        )
        data = r.json()
        self.session.headers.update({
            'Authorization':'Bearer ' + data['token']
        })
        return data

    def get_price(self):
        data = self.session.get(
            self.BASE_URL + '/api/public/price'
        ).json()['data']['price']

        return Price(
            'goldika',
            data['id'],
            data['buy'],
            data['sell'],
            datetime.now()
        )

    def buy(self, amount):
        price = self.get_price()
        r = self.session.post(
            self.BASE_URL + '/api/v1/exchanges/buy',
            json={
                'action':'buy',
                'amount':amount,
                'discount_ids':[],
                'discountIds':[],
                'priceId':price.price_id
            }
        )
        return r.json()

    def sell(self, amount):
        price = self.get_price()
        r = self.session.post(
            self.BASE_URL + '/api/v1/exchanges/sell',
            json={
                'action':'sell',
                'amount':amount,
                'discount_ids':[],
                'discountIds':[],
                'priceId':price.price_id
            }
        )
        return r.json()
    def get_price(self, side):

        data = self.session.get(
            self.BASE_URL + '/api/public/price'
        ).json()['data']['price']


        if side == "buy":

            price = data["buy"]

        else:

            price = data["sell"]


        return Quote(
            platform="goldika",
            symbol="GLD_18C_750TMN",
            side=side,
            price=int(price),
            expires_at=datetime.now(),
            ttl=30,
            timestamp=datetime.now()
        )
