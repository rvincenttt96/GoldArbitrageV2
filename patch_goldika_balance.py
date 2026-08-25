from pathlib import Path

p = Path("./adapters/goldika/client.py")
s = p.read_text(encoding="utf-8")

if "def get_balance(self)" in s:
    raise Exception("get_balance already exists")

marker = '''    def buy(self, amount):'''

method = '''    def get_balance(self):

        r = self.session.get(
            self.BASE_URL + "/api/v1/balances/get",
            timeout=15
        )

        data = r.json()

        if r.status_code != 200:
            raise Exception(
                f"Goldika balance HTTP error: "
                f"{r.status_code} {data}"
            )

        if "data" not in data:
            raise Exception(
                f"Goldika balance response error: {data}"
            )

        return data


'''

if marker not in s:
    raise Exception("buy method marker not found")

s = s.replace(
    marker,
    method + marker,
    1
)

p.write_text(
    s,
    encoding="utf-8"
)

print("GOLDIKA GET_BALANCE ADDED")
