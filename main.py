import os
import asyncio
import json
import websockets
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

MIN_PUMP = 3.0
MAX_PUMP = 50.0
TIME_WINDOW = 600  # 10 хвилин

# Дані монет
coins = {}

# ============================================
# 1. ОТРИМАННЯ ВСІХ Ф'ЮЧЕРСНИХ МОНЕТ (ЧЕРЕЗ REST API)
# ============================================
async def get_all_linear_symbols():
    """
    Отримує ВСІ USDT Perpetual ф'ючерсні монети з Bybit.
    Використовує офіційний ендпоінт /v5/market/instruments-info.
    """
    url = "https://api.bybit.com/v5/market/instruments-info?category=linear"
    
    # Додаємо заголовки, щоб імітувати браузер
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Referer': 'https://www.bybit.com/',
    }

    print("📡 Завантаження списку всіх ф'ючерсних монет з Bybit...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('retCode') == 0:
                        # Отримуємо список символів
                        symbols = [item['symbol'] for item in data['result']['list']]
                        print(f"📋 ✅ Успішно знайдено {len(symbols)} ф'ючерсних монет.")
                        return symbols
                    else:
                        print(f"⚠️ Помилка API: {data.get('retMsg')}")
                else:
                    print(f"❌ HTTP помилка: {response.status}")
    except asyncio.TimeoutError:
        print("❌ Таймаут підключення до Bybit API")
    except aiohttp.ClientConnectorError as e:
        print(f"❌ Помилка з'єднання: {e}")
    except Exception as e:
        print(f"❌ Невідома помилка: {e}")

    print("❌ НЕ ВДАЛОСЯ ОТРИМАТИ СПИСОК МОНЕТ. БОТ НЕ МОЖЕ ПРАЦЮВАТИ.")
    return None

# ============================================
# 2. ВІДПРАВКА СПОВІЩЕННЯ
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
        print(f"❌ Помилка відправки: {e}")

# ============================================
# 3. ПІДКЛЮЧЕННЯ ДО WEBSOCKET ТА МОНІТОРИНГ
# ============================================
async def monitor_symbols(symbols):
    """Підключається до WebSocket та стежить за цінами всіх монет."""
    ws_url = "wss://stream.bybit.com/v5/public/linear"
    
    while True:
        try:
            async with websockets.connect(ws_url, ping_interval=20) as ws:
                print("🔌 Підключено до Bybit WebSocket")
                
                # Підписуємось на всі монети (розбиваємо на частини, щоб не перевантажити)
                batch_size = 50
                for i in range(0, len(symbols), batch_size):
                    batch = symbols[i:i+batch_size]
                    subscribe_msg = {
                        "op": "subscribe",
                        "args": [f"tickers.{s}" for s in batch]
                    }
                    await ws.send(json.dumps(subscribe_msg))
                    print(f"📡 Підписано на {len(batch)} монет...")
                    await asyncio.sleep(0.1)
                
                print(f"✅ Підписку завершено на {len(symbols)} каналів")
                
                # Основний цикл обробки повідомлень
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
                                    
                                    if MIN_PUMP <= abs_change <= MAX_PUMP:
                                        last_time = old_data.get('time', now)
                                        time_diff = (now - last_time).total_seconds()
                                        
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
                                
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        print(f"⚠️ Помилка обробки: {e}")
                        
        except Exception as e:
            print(f"❌ WebSocket помилка: {e}")
            await asyncio.sleep(5)

# ============================================
# 4. ЗАПУСК БОТА
# ============================================
async def main():
    print("=" * 55)
    print("🤖 PUMP/DUMP МОНІТОРИНГ BYBIT (ВСІ МОНЕТИ)")
    print("=" * 55)
    
    # 1. Отримуємо всі монети
    all_symbols = await get_all_linear_symbols()
    if not all_symbols:
        await bot.send_message(chat_id=CHAT_ID, text="❌ Не вдалося завантажити список монет! Бот зупинено.")
        return
    
    print(f"✅ Успішно завантажено {len(all_symbols)} монет.")
    
    # 2. Відправляємо тестове повідомлення в Telegram
    await bot.send_message(
        chat_id=CHAT_ID,
        text=f"""🤖 **PUMP/DUMP Бот запущено!**

📊 Моніторинг: <b>{len(all_symbols)}</b> ф'ючерсних монет
⚡ Діапазон: {MIN_PUMP}% - {MAX_PUMP}%
⏱️ Часове вікно: 10 хвилин
🔄 Повторні сигнали: ✅

🔔 Очікую на стрибки цін...""",
        parse_mode='HTML'
    )
    
    # 3. Запускаємо моніторинг
    await monitor_symbols(all_symbols)

if __name__ == "__main__":
    asyncio.run(main())
