import asyncio
import aiohttp
import random
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = "7781500138:AAHD7j2Pg-I88HX5h55sdcenVJTdE3lKaww"
fetch_url = "https://api.xalyon.xyz/v2/phone"
send_url = "https://api.xalyon.xyz/v2/refresh/"

MAX_CONCURRENT_REQUESTS = 50
MAX_RETRIES = 3
RETRY_DELAY = [1, 3, 5]

success_count = 0
fail_count = 0
error_log = []
processing = False
current_chat_id = None  # To track which chat to send updates to

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(KeyboardButton("/start_process"), KeyboardButton("/status"))

async def fetch_numbers():
    async with aiohttp.ClientSession() as session:
        async with session.get(fetch_url) as response:
            return await response.json() if response.status == 200 else []

async def send_request(session, phone, semaphore):
    global success_count, fail_count
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(f"{send_url}?phone={phone}") as response:
                    if response.status == 200:
                        success_count += 1
                        return
                    print(f"Error {response.status} for {phone}, retry {attempt+1}/{MAX_RETRIES}")
            except Exception as e:
                print(f"Network error: {e}, retry {attempt+1}/{MAX_RETRIES}")
            await asyncio.sleep(random.choice(RETRY_DELAY))
        fail_count += 1
        error_log.append(phone)

async def process_numbers():
    global processing, success_count, fail_count
    processing = True
    success_count = fail_count = 0
    
    try:
        phones = await fetch_numbers()
        if not phones:
            return "No numbers to process."
        
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        async with aiohttp.ClientSession() as session:
            tasks = [send_request(session, phone, semaphore) for phone in phones]
            await asyncio.gather(*tasks)
        
        return f"✅ Done! Success: {success_count}, ❌ Failed: {fail_count}"
    except Exception as e:
        return f"⚠️ Error: {str(e)}"
    finally:
        processing = False

async def progress_monitor():
    """Send automatic updates every 5 seconds while processing"""
    while processing:
        status = f"🔄 Processing...\n✅ Success: {success_count}\n❌ Failed: {fail_count}"
        await bot.send_message(current_chat_id, status)
        await asyncio.sleep(5)  # Update interval

@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    await message.reply("Welcome! Use /start_process to begin.", reply_markup=keyboard)

@dp.message_handler(commands=['start_process'])
async def start_process(message: types.Message):
    global processing, current_chat_id
    if processing:
        await message.reply("⚙️ Process already running!")
        return
    
    current_chat_id = message.chat.id
    await message.reply("🚀 Starting processing...")
    
    # Start both processing and monitoring tasks
    processing_task = asyncio.create_task(run_processing())
    monitor_task = asyncio.create_task(progress_monitor())
    
    # Wait for processing to complete
    await processing_task
    # Automatically cancel monitoring when done
    monitor_task.cancel()

async def run_processing():
    result = await process_numbers()
    await bot.send_message(current_chat_id, result)

@dp.message_handler(commands=['status'])
async def status_cmd(message: types.Message):
    status = (f"🔄 Processing...\n✅ {success_count} Success\n❌ {fail_count} Failed" 
              if processing else "❇️ No active processes")
    await message.reply(status)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
