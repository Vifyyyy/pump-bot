import os
import asyncio
import aiohttp
from datetime import datetime
from telegram import Bot

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHANNEL_ID")

bot = Bot(token=BOT_TOKEN)

MIN_PUMP = 3.0
MAX_PUMP = 50.0
CHECK_INTERVAL = 5
TIME_WINDOW = 900

# MEXC Futures API (ТІЛЬКИ Ф'ЮЧЕРСИ)
MEXC_FUTURES_URL = "https://api.mexc.com/api/v1/contract/detail"

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

async def get_futures_symbols():
    """Отримує список всіх USDT-M ф'ючерсів MEXC"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(MEXC_FUTURES_URL, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"📡 Відповідь MEXC Futures: {type(data)}")
                    
                    # Перевіряємо різні формати
                    contracts = []
                    if isinstance(data, dict):
                        if data.get('code') == 200:
                            contracts = data.get('data', [])
                        elif data.get('success'):
                            contracts = data.get('data', [])
                    elif isinstance(data, list):
                        contracts = data
                    
                    # Фільтруємо USDT-M ф'ючерси
                    symbols = []
                    for c in contracts:
                        if isinstance(c, dict):
                            symbol = c.get('symbol', '')
                            if symbol.endswith('USDT'):
                                symbols.append(symbol)
                    
                    print(f"📋 Знайдено {len(symbols)} USDT-M ф'ючерсів на MEXC")
                    return symbols, contracts
                else:
                    print(f"❌ HTTP {response.status}")
    except Exception as e:
        print(f"❌ Помилка: {e}")
    
    return None, None

async def get_ticker_price(session, symbol):
    """Отримує ціну для ф'ючерсної пари"""
    url = f"https://api.mexc.com/api/v3/ticker/price?symbol={symbol}"
    try:
        async with session.get(url, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                return float(data.get('price', 0))
    except:
        pass
    return 0

async def monitor():
    global all_symbols
    
    print("🔄 Отримання списку USDT-M ф'ючерсів MEXC...")
    
    # Отримуємо список ф'ючерсів
    symbols, _ = await get_futures_symbols()
    if not symbols:
        await bot.send_message(chat_id=CHAT_ID, text="❌ Не вдалося отримати список ф'ючерсів MEXC!")
        return
    
    all_symbols = symbols
    print(f"📡 Починаю моніторинг {len(all_symbols)} USDT-M ф'ючерсів...")
    
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
    
    # Ініціалізуємо початкові ціни
    async with aiohttp.ClientSession() as init_session:
        for symbol in all_symbols[:20]:  # Спочатку перші 20
            price = await get_ticker_price(init_session, symbol)
            if price > 0:
                coins_data[symbol] = {'price': price, 'time': datetime.now(), 'count': 0}
                print(f"📊 {symbol}: {price}")
    
    print(f"✅ Ініціалізовано {len(coins_data)} ф'ючерсів")
    
    # Основний цикл
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                now = datetime.now()
                changes = 0
                
                for symbol in all_symbols:
                    price = await get_ticker_price(session, symbol)
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
    print("🤖 PUMP/DUMP MEXC FUTURES (USDT-M)")
    print("=" * 50)
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
