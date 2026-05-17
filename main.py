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
MIN_PUMP = 3.0          # Мінімальний рух 3%
MAX_PUMP = 50.0         # Максимальний рух 50%
CHECK_INTERVAL = 5      # Перевіряємо кожні 5 секунд
TIME_WINDOW = 900       # 15 хвилин

# --- ВИПРАВЛЕНІ ЕНДПОЇНТИ ДЛЯ MEXC ---
# 1. Ендпоїнт для отримання списку ВСІХ ф'ючерсних пар (USDT-M)
MEXC_CONTRACTS_URL = "https://api.mexc.com/api/v1/contract/detail"
# 2. Ендпоїнт для отримання поточної ціни
MEXC_TICKER_URL = "https://api.mexc.com/api/v3/ticker/price"

# Словник для зберігання даних монет
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
        print(f"✅ {dir_text} {symbol}: {change:+.2f}% (сигнал #{count})")
    except Exception as e:
        print(f"❌ Помилка відправки: {e}")

# ============================================
# ОТРИМАННЯ ВСІХ Ф'ЮЧЕРСНИХ ПАР
# ============================================
async def get_all_futures_symbols():
    """Отримує список ВСІХ USDT-M ф'ючерсних пар з MEXC."""
    print(f"🔄 Завантаження списку всіх USDT-M ф'ючерсів з MEXC...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(MEXC_CONTRACTS_URL, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    # За логами API MEXC повертає словник {"code":200,"data":[...]}
                    if isinstance(data, dict) and data.get('code') == 200:
                        contracts = data.get('data', [])
                        # Фільтруємо тільки USDT-M ф'ючерси (symbol закінчується на USDT)
                        symbols = [c.get('symbol') for c in contracts if c.get('symbol', '').endswith('USDT')]
                        print(f"📋 ✅ Успішно знайдено та відфільтровано {len(symbols)} USDT-M ф'ючерсних пар.")
                        return symbols
                    else:
                        print(f"⚠️ Помилка в даних API: {data.get('msg', 'Невідома помилка')}")
                else:
                    print(f"❌ HTTP помилка при отриманні списку: {response.status}")
    except asyncio.TimeoutError:
        print("❌ Таймаут підключення до MEXC API")
    except aiohttp.ClientConnectorError as e:
        print(f"❌ Помилка з'єднання з MEXC: {e}")
    except Exception as e:
        print(f"❌ Невідома помилка: {e}")

    print("❌ НЕ ВДАЛОСЯ ОТРИМАТИ СПИСОК Ф'ЮЧЕРСІВ. БОТ НЕ МОЖЕ ПРАЦЮВАТИ.")
    return None

# ============================================
# ОСНОВНИЙ МОНІТОРИНГ
# ============================================
async def monitor():
    global all_futures_symbols
    
    # 1. Отримуємо список всіх ф'ючерсів
    all_futures_symbols = await get_all_futures_symbols()
    if not all_futures_symbols:
        await bot.send_message(chat_id=CHAT_ID, text="❌ **КРИТИЧНА ПОМИЛКА:** Не вдалося завантажити список ф'ючерсних монет з MEXC. Бот зупинено.", parse_mode='Markdown')
        return

    print(f"📡 Починаю моніторинг {len(all_futures_symbols)} USDT-M ф'ючерсних монет...")
    print(f"⚙️ Інтервал: {CHECK_INTERVAL}с | Часове вікно: {TIME_WINDOW//60} хв | Діапазон: {MIN_PUMP}% - {MAX_PUMP}%")

    # Відправляємо фінальне повідомлення про запуск в Telegram
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
                # Отримуємо всі поточні ціни в одному запиті
                params = {'symbols': '["' + '","'.join(all_futures_symbols) + '"]'}
                async with session.get(MEXC_TICKER_URL, params=params, timeout=15) as response:
                    if response.status == 200:
                        prices_data = await response.json()
                        now = datetime.now()
                        changes_found = 0

                        # Оновлюємо ціни та перевіряємо зміни
                        for item in prices_data:
                            symbol = item.get('symbol')
                            if not symbol or symbol not in all_futures_symbols:
                                continue
                            
                            try:
                                current_price = float(item.get('price', 0))
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
                        
                        print(f"📊 Перевірено {len(prices_data)} ф'ючерсів | змін: {changes_found} | {datetime.now().strftime('%H:%M:%S')}")
                    else:
                        print(f"❌ HTTP помилка при отриманні цін: {response.status}")
                        
        except asyncio.TimeoutError:
            print("⏰ Таймаут підключення до API цін")
        except Exception as e:
            print(f"❌ Помилка в циклі моніторингу: {e}")
        
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
    
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
