import logging
import os
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import yt_dlp
import subprocess

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not found in .env file!")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logger.info("✅ Bot token loaded successfully")

# Проверка FFmpeg
try:
    result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
    logger.info(f"✅ FFmpeg: ffmpeg")
except Exception as e:
    logger.warning(f"⚠️ FFmpeg not found: {e}")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class DownloadStates(StatesGroup):
    waiting_for_url = State()

def get_ydl_opts():
    """Получить опции для yt-dlp с поддержкой YouTube"""
    return {
        "format": "best[ext=mp4]/best",
        "quiet": False,
        "no_warnings": False,
        "socket_timeout": 120,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.youtube.com/",
        },
        "retries": 10,
        "fragment_retries": 10,
        "skip_unavailable_fragments": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["web", "android", "ios"],
                "player_skip": ["js", "configs"],
            },
        },
        "sleep_interval": 5,
        "max_sleep_interval": 30,
    }

async def download_video(url: str, chat_id: int, message_id: int):
    """Скачать видео в отдельном потоке"""
    try:
        logger.info(f"📥 Starting download for {url}")
        
        ydl_opts = get_ydl_opts()
        
        # Создаём директорию для загрузок
        os.makedirs("downloads", exist_ok=True)
        ydl_opts["outtmpl"] = "downloads/%(id)s.%(ext)s"
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Получаем информацию о видео
            logger.info(f"📊 Fetching video info...")
            info = ydl.extract_info(url, download=True)
            video_file = ydl.prepare_filename(info)
            
            logger.info(f"✅ Video downloaded: {video_file}")
            
            # Отправляем видео
            if os.path.exists(video_file):
                file_size = os.path.getsize(video_file)
                logger.info(f"📤 Sending video ({file_size} bytes)...")
                
                with open(video_file, 'rb') as f:
                    await bot.send_video(
                        chat_id=chat_id,
                        video=f,
                        caption=f"✅ Downloaded: {info.get('title', 'Video')}",
                        timeout=300
                    )
                
                # Удаляем локальный файл
                os.remove(video_file)
                logger.info(f"🗑️ Deleted local file: {video_file}")
                
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="✅ Video downloaded and sent!"
                )
            else:
                raise FileNotFoundError(f"Video file not found: {video_file}")
    
    except Exception as e:
        logger.error(f"❌ Error downloading video: {str(e)}")
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"❌ Error: {str(e)[:100]}"
            )
        except:
            pass

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Команда /start"""
    logger.info(f"👤 User {message.from_user.id} started bot")
    await message.answer(
        "🎬 Welcome to Video Downloader!\n\n"
        "Send me a YouTube link and I'll download it for you.\n\n"
        "Example: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    )

@dp.message(F.text.startswith("http"))
async def handle_url(message: types.Message):
    """Обработка URL"""
    url = message.text.strip()
    logger.info(f"🔗 User {message.from_user.id} sent URL: {url}")
    
    status_msg = await message.answer("⏳ Downloading video... This may take a few minutes.")
    
    # Запускаем загрузку в отдельной задаче
    asyncio.create_task(download_video(url, message.chat.id, status_msg.message_id))

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Команда /help"""
    await message.answer(
        "📖 How to use:\n\n"
        "1. Send me a YouTube URL\n"
        "2. Wait for the download\n"
        "3. I'll send you the video\n\n"
        "Supported platforms:\n"
        "• YouTube\n"
        "• Instagram\n"
        "• TikTok\n"
        "• And many more!"
    )

@dp.message()
async def handle_message(message: types.Message):
    """Обработка обычных сообщений"""
    await message.answer(
        "❓ Please send me a valid URL.\n\n"
        "Example: https://www.youtube.com/watch?v=dQw4w9WgXcQ\n\n"
        "Use /help for more info."
    )

async def main():
    """Главная функция"""
    logger.info("🤖 Bot starting...")
    logger.info("✅ Bot is running 24/7!")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
