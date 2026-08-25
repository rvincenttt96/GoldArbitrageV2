from pathlib import Path

p = Path("./adapters/miligold/client.py")

s = p.read_text(encoding="utf-8")

s = s.replace(
'''f"{self.BASE_URL}/api/v1/wallet/milli/{self.wallet_address}/available-rial-balance"''',
'''f"{self.BASE_URL}/api/v1/wallet/rial/available-balance"'''
)

p.write_text(s, encoding="utf-8")

print("DONE")
