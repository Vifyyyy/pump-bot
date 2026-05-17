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

MIN_PUMP = 3.0
MAX_PUMP = 50.0
TIME_WINDOW = 600

BYBIT_WS = "wss://stream.bybit.com/v5/public/linear"
coins = {}

# ============================================
# ОТРИМАННЯ СПИСКУ ВСІХ МОНЕТ ЧЕРЕЗ REST API (з правильними заголовками)
# ============================================
async def get_all_symbols():
    """Отримує всі ф'ючерсні монети через REST API"""
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Referer': 'https://www.bybit.com/',
        'Origin': 'https://www.bybit.com'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # Спроба 1: стандартний ендпоінт
            async with session.get(
                "https://api.bybit.com/v5/market/tickers?category=linear",
                headers=headers,
                timeout=30
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('retCode') == 0:
                        symbols = [item['symbol'] for item in data['result']['list']]
                        print(f"📋 ✅ Знайдено {len(symbols)} монет (спосіб 1)")
                        return symbols
    except Exception as e:
        print(f"⚠️ Спосіб 1 не вдався: {e}")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Спроба 2: ендпоінт інструментів
            async with session.get(
                "https://api.bybit.com/v5/market/instruments-info?category=linear",
                headers=headers,
                timeout=30
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('retCode') == 0:
                        symbols = [item['symbol'] for item in data['result']['list']]
                        print(f"📋 ✅ Знайдено {len(symbols)} монет (спосіб 2)")
                        return symbols
    except Exception as e:
        print(f"⚠️ Спосіб 2 не вдався: {e}")
    
    print("❌ Не вдалося отримати список монет!")
    return None

# ============================================
# ВІДПРАВКА СПОВІЩЕННЯ
# ============================================
async def send_alert(symbol, old_price, new_price, change, count):
    is_pump = change > 0
    dir_text = "🚀🔥 PUMP" if is_pump else "💀📉 DUMP"
    price_str = f"{new_price:.8f}" if new_price < 1 else f"{new_price:.4f}"
    
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
# ОСНОВНИЙ МОНІТОРИНГ
# ============================================
async def monitor():
    # Отримуємо список всіх монет
    symbols = await get_all_symbols()
    
    if not symbols:
        await bot.send_message(chat_id=CHAT_ID, text="❌ Не вдалося отримати список монет! Бот зупинено.")
        return
    
    print(f"📡 Починаю моніторинг {len(symbols)} монет...")
    
    # Відправляємо тестове повідомлення
    await bot.send_message(
        chat_id=CHAT_ID,
        text=f"""🤖 **PUMP/DUMP Бот запущено!**

📊 Моніторинг: <b>{len(symbols)}</b> ф'ючерсних монет
⚡ Діапазон: {MIN_PUMP}% - {MAX_PUMP}%
⏱️ Часове вікно: 10 хвилин
🔄 Повторні сигнали: ✅

🔔 Очікую на стрибки цін...""",
        parse_mode='HTML'
    )
    
    # Підключаємося до WebSocket для отримання цін
    while True:
        try:
            async with websockets.connect(BYBIT_WS, ping_interval=20) as ws:
                print("🔌 Підключено до WebSocket")
                
                # Підписуємось на всі монети (розбиваємо на частини)
                batch_size = 100
                for i in range(0, len(symbols), batch_size):
                    batch = symbols[i:i+batch_size]
                    subscribe_msg = {
                        "op": "subscribe",
                        "args": [f"tickers.{s}" for s in batch]
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    print(f"📡 Підписано на {len(batch)} монет...")
                    await asyncio.sleep(0.5)
                
                print(f"✅ Підписку завершено на {len(symbols)} каналів")
                
                # Обробка повідомлень
                async for message in ws:
                    try:
                        data = json.loads(message)
                        
                        if 'topic' in data and 'tickers.' in data['topic']:
                            ticker = data.get('data', {})
                            symbol = ticker.get('symbol')
                            
                            if not symbol:
                                continue
                            
                            try:
                                price = float(ticker.get('lastPrice', 0))
                            except:
                                continue
                            
                            if price <= 0:
                                continue
                            
                            now = datetime.now()
                            old_data = coins.get(symbol)
                            
                            if old_data:
                                old_price = old_data.get('price')
                                if old_price and old_price != price:
                                    change = ((price - old_price) / old_price) * 100
                                    abs_change = abs(change)
                                    
                                    if MIN_PUMP <= abs_change <= MAX_PUMP:
                                        last_time = old_data.get('time', now)
                                        time_diff = (now - last_time).total_seconds()
                                        
                                        if time_diff <= TIME_WINDOW:
                                            count = old_data.get('count', 0) + 1
                                            await send_alert(symbol, old_price, price, change, count)
                                            coins[symbol] = {'price': price, 'time': now, 'count': count}
                                        else:
                                            coins[symbol] = {'price': price, 'time': now, 'count': 0}
                                    else:
                                        coins[symbol] = {'price': price, 'time': now, 'count': 0}
                                else:
                                    coins[symbol] = {'price': price, 'time': now, 'count': 0}
                            else:
                                coins[symbol] = {'price': price, 'time': now, 'count': 0}
                                
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
    
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
