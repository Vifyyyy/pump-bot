import os
import asyncio
import aiohttp
from datetime import datetime
from telegram import Bot

TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHANNEL_ID")

if not TOKEN or not CHAT_ID:
    print("❌ ПОМИЛКА: Додай BOT_TOKEN та CHANNEL_ID в Railway!")
    exit(1)

bot = Bot(token=TOKEN)

async def test():
    print("✅ Бот запустився!")
    print(f"Token: {TOKEN[:10]}...")
    print(f"Channel ID: {CHAT_ID}")
    
    await bot.send_message(chat_id=CHAT_ID, text="✅ Тестовий запуск! Бот працює!")
    print("✅ Повідомлення відправлено!")

async def main():
    print("=" * 50)
    print("🔧 ТЕСТОВИЙ БОТ")
    print("=" * 50)
    await test()

if __name__ == "__main__":
    asyncio.run(main())
