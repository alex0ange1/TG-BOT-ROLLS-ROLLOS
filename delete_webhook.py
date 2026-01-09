import asyncio
import os
from aiogram import Bot
from dotenv import load_dotenv

load_dotenv()

async def delete_webhook():
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Вебхук удален!")
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(delete_webhook())