import os
import asyncio
import aiohttp
from datetime import datetime
from telegram import Bot

BOT_TOKEN = "8902921890:AAGgdbhGx3KgBsASB6uk3V2WnIJJNy__en4"
CHAT_ID = "-1003846362726"

bot = Bot(token=BOT_TOKEN)

MIN_PUMP = 3.0
MAX_PUMP = 50.0
CHECK_INTERVAL = 5
TIME_WINDOW = 900

# BingX Futures API
BINGX_CONTRACTS_URL = "https://open-api.bingx.com/openApi/swap/v2/quote/contracts"
BINGX_PRICE_URL = "https://open-api.bingx.com/openApi/swap/v2/quote/price"

coins_data = {}
all_symbols = []

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

async def get_all_symbols():
    """Отримує список ВСІХ USDT-M ф'ючерсів BingX"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BINGX_CONTRACTS_URL, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == 0:
                        contracts = data.get('data', [])
                        symbols = []
                        for c in contracts:
                            symbol = c.get('symbol', '')
                            if symbol.endswith('-USDT'):
                                symbol = symbol.replace('-', '')
                                symbols.append(symbol)
                        print(f"📋 Знайдено {len(symbols)} USDT-M ф'ючерсів на BingX")
                        return symbols
    except Exception as e:
        print(f"❌ Помилка отримання списку: {e}")
    return None

async def get_price(session, symbol):
    url = f"{BINGX_PRICE_URL}?symbol={symbol}"
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('code') == 0:
                    return float(data.get('data', {}).get('price', 0))
    except:
        pass
    return 0

async def monitor():
    global all_symbols
    
    print("🔄 Отримання списку ВСІХ ф'ючерсів BingX...")
    
    # Отримуємо всі ф'ючерсні пари
    all_symbols = await get_all_symbols()
    if not all_symbols:
        print("❌ Не вдалося отримати список, використовую базовий")
        all_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    
    print(f"📡 Починаю моніторинг {len(all_symbols)} USDT-M ф'ючерсів...")
    
    await bot.send_message(
        chat_id=CHAT_ID,
        text=f"""🤖 **PUMP/DUMP Бот (BingX Futures) запущено!**

📊 **Моніторинг:** {len(all_symbols)} USDT-M ф'ючерсів
⚡ **Діапазон:** {MIN_PUMP}% - {MAX_PUMP}%
⏱️ **Часове вікно:** {TIME_WINDOW//60} хвилин
🔄 **Повторні сигнали:** ✅

🔔 Очікую на стрибки цін...""",
        parse_mode='Markdown'
    )
    
    # Ініціалізуємо початкові ціни
    async with aiohttp.ClientSession() as init_session:
        count = 0
        for symbol in all_symbols:
            price = await get_price(init_session, symbol)
            if price > 0:
                coins_data[symbol] = {'price': price, 'time': datetime.now(), 'count': 0}
                count += 1
            await asyncio.sleep(0.1)  # Невелика затримка
        print(f"✅ Ініціалізовано {count} ф'ючерсів")
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                now = datetime.now()
                changes = 0
                
                for symbol in all_symbols:
                    price = await get_price(session, symbol)
                    if price <= 0:
                        continue
                    
                    old = coins_data.get(symbol)
                    if old and old.get('price'):
                        old_price = old['price']
                        if old_price != price:
                            change = ((price - old_price) / old_price) * 100
                            if MIN_PUMP <= abs(change) <= MAX_PUMP:
                                last_time = old.get('time', now)
                                if (now - last_time).total_seconds() <= TIME_WINDOW:
                                    cnt = old.get('count', 0) + 1
                                    await send_alert(symbol, old_price, price, change, cnt)
                                    coins_data[symbol] = {'price': price, 'time': now, 'count': cnt}
                                    changes += 1
                                else:
                                    coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                            else:
                                coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                    elif price > 0:
                        coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                
                print(f"📊 Перевірено {len(all_symbols)} ф'ючерсів | змін: {changes} | {datetime.now().strftime('%H:%M:%S')}")
                        
        except Exception as e:
            print(f"❌ Помилка: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

async def main():
    print("=" * 50)
    print("🤖 PUMP/DUMP BINGX FUTURES (ВСІ МОНЕТИ)")
    print("=" * 50)
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
