import os
import asyncio
import aiohttp
import matplotlib.pyplot as plt
import io
from datetime import datetime, timedelta
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
CHECK_INTERVAL = 5           # Перевіряти кожні 5 секунд
TIMEFRAME = "15"             # 15-хвилинний таймфрейм (в хвилинах)

# Bitunix API
BITUNIX_TICKERS_URL = "https://api.bitunix.com/api/v1/market/tickers"
BITUNIX_KLINE_URL = "https://api.bitunix.com/api/v1/market/kline"

last_prices = {}
check_count = 0

# ============================================
# ФУНКЦІЯ МАЛЮВАННЯ ГРАФІКА
# ============================================
async def generate_price_chart(symbol: str, is_pump: bool) -> io.BytesIO:
    """Генерує 15-хвилинний графік ціни"""
    try:
        # Отримуємо дані kline з Bitunix
        params = {
            "symbol": symbol,
            "interval": TIMEFRAME,
            "limit": 30  # Останні 30 свічок (7.5 годин)
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(BITUNIX_KLINE_URL, params=params) as response:
                if response.status != 200:
                    print(f"⚠️ Не вдалося отримати графік для {symbol}")
                    return None
                
                data = await response.json()
                klines = data.get('data', [])
                
                if not klines:
                    return None
                
                # Розпарсимо дані: час закриття, ціна закриття
                times = []
                prices = []
                
                for kline in klines[-30:]:
                    # Формат: [час_відкриття, відкриття, максимум, мінімум, закриття, об'єм, час_закриття]
                    close_time = datetime.fromtimestamp(kline[6] / 1000)
                    close_price = float(kline[4])
                    times.append(close_time)
                    prices.append(close_price)
                
                if len(prices) < 5:
                    return None
                
                # Створюємо графік
                plt.style.use('dark_background')
                fig, ax = plt.subplots(figsize=(10, 6))
                
                # Колір: зелений для PUMP, червоний для DUMP
                color = '#00ff88' if is_pump else '#ff4444'
                
                # Малюємо лінію
                ax.plot(times, prices, color=color, linewidth=2, marker='o', markersize=4)
                
                # Заповнюємо область під графіком
                ax.fill_between(times, prices, min(prices), alpha=0.3, color=color)
                
                # Налаштування
                ax.set_title(f"{symbol} - 15-хвилинний графік", color='white', fontsize=14, fontweight='bold')
                ax.set_xlabel("Час", color='white')
                ax.set_ylabel("Ціна (USDT)", color='white')
                ax.tick_params(colors='white')
                ax.grid(True, alpha=0.3, color='gray')
                
                # Поворот міток часу
                plt.xticks(rotation=45)
                plt.tight_layout()
                
                # Зберігаємо в буфер
                buf = io.BytesIO()
                plt.savefig(buf, format='png', facecolor='#1a1a2e')
                buf.seek(0)
                plt.close()
                
                return buf
                
    except Exception as e:
        print(f"❌ Помилка генерації графіка для {symbol}: {e}")
        return None

# ============================================
# ФУНКЦІЯ НАДСИЛАННЯ СПОВІЩЕННЯ З ГРАФІКОМ
# ============================================
async def send_alert(symbol: str, old_price: float, new_price: float, change_percent: float):
    """Надсилає сповіщення з графіком в Telegram"""
    is_pump = change_percent > 0
    direction = "🚀🔥 PUMP" if is_pump else "💀📉 DUMP"
    emoji = "📈" if is_pump else "📉"
    
    # Текст сповіщення
    message = f"""
<b>{direction}</b>
━━━━━━━━━━━━━━━━━━━━━
🪙 Монета: <code>{symbol}</code>
{emoji} Зміна: <b>{change_percent:+.2f}%</b>
💰 Ціна: <b>{new_price:,.4f}</b> USDT
📊 Час: {datetime.now().strftime('%H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━━
"""
    
    # Генеруємо графік
    chart = await generate_price_chart(symbol, is_pump)
    
    try:
        if chart:
            # Надсилаємо графік з підписом
            await bot.send_photo(
                chat_id=CHAT_ID,
                photo=chart,
                caption=message,
                parse_mode='HTML'
            )
            print(f"✅ [СПОВІЩЕННЯ] {direction} {symbol}: {change_percent:+.2f}% (з графіком)")
        else:
            # Якщо графік не згенерувався — надсилаємо тільки текст
            await bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode='HTML'
            )
            print(f"✅ [СПОВІЩЕННЯ] {direction} {symbol}: {change_percent:+.2f}% (без графіка)")
    except Exception as e:
        print(f"❌ Помилка відправки: {e}")

# ============================================
# ГОЛОВНА ФУНКЦІЯ МОНІТОРИНГУ
# ============================================
async def monitor_bitunix():
    global check_count
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(BITUNIX_TICKERS_URL, timeout=10) as response:
                    
                    if response.status != 200:
                        await asyncio.sleep(CHECK_INTERVAL)
                        continue
                    
                    data = await response.json()
                    tickers = data.get('data', [])
                    
                    if not tickers:
                        await asyncio.sleep(CHECK_INTERVAL)
                        continue
                    
                    for ticker in tickers:
                        symbol = ticker.get('symbol', '')
                        try:
                            last_price = float(ticker.get('lastPrice', 0))
                        except (ValueError, TypeError):
                            continue
                        
                        if not symbol or last_price <= 0:
                            continue
                        
                        if symbol in last_prices:
                            old_price = last_prices[symbol]
                            if old_price > 0:
                                percent_change = ((last_price - old_price) / old_price) * 100
                                
                                if abs(percent_change) >= THRESHOLD_PERCENT:
                                    await send_alert(symbol, old_price, last_price, percent_change)
                        
                        last_prices[symbol] = last_price
                    
                    check_count += 1
                    if check_count % 20 == 0:
                        print(f"📊 [СТАТУС] Перевірено {len(tickers)} пар | {datetime.now().strftime('%H:%M:%S')}")
                    
        except asyncio.TimeoutError:
            print("⏰ Таймаут...")
        except Exception as e:
            print(f"❌ Помилка: {e}")
        
        await asyncio.sleep(CHECK_INTERVAL)

# ============================================
# ЗАПУСК БОТА
# ============================================
async def main():
    print("=" * 50)
    print("🤖 PUMP/DUMP МОНІТОРИНГ BITUNIX")
    print("📊 З 15-ХВИЛИННИМИ ГРАФІКАМИ")
    print("=" * 50)
    print(f"✅ Telegram бот: підключено")
    print(f"⚙️ Поріг: {THRESHOLD_PERCENT}%")
    print(f"📈 Таймфрейм графіка: 15 хвилин")
    print("=" * 50)
    
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text="🤖 **PUMP/DUMP Бот запущено!**\n\n📊 Моніторинг Bitunix\n📈 15-хвилинні графіки\n⚡ Поріг: 3%",
            parse_mode='Markdown'
        )
        print("✅ Тестове повідомлення відправлено!")
    except Exception as e:
        print(f"❌ Помилка: {e}")
        return
    
    print("🎯 Починаю моніторинг...")
    await monitor_bitunix()

if __name__ == "__main__":
    asyncio.run(main())
