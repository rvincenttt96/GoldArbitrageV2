from adapters.miligold.client import MilliGoldClient

client = MilliGoldClient(
    "+989362798093",
    "Rv6047484"
)

milli = client.get_price("buy")

print("MILLI RAW:", milli["price"])
print("MILLI GRAM:", milli["price"] * 100)
