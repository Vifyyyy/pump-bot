import os
import asyncio
import json
import websockets
from datetime import datetime
from telegram import Bot

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

# Список популярних монет (якщо WebSocket не дасть всі)
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", 
                    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT",
                    "UNIUSDT", "ATOMUSDT", "LTCUSDT", "BCHUSDT", "NEARUSDT",
                    "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "SUIUSDT"]

async def listen_bybit():
    print("🔌 Підключаюсь до Bybit WebSocket...")
    print("📡 Отримую всі монети через WebSocket...")
    
    all_symbols = set()
    
    async with websockets.connect(BYBIT_WS_URL, ping_interval=20) as websocket:
        # Підписуємось на всі ticker-канали через *
        subscribe_msg = {"op": "subscribe", "args": ["tickers.*"]}
        await websocket.send(json.dumps(subscribe_msg))
        print("✅ Підписка на всі канали")
        
        # Збираємо монети протягом 10 секунд
        start_time = datetime.now()
        while (datetime.now() - start_time).seconds < 10:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=1)
                data = json.loads(message)
                
                if 'topic' in data and 'tickers.' in data['topic']:
                    symbol = data.get('data', {}).get('symbol')
                    if symbol:
                        all_symbols.add(symbol)
                        price = data.get('data', {}).get('lastPrice')
                        if len(all_symbols) % 50 == 0:
                            print(f"📊 Знайдено {len(all_symbols)} монет...")
            except asyncio.TimeoutError:
                continue
        
        symbols_list = list(all_symbols) if all_symbols else DEFAULT_SYMBOLS
        print(f"📋 ✅ Всього знайдено {len(symbols_list)} монет")
        
        # Перепідписуємось на кожну монету окремо
        subscribe_msg = {"op": "subscribe", "args": [f"tickers.{s}" for s in symbols_list]}
        await websocket.send(json.dumps(subscribe_msg))
        print(f"✅ Підписка на {len(symbols_list)} каналів")
        
        # Основний цикл обробки
        async for message in websocket:
            try:
                data = json.loads(message)
                if 'topic' in data and 'tickers.' in data['topic']:
                    ticker = data.get('data', {})
                    symbol = ticker.get('symbol', '')
                    try:
                        last_price = float(ticker.get('lastPrice', 0))
                    except:
                        continue
                    
                    if symbol and last_price > 0:
                        old = coins_data.get(symbol, {}).get('price')
                        now = datetime.now()
                        
                        if old and old != last_price:
                            change = ((last_price - old) / old) * 100
                            if MIN_PUMP_PERCENT <= abs(change) <= MAX_PUMP_PERCENT:
                                coin = coins_data.get(symbol, {})
                                time_diff = (now - coin.get('timestamp', now)).total_seconds()
                                
                                if time_diff <= TIME_WINDOW_SECONDS:
                                    count = coin.get('alert_count', 0) + 1
                                    direction = "🚀🔥 PUMP" if change > 0 else "💀📉 DUMP"
                                    price_str = f"{last_price:.8f}" if last_price < 1 else f"{last_price:.4f}"
                                    
                                    msg = f"{direction}\n━━━━━━━━━━━━━━━━━━━━━\n🪙 {symbol}\n📊 Зміна: {change:+.2f}%\n💰 Ціна: {price_str} USDT\n🕐 {now.strftime('%H:%M:%S')}\n🔄 Сигнал #{count+1}"
                                    await bot.send_message(chat_id=CHAT_ID, text=msg)
                                    print(f"✅ {direction} {symbol}: {change:+.2f}%")
                                
                                coins_data[symbol] = {'price': last_price, 'timestamp': now, 'alert_count': count if time_diff <= TIME_WINDOW_SECONDS else 0}
                        else:
                            coins_data[symbol] = {'price': last_price, 'timestamp': datetime.now(), 'alert_count': 0}
            except:
                continue

async def main():
    await bot.send_message(chat_id=CHAT_ID, text="🤖 PUMP/DUMP Бот запущено!\n📊 Завантажую всі монети...")
    await listen_bybit()

if __name__ == "__main__":
    asyncio.run(main())
