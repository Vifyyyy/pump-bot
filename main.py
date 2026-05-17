import os
import asyncio
import aiohttp
from datetime import datetime
from telegram import Bot

# ============================================
# НАЛАШТУВАННЯ - БЕРУТЬСЯ З RAILWAY
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
TIME_WINDOW = 900       # 15 хвилин (900 секунд)

# Bitunix REST API ендпоїнти (USDT-M ф'ючерси)
BITUNIX_TICKERS_URL = "https://api.bitunix.com/openapi/v1/market/tickers"

# Дані монет
coins_data = {}
all_symbols = []

# ============================================
# ФУНКЦІЯ НАДСИЛАННЯ СПОВІЩЕННЯ
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
📊 Часове вікно: 15 хвилин
━━━━━━━━━━━━━━━━━━━━━
"""
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='HTML')
        print(f"✅ {dir_text} {symbol}: {change:+.2f}% (сигнал #{count})")
    except Exception as e:
        print(f"❌ Помилка відправки: {e}")

# ============================================
# ОТРИМАННЯ ВСІХ USDT-M МОНЕТ
# ============================================
async def get_all_symbols():
    """Отримує всі USDT-M ф'ючерсні монети з Bitunix API"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BITUNIX_TICKERS_URL, headers=headers, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == 0:
                        tickers = data.get('data', [])
                        # Фільтруємо тільки USDT-M ф'ючерси
                        symbols = [t.get('symbol', '') for t in tickers 
                                  if t.get('symbol', '').endswith('USDT')]
                        print(f"📋 ✅ Знайдено {len(symbols)} USDT-M ф'ючерсних монет")
                        return symbols, tickers
                    else:
                        print(f"⚠️ Помилка API: {data.get('msg')}")
                else:
                    print(f"❌ HTTP помилка: {response.status}")
    except Exception as e:
        print(f"❌ Помилка: {e}")
    
    return None, None

# ============================================
# ОСНОВНИЙ МОНІТОРИНГ
# ============================================
async def monitor():
    global all_symbols
    
    print("🔄 Отримання списку всіх USDT-M монет...")
    
    # Отримуємо список монет
    symbols, initial_tickers = await get_all_symbols()
    if not symbols:
        await bot.send_message(chat_id=CHAT_ID, text="❌ Не вдалося отримати список монет з Bitunix!")
        return
    
    all_symbols = symbols
    
    # Ініціалізуємо початкові ціни
    coins_loaded = 0
    if initial_tickers:
        for ticker in initial_tickers:
            symbol = ticker.get('symbol', '')
            if symbol.endswith('USDT'):
                try:
                    price = float(ticker.get('lastPrice', 0))
                    if price > 0:
                        coins_data[symbol] = {'price': price, 'time': datetime.now(), 'count': 0}
                        coins_loaded += 1
                except:
                    pass
    
    print(f"📡 Починаю моніторинг {coins_loaded} USDT-M монет")
    print(f"⚙️ Інтервал: {CHECK_INTERVAL}с | Часове вікно: {TIME_WINDOW//60} хв | Діапазон: {MIN_PUMP}%-{MAX_PUMP}%")
    
    # Відправляємо повідомлення про запуск
    await bot.send_message(
        chat_id=CHAT_ID,
        text=f"""🤖 **PUMP/DUMP Бот (Bitunix) запущено!**

📊 **Моніторинг:** <b>{coins_loaded}</b> USDT-M ф'ючерсних монет
⚡ **Діапазон:** {MIN_PUMP}% - {MAX_PUMP}%
⏱️ **Часове вікно:** {TIME_WINDOW//60} хвилин
🔄 **Повторні сигнали:** ✅

🔔 Очікую на стрибки цін...""",
        parse_mode='HTML'
    )
    
    print("✅ Тестове повідомлення відправлено в Telegram")
    print("=" * 55)
    
    # Лічильник для статусу
    check_count = 0
    
    # Основний цикл
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(BITUNIX_TICKERS_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('code') == 0:
                            tickers = data.get('data', [])
                            now = datetime.now()
                            
                            changes_found = 0
                            
                            for ticker in tickers:
                                symbol = ticker.get('symbol', '')
                                if not symbol.endswith('USDT'):
                                    continue
                                
                                try:
                                    price = float(ticker.get('lastPrice', 0))
                                except:
                                    continue
                                
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
                                            time_diff = (now - last_time).total_seconds()
                                            
                                            if time_diff <= TIME_WINDOW:
                                                count = old.get('count', 0) + 1
                                                await send_alert(symbol, old_price, price, change, count)
                                                coins_data[symbol] = {'price': price, 'time': now, 'count': count}
                                                changes_found += 1
                                            else:
                                                coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                        else:
                                            coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                elif price > 0:
                                    coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                            
                            check_count += 1
                            if check_count % 12 == 0:  # Кожну хвилину (12 * 5с = 60с)
                                print(f"📊 Статус: {len(coins_data)} монет | Перевірено: {check_count} | {datetime.now().strftime('%H:%M:%S')}")
                            
                            if changes_found > 0:
                                print(f"📢 Знайдено {changes_found} змін за цю перевірку")
                                
                        else:
                            print(f"⚠️ API помилка: {data.get('msg')}")
                    else:
                        print(f"❌ HTTP {response.status}")
                        
        except asyncio.TimeoutError:
            print("⏰ Таймаут API, повторюю...")
        except Exception as e:
            print(f"❌ Помилка: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

# ============================================
# ЗАПУСК
# ============================================
async def main():
    print("=" * 55)
    print("🤖 PUMP/DUMP МОНІТОРИНГ BITUNIX")
    print("📡 USDT-M Ф'ЮЧЕРСНІ МОНЕТИ")
    print(f"⏱️ ЧАСОВЕ ВІКНО: {TIME_WINDOW//60} ХВИЛИН")
    print("=" * 55)
    
    try:
        await monitor()
    except Exception as e:
        print(f"❌ Критична помилка: {e}")
        await bot.send_message(chat_id=CHAT_ID, text=f"❌ Критична помилка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
