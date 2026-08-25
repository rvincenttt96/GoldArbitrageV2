from pathlib import Path

p = Path("./adapters/miligold/client.py")

s = p.read_text(encoding="utf-8")

old = """    def get_commission(self, amount, price, order_type):"""

new = """    def get_rial_balance(self):

        r = self.session.get(
            f"{self.BASE_URL}/api/v1/wallet/milli/{self.wallet_address}/available-rial-balance"
        )

        return r.json()


    def get_commission(self, amount, price, order_type):"""

if old not in s:
    raise Exception("target not found")

p.write_text(
    s.replace(old, new),
    encoding="utf-8"
)

print("DONE")
