import os
import asyncio
import json
import websockets
from datetime import datetime
from telegram import Bot

# ============================================
# НАЛАШТУВАННЯ - БЕРУТЬСЯ З RAILWAY
# ============================================
TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHANNEL_ID")

if not TOKEN or not CHAT_ID:
    print("❌ ПОМИЛКА: Додай BOT_TOKEN та CHANNEL_ID в Railway!")
    exit(1)

bot = Bot(token=TOKEN)

# ============================================
# НАЛАШТУВАННЯ БОТА
# ============================================
THRESHOLD_PERCENT = 3.0      # Сповіщати при зміні на 3%

# Bybit WebSocket адреса для публічних даних (USDT Perpetual)
BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/linear"

# Зберігаємо останню ціну для кожної монети
last_prices = {}
# Лічильник для логів
check_count = 0

# ============================================
# ФУНКЦІЯ НАДСИЛАННЯ СПОВІЩЕННЯ
# ============================================
async def send_alert(symbol: str, old_price: float, new_price: float, change_percent: float):
    """Надсилає сповіщення про PUMP або DUMP в Telegram"""
    is_pump = change_percent > 0
    direction = "🚀🔥 PUMP" if is_pump else "💀📉 DUMP"
    emoji = "📈" if is_pump else "📉"
    
    message = f"""
{direction}
━━━━━━━━━━━━━━━━━━━━━
🪙 Монета: <code>{symbol}</code>
{emoji} Зміна: <b>{change_percent:+.2f}%</b>
💰 Ціна: <b>{new_price:,.4f}</b> USDT
📊 Час: {datetime.now().strftime('%H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━━
"""
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='HTML')
        print(f"✅ [СПОВІЩЕННЯ] {direction} {symbol}: {change_percent:+.2f}%")
    except Exception as e:
        print(f"❌ Помилка відправки: {e}")

# ============================================
# ОБРОБКА TICKER-ПОВІДОМЛЕНЬ ВІД BYBIT
# ============================================
async def handle_ticker(data: dict):
    """Обробляє ticker-дані від Bybit WebSocket"""
    global check_count
    
    try:
        # Парсимо дані Bybit
        # Формат: {"topic": "tickers.BTCUSDT", "data": {...}}
        if 'data' not in data:
            return
        
        ticker = data['data']
        symbol = ticker.get('symbol', '')
        last_price = float(ticker.get('lastPrice', 0))
        
        if not symbol or last_price <= 0:
            return
        
        # Перевіряємо зміну ціни
        if symbol in last_prices:
            old_price = last_prices[symbol]
            if old_price > 0:
                percent_change = ((last_price - old_price) / old_price) * 100
                
                if abs(percent_change) >= THRESHOLD_PERCENT:
                    await send_alert(symbol, old_price, last_price, percent_change)
        
        # Оновлюємо збережену ціну
        last_prices[symbol] = last_price
        
        # Рідко виводимо статус
        check_count += 1
        if check_count % 100 == 0:
            print(f"📊 [СТАТУС] Відстежується {len(last_prices)} монет | {datetime.now().strftime('%H:%M:%S')}")
            
    except Exception as e:
        print(f"❌ Помилка обробки ticker: {e}")

# ============================================
# ПІДКЛЮЧЕННЯ ДО WEBSOCKET BYBIT
# ============================================
async def listen_bybit():
    """Підключається до Bybit WebSocket і слухає ticker-канали"""
    
    while True:
        try:
            async with websockets.connect(BYBIT_WS_URL, ping_interval=20) as websocket:
                print("🔌 Підключено до Bybit WebSocket")
                
                # Підписуємось на ticker-канали ВСІХ USDT Perpetual ф'ючерсів
                subscribe_msg = {
                    "op": "subscribe",
                    "args": ["tickers.*"]  # * означає всі символи
                }
                await websocket.send(json.dumps(subscribe_msg))
                print("📡 Підписано на ticker-канали всіх монет")
                
                # Слухаємо повідомлення
                async for message in websocket:
                    data = json.loads(message)
                    
                    # Перевіряємо тип повідомлення
                    if 'topic' in data and data['topic'].startswith('tickers.'):
                        await handle_ticker(data)
                    elif 'op' in data and data['op'] == 'pong':
                        pass  # Heartbeat, ігноруємо
                    elif 'success' in data:
                        print(f"✅ Підписка підтверджена: {data}")
                        
        except websockets.exceptions.ConnectionClosed:
            print("⚠️ З'єднання втрачено, перепідключення через 5 секунд...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"❌ Помилка WebSocket: {e}")
            await asyncio.sleep(5)

# ============================================
# ЗАПУСК БОТА
# ============================================
async def main():
    print("=" * 50)
    print("🤖 PUMP/DUMP МОНІТОРИНГ BYBIT")
    print("📊 USDT Perpetual Futures (ВСІ ПАРИ)")
    print("=" * 50)
    print(f"✅ Telegram бот: підключено")
    print(f"⚙️ Поріг спрацювання: {THRESHOLD_PERCENT}%")
    print(f"🔗 WebSocket: {BYBIT_WS_URL}")
    print("=" * 50)
    
    # Відправляємо тестове повідомлення
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=f"""🤖 **PUMP/DUMP Бот для Bybit запущено!**

📊 **Налаштування:**
• Біржа: Bybit (USDT Perpetual)
• Поріг спрацювання: {THRESHOLD_PERCENT}%
• Моніторинг: ВСІ ф'ючерсні пари
• З'єднання: WebSocket (реальний час)

🔔 Очікую на стрибки цін...""",
            parse_mode='Markdown'
        )
        print("✅ Тестове повідомлення відправлено в Telegram!")
    except Exception as e:
        print(f"❌ Помилка відправки тестового: {e}")
        return
    
    print("🎯 Починаю моніторинг Bybit через WebSocket...")
    print("💡 Коли буде PUMP або DUMP на 3% - отримаєш сповіщення")
    print("=" * 50)
    
    # Запускаємо WebSocket моніторинг
    await listen_bybit()

# ============================================
# ТОЧКА ВХОДУ
# ============================================
if __name__ == "__main__":
    asyncio.run(main())
