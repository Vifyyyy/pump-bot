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
MIN_PUMP = 3.0
MAX_PUMP = 50.0
CHECK_INTERVAL = 5
TIME_WINDOW = 900

# KuCoin Futures API
KUCOIN_URL = "https://api-futures.kucoin.com/api/v1/allTickers"

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
    print("🔄 Підключення до KuCoin API...")
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(KUCOIN_URL, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"📡 Отримано відповідь від KuCoin")
                        
                        if data.get('code') == '200000':
                            tickers_data = data.get('data', {})
                            
                            # Перевіряємо формат даних
                            if isinstance(tickers_data, dict):
                                tickers = tickers_data.get('ticker', [])
                            elif isinstance(tickers_data, list):
                                tickers = tickers_data
                            else:
                                print(f"⚠️ Невідомий формат: {type(tickers_data)}")
                                await asyncio.sleep(CHECK_INTERVAL)
                                continue
                            
                            if not tickers:
                                print("⚠️ Немає даних про tickers")
                                await asyncio.sleep(CHECK_INTERVAL)
                                continue
                            
                            now = datetime.now()
                            changes = 0
                            
                            for ticker in tickers:
                                symbol = ticker.get('symbol', '')
                                if not symbol.endswith('USDT'):
                                    continue
                                
                                try:
                                    price = float(ticker.get('last', 0))
                                except (ValueError, TypeError):
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
                                                changes += 1
                                            else:
                                                coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                        else:
                                            coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                else:
                                    coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                            
                            print(f"📊 Перевірено {len(tickers)} пар | змін: {changes} | {datetime.now().strftime('%H:%M:%S')}")
                        else:
                            print(f"⚠️ Помилка API: {data.get('msg')}")
                    else:
                        print(f"❌ HTTP {response.status}")
                        
        except asyncio.TimeoutError:
            print("⏰ Таймаут")
        except Exception as e:
            print(f"❌ Помилка: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

# ============================================
# ЗАПУСК
# ============================================
async def main():
    print("=" * 55)
    print("🤖 PUMP/DUMP МОНІТОРИНГ KUCOIN")
    print(f"⏱️ Часове вікно: {TIME_WINDOW//60} хвилин")
    print("=" * 55)
    
    # Тестове повідомлення
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=f"""🤖 **PUMP/DUMP Бот (KuCoin) запущено!**

⚡ **Діапазон:** {MIN_PUMP}% - {MAX_PUMP}%
⏱️ **Часове вікно:** {TIME_WINDOW//60} хвилин
🔄 **Повторні сигнали:** ✅

🔔 Очікую на стрибки цін...""",
            parse_mode='Markdown'
        )
        print("✅ Тестове повідомлення відправлено")
    except Exception as e:
        print(f"❌ Помилка Telegram: {e}")
    
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
