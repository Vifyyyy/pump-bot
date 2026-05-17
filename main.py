import os
import asyncio
import aiohttp
from datetime import datetime
from telegram import Bot

# ============================================
# НАЛАШТУВАННЯ
# ============================================
TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHANNEL_ID")

if not TOKEN or not CHAT_ID:
    print("❌ ПОМИЛКА: Додай BOT_TOKEN та CHANNEL_ID в Railway!")
    exit(1)

bot = Bot(token=TOKEN)

# ============================================
# ПАРАМЕТРИ МОНІТОРИНГУ
# ============================================
MIN_PUMP = 3.0
MAX_PUMP = 50.0
CHECK_INTERVAL = 5
TIME_WINDOW = 900

# MEXC Futures API (ТІЛЬКИ Ф'ЮЧЕРСНІ ПАРИ)
# Згідно документації MEXC [citation:4][citation:5]
MEXC_FUTURES_URL = "https://api.mexc.com/api/v1/contract/detail"

coins_data = {}

# ============================================
# НАДСИЛАННЯ СПОВІЩЕННЯ
# ============================================
async def send_alert(symbol, old_price, new_price, change, count):
    is_pump = change > 0
    dir_text = "🚀🔥 PUMP" if is_pump else "💀📉 DUMP"
    
    if new_price < 1:
        price_str = f"{new_price:.8f}"
    else:
        price_str = f"{new_price:.4f}"
    
    message = f"""
{dir_text}
━━━━━━━━━━━━━━━━━━━━━
🪙 Монета: <code>{symbol}</code>
📊 Зміна: <b>{change:+.2f}%</b>
💰 Ціна: <b>{price_str}</b> USDT
🕐 Час: {datetime.now().strftime('%H:%M:%S')}
🔄 Сигнал #{count}
━━━━━━━━━━━━━━━━━━━━━
"""
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='HTML')
        print(f"✅ {dir_text} {symbol}: {change:+.2f}% (сигнал #{count})")
    except Exception as e:
        print(f"❌ Помилка: {e}")

# ============================================
# ОТРИМАННЯ ВСІХ Ф'ЮЧЕРСНИХ ПАР MEXC
# ============================================
async def get_futures_symbols():
    """Отримує список всіх ф'ючерсних пар з MEXC"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(MEXC_FUTURES_URL, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Формат відповіді MEXC Futures
                    if isinstance(data, list):
                        # Фільтруємо тільки USDT-M ф'ючерси
                        symbols = [item.get('symbol', '') for item in data if item.get('symbol', '').endswith('USDT')]
                        print(f"📋 ✅ Знайдено {len(symbols)} ф'ючерсних пар (USDT-M)")
                        return symbols, data
                    else:
                        print(f"⚠️ Невідомий формат: {type(data)}")
                else:
                    print(f"❌ HTTP {response.status}")
    except Exception as e:
        print(f"❌ Помилка: {e}")
    
    return None, None

# ============================================
# ОТРИМАННЯ ЦІН (24hr Ticker)
# ============================================
async def get_ticker_price(session, symbol):
    """Отримує поточну ціну для конкретного символу"""
    url = f"https://api.mexc.com/api/v3/ticker/price?symbol={symbol}"
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                return float(data.get('price', 0))
    except:
        pass
    return 0

# ============================================
# ОСНОВНИЙ МОНІТОРИНГ (ВСІ Ф'ЮЧЕРСИ)
# ============================================
async def monitor():
    print("🔄 Підключення до MEXC Futures API...")
    
    # Отримуємо список всіх ф'ючерсних пар
    symbols, contract_data = await get_futures_symbols()
    
    if not symbols:
        print("❌ Не вдалося отримати список ф'ючерсних пар!")
        await bot.send_message(
            chat_id=CHAT_ID,
            text="❌ Не вдалося отримати список ф'ючерсних пар MEXC!"
        )
        return
    
    print(f"📡 Починаю моніторинг {len(symbols)} ф'ючерсних пар (USDT-M)")
    print(f"⚙️ Інтервал: {CHECK_INTERVAL}с | Вікно: {TIME_WINDOW//60}хв | Діапазон: {MIN_PUMP}%-{MAX_PUMP}%")
    
    # Ініціалізуємо початкові ціни
    async with aiohttp.ClientSession() as init_session:
        for symbol in symbols:
            price = await get_ticker_price(init_session, symbol)
            if price > 0:
                coins_data[symbol] = {'price': price, 'time': datetime.now(), 'count': 0}
    
    print(f"✅ Ініціалізовано {len(coins_data)} монет")
    
    # Основний цикл моніторингу
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                changes = 0
                now = datetime.now()
                
                for symbol in symbols:
                    price = await get_ticker_price(session, symbol)
                    
                    if price <= 0:
                        continue
                    
                    old = coins_data.get(symbol)
                    if old and old.get('price'):
                        old_price = old['price']
                        if old_price != price:
                            change = ((price - old_price) / old_price) * 100
                            abs_change = abs(change)
                            
                            if MIN_PUMP <= abs_change <= MAX_PUMP:
                                last_time = old.get('time', now)
                                if (now - last_time).total_seconds() <= TIME_WINDOW:
                                    count = old.get('count', 0) + 1
                                    await send_alert(symbol, old_price, price, change, count)
                                    coins_data[symbol] = {'price': price, 'time': now, 'count': count}
                                    changes += 1
                                else:
                                    coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                            else:
                                coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                    elif price > 0:
                        coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                
                print(f"📊 Перевірено {len(symbols)} ф'ючерсів | змін: {changes} | {datetime.now().strftime('%H:%M:%S')}")
                        
        except Exception as e:
            print(f"❌ Помилка: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

# ============================================
# ЗАПУСК
# ============================================
async def main():
    print("=" * 55)
    print("🤖 PUMP/DUMP МОНІТОРИНГ MEXC FUTURES")
    print("📡 ТІЛЬКИ Ф'ЮЧЕРСНІ ПАРИ (USDT-M)")
    print(f"⏱️ Часове вікно: {TIME_WINDOW//60} хвилин")
    print("=" * 55)
    
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=f"""🤖 **PUMP/DUMP Бот (MEXC Futures) запущено!**

📊 **Тип:** ТІЛЬКИ ф'ючерсні пари (USDT-M)
⚡ **Діапазон:** {MIN_PUMP}% - {MAX_PUMP}%
⏱️ **Часове вікно:** {TIME_WINDOW//60} хвилин
🔄 **Повторні сигнали:** ✅

🔔 Очікую на стрибки цін...""",
            parse_mode='Markdown'
        )
        print("✅ Тестове повідомлення відправлено")
    except Exception as e:
        print(f"❌ Помилка Telegram: {e}")
    
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
