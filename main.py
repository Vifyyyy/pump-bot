import os
import asyncio
from telegram import Bot

TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHANNEL_ID")

print("=" * 50)
print("🚀 ТЕСТОВИЙ БОТ")
print(f"BOT_TOKEN: {'✅ Є' if TOKEN else '❌ НІ'}")
print(f"CHANNEL_ID: {'✅ Є' if CHAT_ID else '❌ НІ'}")
print("=" * 50)

async def main():
    if not TOKEN or not CHAT_ID:
        print("❌ ПОМИЛКА: Змінні відсутні!")
        return
    
    try:
        bot = Bot(token=TOKEN)
        await bot.send_message(chat_id=CHAT_ID, text="✅ Тестове повідомлення! Бот працює!")
        print("✅ Повідомлення відправлено!")
    except Exception as e:
        print(f"❌ ПОМИЛКА: {e}")

if __name__ == "__main__":
    asyncio.run(main())
