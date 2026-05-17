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

BITUNIX_TICKERS_URL = "https://api.bitunix.com/openapi/v1/market/tickers"

coins_data = {}

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
# ОСНОВНИЙ МОНІТОРИНГ
# ============================================
async def monitor():
    print("🔄 Підключення до Bitunix API...")
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(BITUNIX_TICKERS_URL, headers=headers, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('code') == 0:
                            tickers = data.get('data', [])
                            now = datetime.now()
                            
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
                                            if (now - last_time).total_seconds() <= TIME_WINDOW:
                                                count = old.get('count', 0) + 1
                                                await send_alert(symbol, old_price, price, change, count)
                                                coins_data[symbol] = {'price': price, 'time': now, 'count': count}
                                            else:
                                                coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                        else:
                                            coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                elif price > 0:
                                    coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                            
                            print(f"📊 Перевірено {len(tickers)} пар | {datetime.now().strftime('%H:%M:%S')}")
                        else:
                            print(f"⚠️ Помилка: {data.get('msg')}")
                    else:
                        print(f"❌ HTTP {response.status}")
                        
        except Exception as e:
            print(f"❌ Помилка: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

# ============================================
# ЗАПУСК
# ============================================
async def main():
    print("=" * 55)
    print("🤖 PUMP/DUMP МОНІТОРИНГ BITUNIX")
    print(f"⏱️ Часове вікно: {TIME_WINDOW//60} хвилин")
    print("=" * 55)
    
    await bot.send_message(
        chat_id=CHAT_ID,
        text=f"""🤖 **PUMP/DUMP Бот (Bitunix) запущено!**

⚡ **Діапазон:** {MIN_PUMP}% - {MAX_PUMP}%
⏱️ **Часове вікно:** {TIME_WINDOW//60} хвилин
🔄 **Повторні сигнали:** ✅

🔔 Очікую на стрибки цін...""",
        parse_mode='Markdown'
    )
    
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
