import requests
from telegram_config import TELEGRAM_BASE_URL, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

url = f"{TELEGRAM_BASE_URL}/bot{TELEGRAM_TOKEN}/sendMessage"

payload = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": "?? GOLD ARBITRAGE BOT CONNECTED\n\nProxy: OK\nTelegram: OK"
}

r = requests.post(url, json=payload)

print(r.status_code)
print(r.text)
