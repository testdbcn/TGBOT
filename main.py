import asyncio
import aiohttp
import random
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Telegram Bot Token
BOT_TOKEN = "7781500138:AAHD7j2Pg-I88HX5h55sdcenVJTdE3lKaww"

# API URLs
fetch_url = "https://api.xalyon.xyz/v2/phone"
send_url = "https://api.xalyon.xyz/v2/refresh/"

# Concurrency & Retry Settings
MAX_CONCURRENT_REQUESTS = 50
MAX_RETRIES = 3
RETRY_DELAY = [1, 3, 5]

# Global Counters & Task Tracking
success_count = 0
fail_count = 0
error_log = []
processing = False

# Bot Initialization
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Start Keyboard
keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(KeyboardButton("/start_process"), KeyboardButton("/status"))

async def fetch_numbers():
    """Fetch phone numbers from API."""
    async with aiohttp.ClientSession() as session:
        async with session.get(fetch_url) as response:
            if response.status == 200:
                return await response.json()
            return []

async def send_request(session, phone, semaphore):
    """Send request with retries."""
    global success_count, fail_count
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(f"{send_url}?phone={phone}") as response:
                    if response.status == 200:
                        success_count += 1
                        return
                    else:
                        print(f"Error {response.status} for {phone}, retrying ({attempt+1}/{MAX_RETRIES})")
            except Exception as e:
                print(f"Network error: {e}, retrying ({attempt+1}/{MAX_RETRIES})")
            await asyncio.sleep(random.choice(RETRY_DELAY))
        fail_count += 1
        error_log.append(phone)

async def process_numbers():
    """Process numbers asynchronously."""
    global processing, success_count, fail_count
    processing = True
    success_count, fail_count = 0, 0

    try:
        phone_numbers = await fetch_numbers()
        if not phone_numbers:
            return "No numbers to process."

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        async with aiohttp.ClientSession() as session:
            tasks = [send_request(session, phone, semaphore) for phone in phone_numbers]
            await asyncio.gather(*tasks)
        return f"✅ Done! Success: {success_count}, ❌ Failed: {fail_count}"
    except Exception as e:
        return f"⚠️ Error: {str(e)}"
    finally:
        processing = False

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    await message.reply("Welcome! Use /start_process to begin or /status to check progress.", reply_markup=keyboard)

@dp.message_handler(commands=['start_process'])
async def start_process(message: types.Message):
    global processing
    if processing:
        await message.reply("⚙️ Already running...")
    else:
        await message.reply("🚀 Starting process...")
        asyncio.create_task(run_process(message.chat.id))

async def run_process(chat_id):
    result = await process_numbers()
    await bot.send_message(chat_id, result)

@dp.message_handler(commands=['status'])
async def status_command(message: types.Message):
    status_msg = (f"🔄 Processing...\n✅ Success: {success_count}\n❌ Failed: {fail_count}"
                  if processing else
                  f"✅ Done!\nSuccess: {success_count}\nFailed: {fail_count}")
    await message.reply(status_msg)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
