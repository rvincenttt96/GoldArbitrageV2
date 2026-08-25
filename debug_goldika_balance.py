from adapters.goldika.client import GoldikaClient

c = GoldikaClient(
    '9362798093',
    'Rv6047484'
)

c.login()

r = c.session.get(
    c.BASE_URL + '/api/auth/user/profile'
)

print(r.status_code)
print(r.text)
