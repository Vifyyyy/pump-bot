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

# Параметри моніторингу
MIN_PUMP = 3.0          # Мінімальний рух 3%
MAX_PUMP = 50.0         # Максимальний рух 50%
TIME_WINDOW = 600       # 10 хвилин (600 секунд)

BYBIT_WS = "wss://stream.bybit.com/v5/public/linear"

# Зберігаємо дані кожної монети
coins = {}

# ============================================
# ВІДПРАВКА СПОВІЩЕННЯ В TELEGRAM
# ============================================
async def send_alert(symbol, old_price, new_price, change, count):
    is_pump = change > 0
    dir_text = "🚀🔥 PUMP" if is_pump else "💀📉 DUMP"
    
    # Форматуємо ціну (8 знаків для монет дешевших 1$, 4 знаки для дорогих)
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
        print(f"❌ Помилка відправки: {e}")

# ============================================
# ГОЛОВНИЙ МОНІТОРИНГ
# ============================================
async def monitor():
    print("🔌 Підключення до Bybit WebSocket...")
    
    async with websockets.connect(BYBIT_WS, ping_interval=20) as ws:
        # Підписуємось на ВСІ ticker-канали через *
        await ws.send(json.dumps({"op": "subscribe", "args": ["tickers.*"]}))
        print("✅ Підписано на tickers.*")
        
        # Збираємо список ВСІХ монет
        all_symbols = set()
        print("📡 Збираю список всіх монет...")
        
        start = datetime.now()
        while (datetime.now() - start).seconds < 15:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
                data = json.loads(msg)
                
                if 'topic' in data and 'tickers.' in data['topic']:
                    symbol = data.get('data', {}).get('symbol')
                    if symbol:
                        all_symbols.add(symbol)
                        if len(all_symbols) % 100 == 0:
                            print(f"📊 Знайдено {len(all_symbols)} монет...")
            except asyncio.TimeoutError:
                continue
            except:
                continue
        
        symbols_list = list(all_symbols)
        print(f"📋 ✅ Всього знайдено {len(symbols_list)} ф'ючерсних монет")
        
        # Відправляємо тестове повідомлення в Telegram
        await bot.send_message(
            chat_id=CHAT_ID,
            text=f"""🤖 **PUMP/DUMP Бот запущено!**

📊 Моніторинг: <b>{len(symbols_list)}</b> ф'ючерсних монет
⚡ Діапазон: {MIN_PUMP}% - {MAX_PUMP}%
⏱️ Часове вікно: 10 хвилин
🔄 Повторні сигнали: ✅

🔔 Очікую на стрибки цін...""",
            parse_mode='HTML'
        )
        print(f"✅ Тестове повідомлення відправлено")
        
        # Основний цикл обробки цін
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
                            
                            # Перевіряємо діапазон 3% - 50%
                            if MIN_PUMP <= abs_change <= MAX_PUMP:
                                last_time = old_data.get('time', now)
                                time_diff = (now - last_time).total_seconds()
                                
                                # Перевіряємо часове вікно 10 хвилин
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
                print(f"⚠️ Помилка обробки: {e}")

# ============================================
# ЗАПУСК
# ============================================
async def main():
    print("=" * 55)
    print("🤖 PUMP/DUMP МОНІТОРИНГ BYBIT")
    print("📡 Всі ф'ючерсні монети")
    print("=" * 55)
    
    try:
        await monitor()
    except Exception as e:
        print(f"❌ Критична помилка: {e}")
        await bot.send_message(chat_id=CHAT_ID, text=f"❌ Помилка: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
