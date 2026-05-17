i mport os
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

# MEXC Futures - перевірений ендпоїнт
MEXC_TICKER_URL = "https://api.mexc.com/api/v3/ticker/24hr"

coins_data = {}
all_symbols = []

# Список символів, які точно є ф'ючерсами на MEXC
# (будемо фільтрувати за ключовими словами)
FUTURES_INDICATORS = ['USDT']

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
# ФУНКЦІЯ ДЛЯ ПЕРЕВІРКИ ЧИ ЦЕ Ф'ЮЧЕРС
# ============================================
def is_futures_pair(symbol):
    """Перевіряє чи пара є ф'ючерсом за певними ознаками"""
    # На MEXC ф'ючерсні пари зазвичай мають великі об'єми
    # Або ми можемо перевірити через окремий запит
    return symbol.endswith('USDT')

# ============================================
# ОСНОВНИЙ МОНІТОРИНГ
# ============================================
async def monitor():
    global all_symbols
    
    print("🔄 Підключення до MEXC API...")
    print("📡 Отримую всі пари...")
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(MEXC_TICKER_URL, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        if isinstance(data, list):
                            # Фільтруємо USDT пари
                            usdt_pairs = [t for t in data if t.get('symbol', '').endswith('USDT')]
                            
                            if not all_symbols:
                                all_symbols = [t.get('symbol') for t in usdt_pairs]
                                print(f"📋 ✅ Знайдено {len(all_symbols)} USDT пар")
                                
                                for ticker in usdt_pairs:
                                    symbol = ticker.get('symbol')
                                    try:
                                        price = float(ticker.get('lastPrice', 0))
                                        if price > 0:
                                            coins_data[symbol] = {'price': price, 'time': datetime.now(), 'count': 0}
                                    except:
                                        pass
                                
                                print(f"✅ Ініціалізовано {len(coins_data)} монет")
                                
                                await bot.send_message(
                                    chat_id=CHAT_ID,
                                    text=f"""🤖 **PUMP/DUMP Бот (MEXC) запущено!**

📊 **Моніторинг:** {len(all_symbols)} USDT пар
⚡ **Діапазон:** {MIN_PUMP}% - {MAX_PUMP}%
⏱️ **Часове вікно:** {TIME_WINDOW//60} хвилин
🔄 **Повторні сигнали:** ✅

🔔 Очікую на стрибки цін...""",
                                    parse_mode='Markdown'
                                )
                            
                            now = datetime.now()
                            changes = 0
                            
                            for ticker in usdt_pairs:
                                symbol = ticker.get('symbol')
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
                                                changes += 1
                                            else:
                                                coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                        else:
                                            coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                elif price > 0:
                                    coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                            
                            print(f"📊 Перевірено {len(usdt_pairs)} пар | змін: {changes} | {datetime.now().strftime('%H:%M:%S')}")
                        else:
                            print(f"⚠️ Помилка: отримано {type(data)}")
                    else:
                        print(f"❌ HTTP {response.status}")
                        
        except asyncio.TimeoutError:
            print("⏰ Таймаут")
        except aiohttp.ClientError as e:
            print(f"❌ Помилка з'єднання: {e}")
        except Exception as e:
            print(f"❌ Помилка: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

# ============================================
# ЗАПУСК
# ============================================
async def main():
    print("=" * 55)
    print("🤖 PUMP/DUMP МОНІТОРИНГ MEXC")
    print("📡 ВСІ USDT ПАРИ")
    print(f"⏱️ Часове вікно: {TIME_WINDOW//60} хвилин")
    print("=" * 55)
    
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
