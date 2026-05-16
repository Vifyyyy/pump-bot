import os
import time
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

prices = {}

def send_message(text):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": text
        }
    )

send_message("🚀 Bitunix Pump Bot Started")

while True:
    try:
        r = requests.get(
            "https://fapi.bitunix.com/api/v1/futures/market/tickers"
        ).json()

        coins = r["data"]

        now = time.time()

        for coin in coins:

            symbol = coin["symbol"]

            if "USDT" not in symbol:
                continue

            price = float(coin["lastPrice"])

            if symbol not in prices:
                prices[symbol] = {
                    "price": price,
                    "time": now
                }
                continue

            old_price = prices[symbol]["price"]
            old_time = prices[symbol]["time"]

            change = ((price - old_price) / old_price) * 100

            minutes = (now - old_time) / 60

            if abs(change) >= 3 and minutes <= 10:

                if change > 0:
                    msg = f"🚀 PUMP {symbol}\n+{round(change,2)}%"
                else:
                    msg = f"📉 DUMP {symbol}\n{round(change,2)}%"

                send_message(msg)

                prices[symbol] = {
                    "price": price,
                    "time": now
                }

        time.sleep(20)

    except Exception as e:
        print(e)
        time.sleep(10)