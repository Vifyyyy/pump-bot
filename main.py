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

MIN_PUMP = 3.0
MAX_PUMP = 50.0
TIME_WINDOW = 600

# Binance Futures WebSocket (всі монети в одному каналі)
BINANCE_WS = "wss://fstream.binance.com/ws/!ticker@arr"

# Дані монет
coins_data = {}
all_symbols = set()

# ============================================
# ВІДПРАВКА СПОВІЩЕННЯ
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
        print(f"✅ {dir_text} {symbol}: {change:+.2f}% (сигнал #{count})")
    except Exception as e:
        print(f"❌ Помилка: {e}")

# ============================================
# ОСНОВНИЙ МОНІТОРИНГ (ТІЛЬКИ WEBSOCKET)
# ============================================
async def monitor():
    print("🔌 Підключення до Binance WebSocket...")
    
    while True:
        try:
            async with websockets.connect(BINANCE_WS, ping_interval=20) as ws:
                print("✅ Підключено! Отримую всі ціни...")
                
                # Відправляємо повідомлення про запуск
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text="""🤖 **PUMP/DUMP Бот (Binance Futures) запущено!**

📊 **Моніторинг:** ВСІ ф'ючерсні монети (через WebSocket)
⚡ **Діапазон:** 3% - 50%
⏱️ **Часове вікно:** 10 хвилин
🔄 **Повторні сигнали:** ✅

📡 **Збір монет:** автоматично з потоку даних

🔔 Очікую на стрибки цін...""",
                    parse_mode='Markdown'
                )
                print("✅ Тестове повідомлення відправлено")
                
                async for message in ws:
                    try:
                        tickers = json.loads(message)
                        
                        for ticker in tickers:
                            symbol = ticker.get('s', '')
                            
                            # Фільтруємо USDT пари
                            if not symbol.endswith('USDT'):
                                continue
                            
                            # Додаємо символ до списку
                            if symbol not in all_symbols:
                                all_symbols.add(symbol)
                                if len(all_symbols) % 100 == 0:
                                    print(f"📊 Знайдено {len(all_symbols)} монет...")
                            
                            try:
                                price = float(ticker.get('c', 0))
                            except:
                                continue
                            
                            if price <= 0:
                                continue
                            
                            now = datetime.now()
                            old = coins_data.get(symbol)
                            
                            if old:
                                old_price = old.get('price')
                                if old_price and old_price != price:
                                    change = ((price - old_price) / old_price) * 100
                                    abs_change = abs(change)
                                    
                                    if MIN_PUMP <= abs_change <= MAX_PUMP:
                                        last_time = old.get('time', now)
                                        time_diff = (now - last_time).total_seconds()
                                        
                                        if time_diff <= TIME_WINDOW:
                                            count = old.get('count', 0) + 1
                                            await send_alert(symbol, old_price, price, change, count)
                                            coins_data[symbol] = {'price': price, 'time': now, 'count': count}
                                        else:
                                            coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                    else:
                                        coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                else:
                                    coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                            else:
                                coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                
                    except json.JSONDecodeError:
                        continue
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
    print("🤖 PUMP/DUMP МОНІТОРИНГ BINANCE FUTURES")
    print("📡 WebSocket (обхід блокування 451)")
    print("=" * 55)
    
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
