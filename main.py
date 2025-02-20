import asyncio
import aiohttp
import random
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = "YOUR_BOT_TOKEN"
fetch_url = "https://api.xalyon.xyz/v2/phone"
send_url = "https://api.xalyon.xyz/v2/refresh/"

MAX_CONCURRENT_REQUESTS = 5  # Reduced for testing
MAX_RETRIES = 2
RETRY_DELAY = [1, 2]

# Thread-safe counters
class Counter:
    def __init__(self):
        self.value = 0
        self._lock = asyncio.Lock()

    async def increment(self):
        async with self._lock:
            self.value += 1

success_counter = Counter()
fail_counter = Counter()
error_log = []
processing = False
current_chat_id = None

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(KeyboardButton("/start_process"), KeyboardButton("/status"))

async def fetch_numbers():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(fetch_url) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"Fetched {len(data)} numbers")
                    return data
                print(f"Fetch failed: HTTP {response.status}")
                return []
    except Exception as e:
        print(f"Fetch error: {str(e)}")
        return []

async def send_request(session, phone, semaphore):
    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(
                    f"{send_url}?phone={phone}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        await success_counter.increment()
                        print(f"Success: {phone}")
                        return True
                    print(f"Attempt {attempt+1} failed for {phone}: HTTP {response.status}")
            except Exception as e:
                print(f"Attempt {attempt+1} error for {phone}: {str(e)}")
            
            await asyncio.sleep(random.choice(RETRY_DELAY))
        
        await fail_counter.increment()
        error_log.append(phone)
        print(f"Permanent failure: {phone}")
        return False

async def process_numbers():
    global processing
    processing = True
    await success_counter.increment(0)  # Reset counter
    await fail_counter.increment(0)     # Reset counter
    
    try:
        phones = await fetch_numbers()
        if not phones:
            return "⚠️ No numbers to process"
        
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        async with aiohttp.ClientSession() as session:
            tasks = [send_request(session, phone, semaphore) for phone in phones]
            results = await asyncio.gather(*tasks)
        
        success_rate = sum(results) / len(results)
        return (f"✅ Processing complete!\n"
                f"Success: {success_counter.value}\n"
                f"Failed: {fail_counter.value}\n"
                f"Success rate: {success_rate:.1%}")
    except Exception as e:
        return f"⚠️ Processing error: {str(e)}"
    finally:
        processing = False

async def progress_monitor():
    while processing:
        status = (f"🔄 Processing...\n"
                 f"✅ Success: {success_counter.value}\n"
                 f"❌ Failed: {fail_counter.value}")
        await bot.send_message(current_chat_id, status)
        await asyncio.sleep(5)

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
    
    processing_task = asyncio.create_task(run_processing())
    monitor_task = asyncio.create_task(progress_monitor())
    
    try:
        await processing_task
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

async def run_processing():
    result = await process_numbers()
    await bot.send_message(current_chat_id, result)

@dp.message_handler(commands=['status'])
async def status_cmd(message: types.Message):
    status = (f"🔄 Processing...\n✅ {success_counter.value} Success\n❌ {fail_counter.value} Failed" 
              if processing else "❇️ No active processes")
    await message.reply(status)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
