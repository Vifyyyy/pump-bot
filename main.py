import os
import asyncio
import json
import websockets
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

MIN_PUMP = 3.0          # Мінімальний рух 3%
MAX_PUMP = 50.0         # Максимальний рух 50%
TIME_WINDOW = 600       # 10 хвилин

# Binance Futures WebSocket (всі монети в одному каналі)
BINANCE_WS = "wss://fstream.binance.com/ws/!ticker@arr"

# Дані монет
coins_data = {}
all_symbols = []

# ============================================
# ОТРИМАННЯ ВСІХ Ф'ЮЧЕРСНИХ МОНЕТ
# ============================================
async def get_all_futures_symbols():
    """Отримує актуальний список всіх ф'ючерсних пар з Binance"""
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    symbols = [item['symbol'] for item in data['symbols'] if item['status'] == 'TRADING']
                    
                    # Фільтруємо тільки USDT пари
                    usdt_symbols = [s for s in symbols if s.endswith('USDT')]
                    print(f"📋 ✅ Знайдено {len(usdt_symbols)} ф'ючерсних монет (USDT)")
                    return usdt_symbols
                else:
                    print(f"❌ HTTP помилка: {response.status}")
    except Exception as e:
        print(f"❌ Помилка: {e}")
    
    print("❌ НЕ ВДАЛОСЯ ОТРИМАТИ СПИСОК МОНЕТ!")
    return None

# ============================================
# ВІДПРАВКА СПОВІЩЕННЯ
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
# ОСНОВНИЙ МОНІТОРИНГ
# ============================================
async def monitor():
    global all_symbols
    
    # Отримуємо список всіх монет
    all_symbols = await get_all_futures_symbols()
    if not all_symbols:
        await bot.send_message(
            chat_id=CHAT_ID,
            text="❌ Не вдалося отримати список монет з Binance! Бот зупинено."
        )
        return
    
    print(f"📡 Починаю моніторинг {len(all_symbols)} монет...")
    
    # Відправляємо повідомлення про запуск
    await bot.send_message(
        chat_id=CHAT_ID,
        text=f"""🤖 **PUMP/DUMP Бот (Binance Futures) запущено!**

📊 **Моніторинг:** <b>{len(all_symbols)}</b> ф'ючерсних монет
⚡ **Діапазон:** {MIN_PUMP}% - {MAX_PUMP}%
⏱️ **Часове вікно:** 10 хвилин
🔄 **Повторні сигнали:** ✅
📡 **Нові монети:** автоматично додаються

🔔 Очікую на стрибки цін...""",
        parse_mode='HTML'
    )
    
    # Підключаємося до WebSocket
    while True:
        try:
            async with websockets.connect(BINANCE_WS, ping_interval=20) as ws:
                print("🔌 Підключено до Binance WebSocket")
                
                async for message in ws:
                    try:
                        tickers = json.loads(message)
                        
                        for ticker in tickers:
                            symbol = ticker.get('s', '')
                            
                            # Фільтруємо тільки USDT пари
                            if not symbol.endswith('USDT'):
                                continue
                            
                            try:
                                price = float(ticker.get('c', 0))
                            except:
                                continue
                            
                            if price <= 0:
                                continue
                            
                            now = datetime.now()
                            old = coins_data.get(symbol)
                            
                            if old:
                                old_price = old.get('price')
                                if old_price and old_price != price:
                                    change = ((price - old_price) / old_price) * 100
                                    abs_change = abs(change)
                                    
                                    if MIN_PUMP <= abs_change <= MAX_PUMP:
                                        last_time = old.get('time', now)
                                        time_diff = (now - last_time).total_seconds()
                                        
                                        if time_diff <= TIME_WINDOW:
                                            count = old.get('count', 0) + 1
                                            await send_alert(symbol, old_price, price, change, count)
                                            coins_data[symbol] = {'price': price, 'time': now, 'count': count}
                                        else:
                                            coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                    else:
                                        coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                else:
                                    coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                            else:
                                coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        print(f"⚠️ Помилка: {e}")
                        
        except Exception as e:
            print(f"❌ WebSocket помилка: {e}")
            await asyncio.sleep(5)

# ============================================
# ЗАПУСК
# ============================================
async def main():
    print("=" * 55)
    print("🤖 PUMP/DUMP МОНІТОРИНГ BINANCE FUTURES")
    print("📡 ВСІ ф'ючерсні монети (автооновлення)")
    print("=" * 55)
    
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
