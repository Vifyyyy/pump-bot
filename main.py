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

MIN_PUMP_PERCENT = 3.0
MAX_PUMP_PERCENT = 50.0
TIME_WINDOW_SECONDS = 600

BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/linear"
coins_data = {}

# ============================================
# ОТРИМАННЯ ВСІХ МОНЕТ (З ПРАВИЛЬНИМИ ЗАГОЛОВКАМИ)
# ============================================
async def get_all_symbols():
    """Отримує ВСІ монети з Bybit з правильними заголовками"""
    
    # Заголовки, щоб Bybit думав, що це браузер
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9',
        'Source': 'web'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.bybit.com/v5/market/tickers?category=linear",
                headers=headers,
                timeout=30
            ) as response:
                print(f"📡 Статус: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    if data.get('retCode') == 0:
                        symbols = [item['symbol'] for item in data['result']['list']]
                        print(f"📋 ✅ Знайдено {len(symbols)} ф'ючерсних монет")
                        return symbols
                    else:
                        print(f"⚠️ Помилка: {data.get('retMsg')}")
                else:
                    print(f"⚠️ HTTP {response.status}")
                    
    except Exception as e:
        print(f"❌ Помилка: {e}")
    
    print("❌ НЕ ВДАЛОСЯ ОТРИМАТИ СПИСОК!")
    return None

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
    
    if abs_change < MIN_PUMP_PERCENT or abs_change > MAX_PUMP_PERCENT:
        return False
    
    coin = coins_data.get(symbol, {})
    time_since_last = (now - coin.get('timestamp', now)).total_seconds() if coin.get('timestamp') else TIME_WINDOW_SECONDS + 1
    
    if time_since_last <= TIME_WINDOW_SECONDS:
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
    if not symbols:
        print("❌ Немає списку монет!")
        return
    
    print(f"📡 Моніторинг {len(symbols)} монет...")
    
    while True:
        try:
            async with websockets.connect(BYBIT_WS_URL, ping_interval=20) as websocket:
                print("🔌 Підключено до WebSocket")
                
                # Підписуємось на всі монети
                subscribe_msg = {
                    "op": "subscribe",
                    "args": [f"tickers.{s}" for s in symbols]
                }
                await websocket.send(json.dumps(subscribe_msg))
                print(f"✅ Підписка на {len(symbols)} каналів")
                
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        
                        if 'success' in data:
                            print("✅ Підтверджено")
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
                                    if len(coins_data) % 50 == 0:
                                        print(f"📊 Завантажено {len(coins_data)}/{len(symbols)}")
                                    
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
    print("=" * 55)
    
    all_symbols = await get_all_symbols()
    
    if not all_symbols:
        print("❌ НЕ ВДАЛОСЯ ЗАВАНТАЖИТИ МОНЕТИ!")
        await bot.send_message(
            chat_id=CHAT_ID,
            text="❌ Не вдалося завантажити список монет з Bybit API.\nBybit блокує Railway IP."
        )
        return
    
    print(f"✅ {len(all_symbols)} монет завантажено")
    print("=" * 55)
    
    await bot.send_message(
        chat_id=CHAT_ID,
        text=f"""🤖 **PUMP/DUMP Бот запущено!**

📊 Моніторинг: <b>{len(all_symbols)}</b> ф'ючерсних монет
⚡ Діапазон: {MIN_PUMP_PERCENT}% - {MAX_PUMP_PERCENT}%
⏱️ Часове вікно: {TIME_WINDOW_SECONDS//60} хвилин

🔔 Очікую на стрибки цін...""",
        parse_mode='HTML'
    )
    
    await listen_bybit(all_symbols)

if __name__ == "__main__":
    asyncio.run(main())
