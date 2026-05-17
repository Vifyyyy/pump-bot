import os
import asyncio
import aiohttp
import hashlib
import hmac
import time
from datetime import datetime
from telegram import Bot

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHANNEL_ID")

# ТВОЇ API КЛЮЧІ З MEXC
API_KEY = "mxOvglljSPq8BPGXrZ"
API_SECRET = "77a3022b16f84b9cae2a8662c3a7bd42"

bot = Bot(token=BOT_TOKEN)

MIN_PUMP = 3.0
MAX_PUMP = 50.0
CHECK_INTERVAL = 5
TIME_WINDOW = 900

# MEXC Futures API (з авторизацією)
MEXC_FUTURES_URL = "https://api.mexc.com/api/v3/ticker/24hr"

coins_data = {}
all_symbols = []

def generate_signature(params, secret):
    """Генерує підпис для авторизації"""
    query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
    signature = hmac.new(secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    return signature

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
    await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='HTML')
    print(f"✅ {dir_text} {symbol}: {change:+.2f}%")

async def monitor():
    global all_symbols
    print("🔄 Підключення до MEXC Futures API з авторизацією...")
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                # Додаємо заголовки авторизації
                headers = {
                    'X-MEXC-APIKEY': API_KEY,
                    'Content-Type': 'application/json'
                }
                
                async with session.get(MEXC_FUTURES_URL, headers=headers, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if isinstance(data, list):
                            # Фільтруємо USDT пари (ф'ючерси)
                            usdt_pairs = [t for t in data if t.get('symbol', '').endswith('USDT')]
                            
                            if not all_symbols:
                                all_symbols = [t.get('symbol') for t in usdt_pairs]
                                print(f"📋 Знайдено {len(all_symbols)} USDT-M ф'ючерсів на MEXC")
                                
                                for t in usdt_pairs:
                                    try:
                                        p = float(t.get('lastPrice', 0))
                                        if p > 0:
                                            coins_data[t.get('symbol')] = {'price': p, 'time': datetime.now(), 'count': 0}
                                    except: pass
                                
                                print(f"✅ Ініціалізовано {len(coins_data)} ф'ючерсів")
                                
                                await bot.send_message(
                                    chat_id=CHAT_ID,
                                    text=f"""🤖 **PUMP/DUMP Бот (MEXC Futures) запущено!**

📊 **Моніторинг:** {len(all_symbols)} USDT-M ф'ючерсних пар
⚡ **Діапазон:** {MIN_PUMP}% - {MAX_PUMP}%
⏱️ **Часове вікно:** {TIME_WINDOW//60} хвилин
🔄 **Повторні сигнали:** ✅

🔔 Очікую на стрибки цін...""",
                                    parse_mode='Markdown'
                                )
                            
                            now = datetime.now()
                            changes = 0
                            
                            for t in usdt_pairs:
                                sym = t.get('symbol')
                                try:
                                    price = float(t.get('lastPrice', 0))
                                except: continue
                                if price <= 0: continue
                                
                                old = coins_data.get(sym)
                                if old and old.get('price'):
                                    old_p = old['price']
                                    if old_p != price:
                                        change = ((price - old_p) / old_p) * 100
                                        if MIN_PUMP <= abs(change) <= MAX_PUMP:
                                            last_t = old.get('time', now)
                                            if (now - last_t).total_seconds() <= TIME_WINDOW:
                                                cnt = old.get('count', 0) + 1
                                                await send_alert(sym, old_p, price, change, cnt)
                                                coins_data[sym] = {'price': price, 'time': now, 'count': cnt}
                                                changes += 1
                                            else:
                                                coins_data[sym] = {'price': price, 'time': now, 'count': 0}
                                        else:
                                            coins_data[sym] = {'price': price, 'time': now, 'count': 0}
                                else:
                                    coins_data[sym] = {'price': price, 'time': now, 'count': 0}
                            
                            print(f"📊 Перевірено {len(usdt_pairs)} ф'ючерсів | змін: {changes} | {datetime.now().strftime('%H:%M:%S')}")
                        else:
                            print(f"⚠️ Невідомий формат")
                    else:
                        print(f"❌ HTTP {response.status}")
        except Exception as e:
            print(f"❌ Помилка: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

async def main():
    print("=" * 50)
    print("🤖 PUMP/DUMP MEXC FUTURES (USDT-M)")
    print("📡 З API авторизацією")
    print("=" * 50)
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
