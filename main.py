import asyncio
import os
from datetime import datetime
from telegram import Bot
from bitunix import BitunixClient

# --- ЗМІННІ (ВІЗЬМУТЬСЯ З НАЛАШТУВАНЬ RAILWAY) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
# API-ключі зараз не потрібні, бо ми лише читаємо публічні ціни

# --- НАЛАШТУВАННЯ ---
THRESHOLD_PERCENT = 3.0  # Сповіщати при зміні ціни на 3% і більше

# --- ЗМІННІ ДЛЯ РОБОТИ БОТА ---
bot = Bot(token=TELEGRAM_TOKEN)

# Словник, щоб запам'ятати ціну кожної монети за секунду до цього
last_prices = {}

async def send_alert(symbol, old_price, new_price, change_percent):
    """Надсилає сповіщення про рух ціни в Telegram."""
    direction = "🚀 PUMP (різке зростання)" if change_percent > 0 else "💥 DUMP (різке падіння)"
    message = (
        f"{direction} {symbol}\n"
        f"Зміна за 1 секунду: {change_percent:.2f}%\n"
        f"Ціна: {new_price}\n"
        f"Час: {datetime.now().strftime('%H:%M:%S')}"
    )
    await bot.send_message(chat_id=CHAT_ID, text=message)
    print(f"✅ Відправлено сповіщення: {message}")

async def main():
    print("🤖 Бот для Bitunix запускається...")
    print(f"⚙️ Поріг спрацювання: {THRESHOLD_PERCENT}%")

    # Підключаємося до Bitunix (без API-ключів, тільки для читання публічних даних)
    # Пробуємо створити клієнта. Якщо немає ключів, він все одно зможе читати ціни.
    try:
        client = BitunixClient("", "")
        print("🔌 Підключення до Bitunix встановлено")
    except Exception as e:
        print(f"❌ Помилка підключення до Bitunix: {e}")
        return

    print("📡 Починаємо моніторинг цін на Bitunix...")
    print("⏳ Очікуємо на стрибки цін...")

    # Нескінченний цикл моніторингу
    while True:
        try:
            # Отримуємо список всіх торгових пар (трейдинг пар) з біржі
            all_pairs = client.get_trading_pairs()
            
            # Проходимось по кожній парі та перевіряємо ціну
            for pair in all_pairs:
                symbol = pair.get('symbol') # Назва пари, наприклад BTCUSDT
                if not symbol:
                    continue
                    
                # Отримуємо останню ціну для цієї пари
                latest_price_data = client.get_latest_price(symbol)
                # Відповідь може мати вигляд {"code": 0, "data": {"price": "50000"}}
                if latest_price_data and 'data' in latest_price_data:
                    try:
                        new_price = float(latest_price_data['data']['price'])
                    except (ValueError, KeyError, TypeError):
                        continue
                else:
                    continue
                
                # Перевіряємо, чи бачили цю монету раніше
                if symbol in last_prices:
                    old_price = last_prices[symbol]
                    # Обчислюємо зміну у відсотках
                    if old_price > 0:
                        percent_change = ((new_price - old_price) / old_price) * 100
                        
                        # Якщо зміна більша за поріг (наприклад, 3%) - надсилаємо сповіщення
                        if abs(percent_change) >= THRESHOLD_PERCENT:
                            await send_alert(symbol, old_price, new_price, percent_change)
                
                # Оновлюємо збережену ціну для наступної перевірки
                last_prices[symbol] = new_price
            
            # Затримка в 1 секунду, щоб не перевантажувати біржу
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"❌ Сталася помилка: {e}")
            print("⏳ Спроба перепідключення через 5 секунд...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
