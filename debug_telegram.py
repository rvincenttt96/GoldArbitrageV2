import requests

TOKEN = "8866886357:AAEO_4CkMTgaZmxrZBhyD9-HnjXCDZxE0AE"

url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

r = requests.get(url)

print(r.json())
