from adapters.miligold.client import MilliGoldClient


client = MilliGoldClient(
    "+989362798093",
    "Rv6047484"
)

client.login()

print("COOKIES:")
print(client.session.cookies)
