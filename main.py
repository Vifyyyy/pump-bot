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

# Ендпоїнт для отримання списку ВСІХ ф'ючерсів MEXC
MEXC_FUTURES_INFO_URL = "https://api.mexc.com/api/v1/contract/detail"
# Ендпоїнт для отримання цін 24hr
MEXC_TICKER_URL = "https://api.mexc.com/api/v3/ticker/24hr"

coins_data = {}
all_futures_symbols = []

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
        print(f"✅ {dir_text} {symbol}: {change:+.2f}%")
    except Exception as e:
        print(f"❌ Помилка: {e}")

# ============================================
# ОТРИМАННЯ СПИСКУ ВСІХ Ф'ЮЧЕРСІВ
# ============================================
async def get_futures_symbols():
    """Отримує список ВСІХ USDT-M ф'ючерсних пар з MEXC"""
    print("🔄 Завантаження списку всіх ф'ючерсних пар MEXC...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(MEXC_FUTURES_INFO_URL, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == 200:
                        contracts = data.get('data', [])
                        # Фільтруємо тільки USDT-M ф'ючерси
                        symbols = [c.get('symbol') for c in contracts if c.get('symbol', '').endswith('USDT')]
                        print(f"📋 ✅ Знайдено {len(symbols)} USDT-M ф'ючерсних пар.")
                        return symbols
                    else:
                        print(f"⚠️ Помилка в даних API: {data.get('msg', 'Невідома помилка')}")
                else:
                    print(f"❌ HTTP помилка при отриманні списку: {response.status}")
    except Exception as e:
        print(f"❌ Помилка: {e}")
    
    print("❌ НЕ ВДАЛОСЯ ОТРИМАТИ СПИСОК Ф'ЮЧЕРСІВ.")
    return None

# ============================================
# ОСНОВНИЙ МОНІТОРИНГ
# ============================================
async def monitor():
    global all_futures_symbols
    
    # 1. Отримуємо список ф'ючерсів
    all_futures_symbols = await get_futures_symbols()
    if not all_futures_symbols:
        await bot.send_message(chat_id=CHAT_ID, text="❌ **КРИТИЧНА ПОМИЛКА:** Не вдалося завантажити список ф'ючерсів MEXC. Бот зупинено.", parse_mode='Markdown')
        return

    print(f"📡 Починаю моніторинг {len(all_futures_symbols)} USDT-M ф'ючерсів...")
    print(f"⚙️ Інтервал: {CHECK_INTERVAL}с | Вікно: {TIME_WINDOW//60}хв | Діапазон: {MIN_PUMP}%-{MAX_PUMP}%")

    await bot.send_message(
        chat_id=CHAT_ID,
        text=f"""🤖 **PUMP/DUMP Бот (MEXC Futures) запущено!**

📊 **Моніторинг:** <b>{len(all_futures_symbols)}</b> USDT-M ф'ючерсних пар
⚡ **Діапазон:** {MIN_PUMP}% - {MAX_PUMP}%
⏱️ **Часове вікно:** {TIME_WINDOW//60} хвилин
🔄 **Повторні сигнали:** ✅

🔔 Очікую на стрибки цін...""",
        parse_mode='HTML'
    )

    # Основний цикл моніторингу
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(MEXC_TICKER_URL, timeout=15) as response:
                    if response.status == 200:
                        all_tickers = await response.json()
                        now = datetime.now()
                        changes_found = 0

                        # Фільтруємо тільки ті ticker, які є в нашому списку ф'ючерсів
                        for ticker in all_tickers:
                            symbol = ticker.get('symbol')
                            if symbol not in all_futures_symbols:
                                continue
                            
                            try:
                                current_price = float(ticker.get('lastPrice', 0))
                            except (ValueError, TypeError):
                                continue

                            if current_price <= 0:
                                continue

                            old_data = coins_data.get(symbol)
                            if old_data:
                                old_price = old_data.get('price')
                                if old_price and old_price != current_price:
                                    change_percent = ((current_price - old_price) / old_price) * 100
                                    abs_change = abs(change_percent)
                                    
                                    if MIN_PUMP <= abs_change <= MAX_PUMP:
                                        last_time = old_data.get('time', now)
                                        if (now - last_time).total_seconds() <= TIME_WINDOW:
                                            alert_count = old_data.get('count', 0) + 1
                                            await send_alert(symbol, old_price, current_price, change_percent, alert_count)
                                            coins_data[symbol] = {'price': current_price, 'time': now, 'count': alert_count}
                                            changes_found += 1
                                        else:
                                            coins_data[symbol] = {'price': current_price, 'time': now, 'count': 0}
                                    else:
                                        coins_data[symbol] = {'price': current_price, 'time': now, 'count': 0}
                                else:
                                    coins_data[symbol] = {'price': current_price, 'time': now, 'count': 0}
                            else:
                                coins_data[symbol] = {'price': current_price, 'time': now, 'count': 0}
                        
                        print(f"📊 Перевірено {len(all_futures_symbols)} ф'ючерсів | змін: {changes_found} | {datetime.now().strftime('%H:%M:%S')}")
                    else:
                        print(f"❌ HTTP помилка: {response.status}")
                        
        except Exception as e:
            print(f"❌ Помилка в циклі моніторингу: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

# ============================================
# ЗАПУСК
# ============================================
async def main():
    print("=" * 55)
    print("🤖 PUMP/DUMP МОНІТОРИНГ MEXC FUTURES")
    print("📡 ТІЛЬКИ USDT-M Ф'ЮЧЕРСНІ ПАРИ")
    print(f"⏱️ Часове вікно: {TIME_WINDOW//60} хвилин")
    print("=" * 55)
    
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
