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

# ============================================
# ПАРАМЕТРИ МОНІТОРИНГУ
# ============================================
MIN_PUMP = 3.0
MAX_PUMP = 50.0
TIME_WINDOW = 900  # 15 хвилин

# WebSocket MEXC Futures (тільки ф'ючерси)
MEXC_WS_URL = "wss://contract.mexc.com/ws"

# Дані монет
coins_data = {}
all_symbols = set()

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
        print(f"✅ {dir_text} {symbol}: {change:+.2f}% (сигнал #{count})")
    except Exception as e:
        print(f"❌ Помилка: {e}")

# ============================================
# ОСНОВНИЙ МОНІТОРИНГ (WEBSOCKET)
# ============================================
async def monitor():
    print("🔌 Підключення до WebSocket MEXC Futures...")
    
    while True:
        try:
            async with websockets.connect(MEXC_WS_URL, ping_interval=20) as ws:
                print("✅ Підключено до MEXC WebSocket")
                
                # Підписуємось на канал sub.tickers (всі ф'ючерси)
                subscribe_msg = {
                    "method": "SUBSCRIPTION",
                    "params": ["sub.tickers"]
                }
                await ws.send(json.dumps(subscribe_msg))
                print("📡 Підписано на канал sub.tickers (ВСІ ф'ючерси)")
                
                # Відправляємо повідомлення про запуск
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text="""🤖 **PUMP/DUMP Бот (MEXC Futures) запущено!**

📡 **Режим:** WebSocket (реальний час)
⚡ **Діапазон:** 3% - 50%
⏱️ **Часове вікно:** 15 хвилин
🔄 **Повторні сигнали:** ✅

🔔 Очікую на стрибки цін...""",
                    parse_mode='Markdown'
                )
                print("✅ Повідомлення про запуск відправлено")
                
                # Основний цикл отримання повідомлень
                async for message in ws:
                    try:
                        data = json.loads(message)
                        
                        # Перевіряємо формат повідомлення MEXC
                        if 'd' in data and 'ticker' in data['d']:
                            ticker_data = data['d']['ticker']
                            symbol = ticker_data.get('symbol', '')
                            
                            # MEXC повертає символи з підкресленням, наприклад BTC_USDT
                            symbol = symbol.replace('_', '')
                            
                            if not symbol.endswith('USDT'):
                                continue
                            
                            # Додаємо символ до списку
                            if symbol not in all_symbols:
                                all_symbols.add(symbol)
                                if len(all_symbols) % 50 == 0:
                                    print(f"📊 Зібрано {len(all_symbols)} ф'ючерсів")
                            
                            try:
                                price = float(ticker_data.get('lastPrice', 0))
                            except (ValueError, TypeError):
                                continue
                            
                            if price <= 0:
                                continue
                            
                            now = datetime.now()
                            old = coins_data.get(symbol)
                            
                            if old and old.get('price'):
                                old_price = old['price']
                                if old_price != price:
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
                                
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        print(f"⚠️ Помилка обробки: {e}")
                        
        except websockets.exceptions.ConnectionClosed:
            print("⚠️ З'єднання втрачено, перепідключення через 5 секунд...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"❌ Помилка WebSocket: {e}")
            await asyncio.sleep(5)

# ============================================
# ЗАПУСК
# ============================================
async def main():
    print("=" * 55)
    print("🤖 PUMP/DUMP МОНІТОРИНГ MEXC FUTURES")
    print("📡 WebSocket (тільки ф'ючерси)")
    print(f"⏱️ Часове вікно: {TIME_WINDOW//60} хвилин")
    print("=" * 55)
    
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
