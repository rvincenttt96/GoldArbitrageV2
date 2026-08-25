from adapters.goldika.client import GoldikaClient

c = GoldikaClient(
    '9362798093',
    'Rv6047484'
)

c.login()

paths = [
    '/api/v1/account',
    '/api/v1/account/balance',
    '/api/v1/account/balances',
    '/api/v1/wallet',
    '/api/v1/wallets',
    '/api/user',
    '/api/auth/user',
    '/api/auth/user/me',
]

for p in paths:
    r = c.session.get(c.BASE_URL + p)
    print("----", p, r.status_code)
    print(r.text[:200])
