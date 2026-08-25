from adapters.goldika.client import GoldikaClient

client = GoldikaClient(
    username="YOUR_USERNAME",
    password="YOUR_PASSWORD"
)

r = client.session.post(
    client.BASE_URL + "/api/auth/user/login/password",
    json={
        "username": client.username,
        "password": client.password
    }
)

print("STATUS:", r.status_code)
print("HEADERS:", r.headers)
print("TEXT:", r.text)
