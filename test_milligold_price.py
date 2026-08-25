from adapters.miligold.client import MilliGoldClient


client = MilliGoldClient(
    "+989362798093",
    "Rv6047484"
)

result = client.get_price("buy")

print("RESULT:")
print(result)
