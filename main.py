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

# KuCoin Futures API
KUCOIN_FUTURES_URL = "https://api-futures.kucoin.com/api/v1/allTickers"

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

async def monitor():
    global all_symbols
    print("🔄 Підключення до KuCoin Futures API...")
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(KUCOIN_FUTURES_URL, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        print(f"📡 Тип даних: {type(data)}")
                        
                        # Перевіряємо різні формати
                        tickers = []
                        if isinstance(data, list):
                            tickers = data
                        elif isinstance(data, dict):
                            if data.get('code') == '200000':
                                tickers_data = data.get('data', {})
                                if isinstance(tickers_data, list):
                                    tickers = tickers_data
                                elif isinstance(tickers_data, dict):
                                    tickers = tickers_data.get('ticker', [])
                        else:
                            print(f"⚠️ Невідомий формат")
                            await asyncio.sleep(CHECK_INTERVAL)
                            continue
                        
                        if not tickers:
                            print("⚠️ Немає даних")
                            await asyncio.sleep(CHECK_INTERVAL)
                            continue
                        
                        # Фільтруємо USDT
                        usdt_tickers = []
                        for t in tickers:
                            if isinstance(t, dict):
                                symbol = t.get('symbol', '')
                                if symbol.endswith('USDT'):
                                    usdt_tickers.append(t)
                        
                        if not all_symbols:
                            all_symbols = [t.get('symbol') for t in usdt_tickers]
                            print(f"📋 Знайдено {len(all_symbols)} USDT пар")
                            
                            for t in usdt_tickers:
                                try:
                                    p = float(t.get('last', 0))
                                    if p > 0:
                                        coins_data[t.get('symbol')] = {'price': p, 'time': datetime.now(), 'count': 0}
                                except: pass
                            
                            await bot.send_message(
                                chat_id=CHAT_ID,
                                text=f"""🤖 **PUMP/DUMP Бот (KuCoin) запущено!**

📊 **Моніторинг:** {len(all_symbols)} USDT пар
⚡ **Діапазон:** {MIN_PUMP}% - {MAX_PUMP}%
⏱️ **Часове вікно:** {TIME_WINDOW//60} хвилин

🔔 Очікую на стрибки цін...""",
                                parse_mode='Markdown'
                            )
                        
                        now = datetime.now()
                        changes = 0
                        
                        for t in usdt_tickers:
                            sym = t.get('symbol')
                            try:
                                price = float(t.get('last', 0))
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
                        
                        print(f"📊 Перевірено {len(usdt_tickers)} пар | змін: {changes} | {datetime.now().strftime('%H:%M:%S')}")
                    else:
                        print(f"❌ HTTP {response.status}")
        except Exception as e:
            print(f"❌ Помилка: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

async def main():
    print("=" * 50)
    print("🤖 PUMP/DUMP KUCOIN")
    print("=" * 50)
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
