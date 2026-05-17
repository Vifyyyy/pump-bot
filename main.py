import os
import asyncio
import json
import websockets
from datetime import datetime
from telegram import Bot

TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHANNEL_ID")

if not TOKEN or not CHAT_ID:
    print("❌ ПОМИЛКА: Додай BOT_TOKEN та CHANNEL_ID в Railway!")
    exit(1)

bot = Bot(token=TOKEN)

MIN_PUMP = 3.0
MAX_PUMP = 50.0
TIME_WINDOW = 900

MEXC_WS_URL = "wss://contract.mexc.com/ws"

coins_data = {}
all_symbols = set()

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

async def monitor():
    print("🔌 Підключення до WebSocket MEXC Futures...")
    
    while True:
        try:
            async with websockets.connect(MEXC_WS_URL, ping_interval=20) as ws:
                print("✅ Підключено до MEXC WebSocket")
                
                subscribe_msg = {
                    "method": "SUBSCRIPTION",
                    "params": ["sub.tickers"]
                }
                await ws.send(json.dumps(subscribe_msg))
                print("📡 Підписано на sub.tickers")
                
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text="🤖 **Бот MEXC Futures запущено!**\n\n⚡ 3%-50% | 15 хвилин\n🔔 Очікую стрибки...",
                    parse_mode='Markdown'
                )
                
                async for message in ws:
                    try:
                        data = json.loads(message)
                        
                        if 'd' in data and 'ticker' in data['d']:
                            ticker = data['d']['ticker']
                            symbol = ticker.get('symbol', '').replace('_', '')
                            
                            if not symbol.endswith('USDT'):
                                continue
                            
                            all_symbols.add(symbol)
                            
                            try:
                                price = float(ticker.get('lastPrice', 0))
                            except:
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
                                        if (now - last_time).total_seconds() <= TIME_WINDOW:
                                            count = old.get('count', 0) + 1
                                            await send_alert(symbol, old_price, price, change, count)
                                            coins_data[symbol] = {'price': price, 'time': now, 'count': count}
                                        else:
                                            coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                    else:
                                        coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                            else:
                                coins_data[symbol] = {'price': price, 'time': now, 'count': 0}
                                
                    except Exception as e:
                        print(f"⚠️ Помилка: {e}")
                        
        except Exception as e:
            print(f"❌ Помилка: {e}")
            await asyncio.sleep(5)

async def main():
    print("=" * 50)
    print("🤖 PUMP/DUMP MEXC FUTURES")
    print("=" * 50)
    await monitor()

if __name__ == "__main__":
    asyncio.run(main())
