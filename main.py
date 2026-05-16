import os
import asyncio
import json
import websockets
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

THRESHOLD_PERCENT = 3.0
BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/linear"

last_prices = {}

# ============================================
# ОТРИМАННЯ СПИСКУ ВСІХ МОНЕТ ЧЕРЕЗ REST API
# ============================================
async def get_all_symbols():
    """Отримує список всіх USDT Perpetual пар з Bybit"""
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.bybit.com/v5/market/tickers?category=linear") as response:
            if response.status == 200:
                data = await response.json()
                if data['retCode'] == 0:
                    symbols = [item['symbol'] for item in data['result']['list']]
                    print(f"📋 Знайдено {len(symbols)} монет")
                    return symbols
    print("⚠️ Не вдалося отримати список монет")
    return []

# ============================================
# НАДСИЛАННЯ СПОВІЩЕННЯ
# ============================================
async def send_alert(symbol: str, old_price: float, new_price: float, change_percent: float):
    is_pump = change_percent > 0
    direction = "🚀🔥 PUMP" if is_pump else "💀📉 DUMP"
    emoji = "📈" if is_pump else "📉"
    
    message = f"""
{direction}
━━━━━━━━━━━━━━━━━━━━━
🪙 Монета: <code>{symbol}</code>
{emoji} Зміна: <b>{change_percent:+.2f}%</b>
💰 Ціна: <b>{new_price:,.8f}</b> USDT
📊 Час: {datetime.now().strftime('%H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━━
"""
    await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='HTML')
    print(f"✅ {direction} {symbol}: {change_percent:+.2f}%")

# ============================================
# ПІДКЛЮЧЕННЯ ДО WEBSOCKET ДЛЯ КОЖНОЇ МОНЕТИ
# ============================================
async def listen_bybit():
    symbols = await get_all_symbols()
    if not symbols:
        print("❌ Не вдалося отримати список монет!")
        return
    
    # Створюємо список для підписки на КОЖНУ монету окремо
    ticker_args = [f"tickers.{symbol}" for symbol in symbols]
    print(f"📡 Підписуюсь на {len(ticker_args)} ticker-каналів...")
    
    while True:
        try:
            async with websockets.connect(BYBIT_WS_URL, ping_interval=20) as websocket:
                print("🔌 Підключено до Bybit WebSocket")
                
                # Підписуємось на всі ticker-канали
                subscribe_msg = {
                    "op": "subscribe",
                    "args": ticker_args
                }
                await websocket.send(json.dumps(subscribe_msg))
                print("✅ Підписку надіслано")
                
                async for message in websocket:
                    data = json.loads(message)
                    
                    if 'success' in data:
                        print(f"✅ Підтверджено: {data}")
                    elif 'topic' in data and data['topic'].startswith('tickers.'):
                        ticker = data['data']
                        symbol = ticker.get('symbol', '')
                        last_price = float(ticker.get('lastPrice', 0))
                        
                        if symbol and last_price > 0:
                            if symbol in last_prices:
                                old_price = last_prices[symbol]
                                if old_price > 0:
                                    change = ((last_price - old_price) / old_price) * 100
                                    if abs(change) >= THRESHOLD_PERCENT:
                                        await send_alert(symbol, old_price, last_price, change)
                            last_prices[symbol] = last_price
                            
        except Exception as e:
            print(f"❌ Помилка: {e}")
            await asyncio.sleep(5)

# ============================================
# ЗАПУСК
# ============================================
async def main():
    print("=" * 50)
    print("🤖 PUMP/DUMP МОНІТОРИНГ BYBIT (ФІКС)")
    print("=" * 50)
    
    await bot.send_message(chat_id=CHAT_ID, text="🤖 **PUMP/DUMP Бот запущено! (виправлена версія)**\n\n📊 Моніторинг: ВСІ ф'ючерсні пари\n⚡ Поріг: 3%\n🔔 Очікую на стрибки...", parse_mode='Markdown')
    
    await listen_bybit()

if __name__ == "__main__":
    asyncio.run(main())
