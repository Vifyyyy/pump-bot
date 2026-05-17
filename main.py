import os
import asyncio
import aiohttp
from datetime import datetime
from telegram import Bot

# ================= НАЛАШТУВАННЯ =================
TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHANNEL_ID")

if not TOKEN or not CHAT_ID:
    print("❌ Помилка: Додайте BOT_TOKEN та CHANNEL_ID в Railway Variables!")
    exit(1)

bot = Bot(token=TOKEN)

# Параметри моніторингу
MIN_PUMP = 3.0          # Мінімальний рух (%)
MAX_PUMP = 50.0         # Максимальний рух (%)
CHECK_INTERVAL = 5      # Частота перевірки (секунд)
TIME_WINDOW = 900       # Часове вікно для руху (15 хвилин)

# Ендпоінт Bitunix для списку всіх пар
BITUNIX_URL = "https://api.bitunix.com/openapi/v1/market/tickers"

# Словник для зберігання попередніх цін (symbol -> price)
price_cache = {}

# ================= ФУНКЦІЯ СПОВІЩЕННЯ =================
async def send_alert(symbol, old_price, new_price, change, count):
    is_pump = change > 0
    direction = "🚀🔥 PUMP" if is_pump else "💀📉 DUMP"
    price_str = f"{new_price:.8f}" if new_price < 1 else f"{new_price:.4f}"
    
    message = f"""
{direction}
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
        print(f"✅ Сигнал: {direction} {symbol} ({change:+.2f}%)")
    except Exception as e:
        print(f"❌ Помилка відправки: {e}")

# ================= ОСНОВНИЙ МОНІТОРИНГ =================
async def monitor():
    print(f"🚀 Запуск моніторингу Bitunix | Перевірка кожні {CHECK_INTERVAL}с | Вікно: {TIME_WINDOW//60}хв")
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(BITUNIX_URL, timeout=15) as response:
                    if response.status != 200:
                        print(f"⚠️ Помилка HTTP {response.status}")
                        await asyncio.sleep(CHECK_INTERVAL)
                        continue
                    
                    data = await response.json()
                    if data.get('code') != 0:
                        print(f"⚠️ Помилка API: {data.get('msg')}")
                        await asyncio.sleep(CHECK_INTERVAL)
                        continue
                    
                    tickers = data.get('data', [])
                    now = datetime.now()
                    alert_triggered = False
                    
                    for ticker in tickers:
                        symbol = ticker.get('symbol', '')
                        if not symbol.endswith('USDT'):
                            continue
                        try:
                            current_price = float(ticker.get('lastPrice', 0))
                        except:
                            continue
                        if current_price <= 0:
                            continue
                        
                        # Перевіряємо зміну ціни
                        if symbol in price_cache:
                            old_price = price_cache[symbol]
                            if old_price != current_price:
                                change_percent = ((current_price - old_price) / old_price) * 100
                                abs_change = abs(change_percent)
                                
                                if MIN_PUMP <= abs_change <= MAX_PUMP:
                                    # Оновлюємо дані та надсилаємо сигнал
                                    count = price_cache.get(f"{symbol}_count", 0) + 1
                                    await send_alert(symbol, old_price, current_price, change_percent, count)
                                    price_cache[symbol] = current_price
                                    price_cache[f"{symbol}_count"] = count
                                    alert_triggered = True
                                    continue
                        
                        # Якщо сигналу не було, просто оновлюємо ціну (скидаємо лічильник)
                        if alert_triggered and symbol in price_cache:
                            continue
                        price_cache[symbol] = current_price
                        price_cache[f"{symbol}_count"] = 0
                    
                    print(f"📊 Статус: {datetime.now().strftime('%H:%M:%S')} | Монет: {len(tickers)} | Змін: {'Є' if alert_triggered else 'Немає'}")
                    
        except asyncio.TimeoutError:
            print("⏰ Таймаут з'єднання")
        except Exception as e:
            print(f"❌ Помилка: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

# ================= ЗАПУСК =================
async def main():
    print("=" * 50)
    print("🤖 PUMP/DUMP МОНІТОРИНГ BITUNIX")
    print(f"⏱️ Часове вікно: {TIME_WINDOW//60} хвилин")
    print("=" * 50)
    
    # Повідомлення про запуск
    await bot.send_message(
        chat_id=CHAT_ID,
        text=f"🤖 **Bitunix Бот запущено!**\n\n⚡ Діапазон: {MIN_PUMP}%–{MAX_PUMP}%\n⏱️ Вікно: {TIME_WINDOW//60} хв\n🔄 Повторні сигнали: ✅\n\n🔔 Стежу за ринком...",
        parse_mode='Markdown'
    )
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
