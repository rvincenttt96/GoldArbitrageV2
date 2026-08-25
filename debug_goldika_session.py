import requests
from adapters.goldika.client import GoldikaClient

client = GoldikaClient(
    username="YOUR_USERNAME",
    password="YOUR_PASSWORD"
)

r = client.session.get(
    "https://goldika.ir"
)

print("INIT:", r.status_code)
print(client.session.cookies)

r = client.session.post(
    client.BASE_URL + "/api/auth/user/login/password",
    json={
        "username": client.username,
        "password": client.password
    }
)

print("LOGIN:", r.status_code)
print(r.text)
