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

# Параметри моніторингу
MIN_PUMP_PERCENT = 3.0      # Мінімальний рух 3%
MAX_PUMP_PERCENT = 50.0     # Максимальний рух 50%
TIME_WINDOW_SECONDS = 600   # 10 хвилин

BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/linear"

# Дані монет
coins_data = {}

# ============================================
# ОТРИМАННЯ ВСІХ Ф'ЮЧЕРСНИХ МОНЕТ З BYBIT
# ============================================
async def get_all_symbols():
    """Отримує ВСІ USDT Perpetual ф'ючерсні пари з Bybit"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.bybit.com/v5/market/tickers?category=linear") as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('retCode') == 0:
                        symbols = [item['symbol'] for item in data['result']['list']]
                        print(f"📋 Знайдено {len(symbols)} ф'ючерсних монет на Bybit")
                        return symbols
                    else:
                        print(f"⚠️ API помилка: {data.get('retMsg')}")
                else:
                    print(f"⚠️ HTTP помилка: {response.status}")
    except Exception as e:
        print(f"❌ Помилка при з'єднанні: {e}")
    
    # Якщо не вдалося отримати список - базовий варіант (аварійний режим)
    print("⚠️ Використовую базовий список монет (аварійний режим)")
    return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", 
            "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT"]

# ============================================
# НАДСИЛАННЯ СПОВІЩЕННЯ
# ============================================
async def send_alert(symbol: str, old_price: float, new_price: float, change_percent: float, alert_count: int):
    is_pump = change_percent > 0
    direction = "🚀🔥 PUMP" if is_pump else "💀📉 DUMP"
    emoji = "📈" if is_pump else "📉"
    
    if new_price < 1:
        price_str = f"{new_price:.8f}"
    else:
        price_str = f"{new_price:.4f}"
    
    message = f"""
{direction}
━━━━━━━━━━━━━━━━━━━━━
🪙 Монета: <code>{symbol}</code>
{emoji} Зміна: <b>{change_percent:+.2f}%</b>
💰 Ціна: <b>{price_str}</b> USDT
📊 Час: {datetime.now().strftime('%H:%M:%S')}
🔄 Сигнал #{alert_count + 1}
━━━━━━━━━━━━━━━━━━━━━
"""
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='HTML')
        print(f"✅ {direction} {symbol}: {change_percent:+.2f}%")
    except Exception as e:
        print(f"❌ Помилка відправки: {e}")

# ============================================
# ПЕРЕВІРКА РУХУ
# ============================================
async def check_and_alert(symbol: str, old_price: float, new_price: float):
    now = datetime.now()
    change_percent = ((new_price - old_price) / old_price) * 100
    abs_change = abs(change_percent)
    
    # Перевіряємо діапазон 3%-50%
    if abs_change < MIN_PUMP_PERCENT or abs_change > MAX_PUMP_PERCENT:
        return False
    
    coin = coins_data.get(symbol, {})
    last_price = coin.get('price')
    
    # Перевіряємо чи був рух в межах 10 хвилин
    if last_price is None:
        # Перша ціна
        coins_data[symbol] = {
            'price': new_price,
            'timestamp': now,
            'last_alert': now,
            'alert_count': 0
        }
        await send_alert(symbol, old_price, new_price, change_percent, 0)
        return True
    
    time_since_last = (now - coin.get('timestamp', now)).total_seconds()
    
    if time_since_last <= TIME_WINDOW_SECONDS:
        # Рух в межах 10 хвилин
        new_count = coin.get('alert_count', 0) + 1
        coins_data[symbol] = {
            'price': new_price,
            'timestamp': now,
            'last_alert': now,
            'alert_count': new_count
        }
        await send_alert(symbol, old_price, new_price, change_percent, new_count)
        return True
    else:
        # Повільний рух - оновлюємо базову ціну
        coins_data[symbol] = {
            'price': new_price,
            'timestamp': now,
            'last_alert': None,
            'alert_count': 0
        }
        return False

# ============================================
# ПІДКЛЮЧЕННЯ ДО WEBSOCKET
# ============================================
async def listen_bybit(symbols):
    print(f"📡 Починаю моніторинг {len(symbols)} ф'ючерсних монет...")
    
    while True:
        try:
            async with websockets.connect(BYBIT_WS_URL, ping_interval=20) as websocket:
                print("🔌 Підключено до Bybit WebSocket")
                
                # Підписуємось на кожну монету окремо
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [f"tickers.{s}" for s in symbols]
                }
                await websocket.send(json.dumps(subscribe_msg))
                print(f"✅ Підписку надіслано на {len(symbols)} каналів")
                
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        
                        if 'success' in data:
                            print("✅ Підписка підтверджена")
                        elif 'topic' in data and 'tickers.' in data['topic']:
                            ticker = data.get('data', {})
                            symbol = ticker.get('symbol', '')
                            try:
                                last_price = float(ticker.get('lastPrice', 0))
                            except (TypeError, ValueError):
                                continue
                            
                            if symbol and last_price > 0:
                                old_data = coins_data.get(symbol, {})
                                old_price = old_data.get('price')
                                
                                if old_price is not None and old_price != last_price:
                                    await check_and_alert(symbol, old_price, last_price)
                                else:
                                    coins_data[symbol] = {
                                        'price': last_price,
                                        'timestamp': datetime.now(),
                                        'last_alert': None,
                                        'alert_count': 0
                                    }
                                    print(f"📊 {symbol}: додано, ціна {last_price}")
                                    
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
    print("🤖 PUMP/DUMP МОНІТОРИНГ BYBIT")
    print("📊 ВСІ Ф'ЮЧЕРСНІ МОНЕТИ")
    print("=" * 55)
    
    # Отримуємо всі монети з Bybit
    all_symbols = await get_all_symbols()
    print(f"⚙️ Моніторинг: {len(all_symbols)} монет")
    print(f"⚙️ Діапазон: {MIN_PUMP_PERCENT}% - {MAX_PUMP_PERCENT}%")
    print(f"⚙️ Часове вікно: {TIME_WINDOW_SECONDS//60} хвилин")
    print("=" * 55)
    
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=f"""🤖 **PUMP/DUMP Бот запущено!**

📊 **Налаштування:**
• Моніторинг: <b>{len(all_symbols)}</b> ф'ючерсних монет
• Діапазон: {MIN_PUMP_PERCENT}% - {MAX_PUMP_PERCENT}%
• Часове вікно: {TIME_WINDOW_SECONDS//60} хвилин
• Повторні сигнали: ✅

🔔 Очікую на стрибки цін...""",
            parse_mode='HTML'
        )
        print("✅ Тестове повідомлення відправлено")
    except Exception as e:
        print(f"❌ Помилка Telegram: {e}")
    
    await listen_bybit(all_symbols)

if __name__ == "__main__":
    asyncio.run(main())
