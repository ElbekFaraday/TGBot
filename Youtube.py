# -*- coding: utf-8 -*-
import asyncio
import os
import uuid
import tempfile
import subprocess
import platform
import glob
import re
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import CommandStart, Command
import yt_dlp
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get token from environment
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logger.error("❌ BOT_TOKEN not found in environment variables!")
    exit(1)

logger.info("✅ Bot token loaded successfully")

bot = Bot(token=TOKEN)
dp = Dispatcher()

video_data = {}
TEMP_DIR = tempfile.gettempdir()

# Supported sources
SUPPORTED_SOURCES = [
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "tiktok.com",
    "vt.tiktok.com",
    "vm.tiktok.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "vimeo.com",
    "dailymotion.com",
    "soundcloud.com",
    "spotify.com",
    "snapchat.com",
    "snap.com"
]

# Set FFmpeg path
FFMPEG_LOCATION = "ffmpeg"
logger.info(f"✅ FFmpeg: {FFMPEG_LOCATION}")


def get_ydl_opts(is_audio=False, format_id=None):
    """Get yt-dlp options with YouTube authentication fixes"""
    ydl_opts = {
        "quiet": False,
        "no_warnings": True,
        "socket_timeout": 60,
        "ffmpeg_location": FFMPEG_LOCATION,
        
        "extractor_args": {
            "youtube": {
                "player_client": ["web", "android", "ios"],
                "player_skip": ["js", "configs"],
            },
            "instagram": {
                "android_api": True,
            },
            "snapchat": {
                "api": True,
            }
        },
        
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.youtube.com/",
        },
        
        "sleep_interval": 3,
        "max_sleep_interval": 10,
        "retries": 5,
        "skip_unavailable_fragments": True,
    }
    
    return ydl_opts


def get_formats(url):
    """Extract video info and available formats from URL"""
    ydl_opts = get_ydl_opts()

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise Exception(f"Failed to extract video info: {str(e)}")

    formats_list = []

    print(f"\n=== DEBUG: Total formats available: {len(info.get('formats', []))} ===")

    is_youtube = "youtube" in url or "youtu.be" in url

    video_formats = {}
    audio_formats = []

    print("\nAll formats:")
    for idx, f in enumerate(info.get("formats", [])[:15]):
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        height = f.get("height")
        print(
            f"  [{idx}] id={f.get('format_id')}, vcodec={vcodec}, acodec={acodec}, height={height}, fps={f.get('fps')}")

    for f in info.get("formats", []):
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        height = f.get("height")
        format_id = f.get("format_id")

        if vcodec != "none" and acodec == "none" and height and height > 0:
            if height not in video_formats:
                video_formats[height] = format_id
                print(f"\n✓ Video format found: {height}p (id: {format_id})")

        if acodec != "none" and vcodec == "none":
            audio_formats.append(format_id)

    print(f"\nVideo formats found: {len(video_formats)} unique heights")
    print(f"Audio formats found: {len(audio_formats)}")

    if is_youtube and audio_formats and video_formats:
        best_audio = audio_formats[0]
        print(f"\n🎵 Best audio format: {best_audio}")
        print(f"\nCombining video+audio formats:")
        for height in sorted(video_formats.keys(), reverse=True):
            video_id = video_formats[height]
            combined_format = f"{video_id}+{best_audio}"
            formats_list.append({
                "format_id": combined_format,
                "quality": int(height),
                "ext": "mp4",
                "filesize": 0,
                "type": "combined_av"
            })
            print(f"  ✓ {height}p: {combined_format}")

    if not formats_list and video_formats:
        print(f"\n⚠️ Using video-only formats (no audio):")
        for height in sorted(video_formats.keys(), reverse=True):
            formats_list.append({
                "format_id": video_formats[height],
                "quality": int(height),
                "ext": "mp4",
                "filesize": 0,
                "type": "video_only"
            })
            print(f"  - {height}p")

    if not formats_list:
        print(f"\n⚠️ Fallback: looking for combined or best formats")
        for f in info.get("formats", []):
            vcodec = f.get("vcodec", "none")
            acodec = f.get("acodec", "none")
            height = f.get("height")
            format_id = f.get("format_id")

            if vcodec != "none" and acodec != "none" and height and height > 0:
                formats_list.append({
                    "format_id": format_id,
                    "quality": int(height),
                    "ext": f.get("ext", "mp4"),
                    "filesize": 0,
                    "type": "combined"
                })
                print(f"  - {height}p combined (id: {format_id})")

    if not formats_list:
        print(f"\n🔴 Using last resort: best format")
        formats_list.append({
            "format_id": "best",
            "quality": 720,
            "ext": "mp4",
            "filesize": 0,
            "type": "best"
        })

    unique_qualities = {}
    for f in sorted(formats_list, key=lambda x: x["quality"], reverse=True):
        quality = f["quality"]
        if quality not in unique_qualities:
            unique_qualities[quality] = f

    unique_formats = sorted(unique_qualities.values(), key=lambda x: x["quality"], reverse=True)

    print(f"\n📊 Final unique formats: {len(unique_formats)}")
    for uf in unique_formats:
        print(f"  - {uf['quality']}p (id: {uf['format_id']}, type: {uf['type']})")
    print(f"=== END DEBUG ===\n")

    return info, unique_formats


def format_file_size(size_bytes):
    """Convert bytes to human readable format"""
    try:
        size_bytes = int(size_bytes)
    except (ValueError, TypeError):
        return "Unknown"

    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def find_downloaded_file(directory, base_name):
    """Find the downloaded file by searching for files with base name"""
    if not os.path.exists(directory):
        return None

    pattern = os.path.join(directory, f"{base_name}*")
    files = glob.glob(pattern)

    if files:
        return max(files, key=os.path.getctime)

    return None


def download_video(url, format_id, output_dir, base_name, is_audio=False):
    """Download video or audio"""
    os.makedirs(output_dir, exist_ok=True)

    ydl_opts = get_ydl_opts(is_audio=is_audio, format_id=format_id)
    ydl_opts["outtmpl"] = os.path.join(output_dir, base_name)

    if is_audio:
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        ydl_opts["format"] = format_id

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        print(f"Download error: {e}")
        raise

    downloaded_file = find_downloaded_file(output_dir, base_name)

    if not downloaded_file:
        print(f"Contents of {output_dir}: {os.listdir(output_dir)}")
        raise FileNotFoundError(f"Could not find downloaded file with base name: {base_name}")

    print(f"Downloaded file found: {downloaded_file}")
    return downloaded_file


def is_supported_source(url):
    """Check if URL is from supported source"""
    return any(source in url for source in SUPPORTED_SOURCES)


def get_source_name(url):
    """Get source name from URL"""
    if "youtube.com" in url or "youtu.be" in url:
        return "YouTube"
    elif "instagram.com" in url:
        return "Instagram"
    elif "tiktok" in url:
        return "TikTok"
    elif "facebook.com" in url:
        return "Facebook"
    elif "twitter.com" in url or "x.com" in url:
        return "Twitter/X"
    elif "vimeo.com" in url:
        return "Vimeo"
    elif "dailymotion.com" in url:
        return "Dailymotion"
    elif "soundcloud.com" in url:
        return "SoundCloud"
    elif "spotify.com" in url:
        return "Spotify"
    elif "snapchat.com" in url or "snap.com" in url:
        return "Snapchat"
    return "Unknown Source"


@dp.my_chat_member()
async def on_bot_added_to_group(update: types.ChatMemberUpdated):
    """Handle when bot is added to a group"""
    if update.new_chat_member.status == "member":
        chat = update.chat

        if chat.type in ["group", "supergroup"]:
            logger.info(f"✓ Bot added to group: {chat.title} (ID: {chat.id})")

            welcome_msg = (
                f"👋 Привет! Я бот для скачивания видео.\n\n"
                f"🎬 <b>Мне нужны разрешения:</b>\n"
                f"✓ Отправлять сообщения\n"
                f"✓ Редактировать свои сообщения\n"
                f"✓ Загружать видео/медиа\n\n"
                f"<b>Как меня использовать:</b>\n"
                f"1️⃣ Просто отправь ссылку на видео\n"
                f"2️⃣ Выбери качество из кнопок\n"
                f"3️⃣ Жди загрузку видео\n\n"
                f"<b>✅ Поддерживаемые сайты:</b>\n"
                f"YouTube ✅ | Instagram ✅ | Facebook ✅\n"
                f"Twitter ✅ | Vimeo ✅ | Dailymotion ✅\n"
                f"SoundCloud ✅ | Spotify ✅ | Snapchat ✅\n"
                f"TikTok ⚠️ (ограниченная поддержка)\n\n"
                f"⚠️ <b>Важно:</b> Пожалуйста, убедись что у меня есть необходимые разрешения!"
            )

            try:
                await bot.send_message(
                    chat_id=chat.id,
                    text=welcome_msg,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"⚠️ Could not send message to group: {e}")


@dp.message(CommandStart())
async def start(message: types.Message):
    """Handle /start command"""
    chat = message.chat

    if chat.type in ["group", "supergroup"]:
        await message.answer(
            "🎬 Загрузчик видео активен!\n\n"
            "📤 Отправь ссылку на видео:"
        )
    else:
        await message.answer(
            "🎬 <b>Загрузчик видео и аудио</b>\n\n"
            "✅ <b>FFmpeg установлен</b>\n\n"
            "<b>✅ Отлично поддерживаемые:</b>\n"
            "• YouTube (все качества 144p-4K+)\n"
            "• Instagram (видео и фото)\n"
            "• Facebook (видео)\n"
            "• Twitter/X (видео)\n"
            "• Vimeo\n"
            "• Dailymotion\n"
            "• SoundCloud (аудио)\n"
            "• Spotify (ограничено)\n"
            "• Snapchat\n\n"
            "<b>⚠️ Ограниченная поддержка:</b>\n"
            "• TikTok (блокировка от TikTok)\n\n"
            "📤 <b>Просто отправь ссылку!</b>",
            parse_mode="HTML"
        )


@dp.message(Command("help"))
async def help_cmd(message: types.Message):
    """Handle /help command"""
    await message.answer(
        f"📖 <b>Как использовать:</b>\n\n"
        "1️⃣ Отправь ссылку на видео\n"
        "2️⃣ Выбери качество из доступных опций\n"
        "3️⃣ Жди загрузки видео\n\n"
        f"<b>✅ Хорошо поддерживаемые сайты:</b>\n"
        "YouTube, Instagram, Facebook, Twitter/X, Vimeo, Dailymotion, SoundCloud, Spotify, Snapchat\n\n"
        f"<b>⚠️ TikTok:</b>\n"
        "Поддержка ограничена из-за защиты TikTok от ботов. Некоторые видео могут не работать.\n\n"
        f"<b>🎵 Опции загрузки:</b>\n"
        "Бот покажет все доступные качества видео. Просто выбери нужное!",
        parse_mode="HTML"
    )


@dp.message()
async def handle(message: types.Message):
    """Handle URL messages"""
    if not message.text:
        await message.answer(
            "❌ Пожалуйста, отправь текстовое сообщение со ссылкой.\n"
            "Я не могу обработать медиа файлы, только текстовые ссылки."
        )
        return

    url = message.text.strip()

    if not url or (not url.startswith("http://") and not url.startswith("https://")):
        await message.answer(
            "❌ Это не похоже на ссылку.\n"
            "Отправь ссылку в формате: https://youtube.com/watch?v=..."
        )
        return

    if not is_supported_source(url):
        await message.answer(
            "❌ Ссылка не поддерживается.\n\n"
            "<b>✅ Поддерживаемые сайты:</b>\n"
            "YouTube, Instagram, Facebook, Twitter/X, Vimeo, Dailymotion, SoundCloud, Spotify, Snapchat, TikTok"
        )
        return

    source_name = get_source_name(url)
    status_msg = await message.answer(
        f"⏳ Анализирую {source_name}..."
    )

    try:
        info, formats = get_formats(url)

        if not formats:
            await status_msg.edit_text(
                "❌ Нет доступных форматов"
            )
            return

        video_id = str(uuid.uuid4())

        video_data[video_id] = {
            "url": url,
            "formats": formats,
            "info": info
        }

        # Create buttons for each available quality
        buttons = []

        # Sort formats by quality (descending)
        sorted_formats = sorted(formats, key=lambda x: x["quality"], reverse=True)

        # Add quality buttons (2 per row)
        for i in range(0, len(sorted_formats), 2):
            row = []

            # First button
            fmt = sorted_formats[i]
            quality = int(fmt["quality"])
            row.append(
                InlineKeyboardButton(
                    text=f"📹 {quality}p",
                    callback_data=f"{video_id}|quality|{i}"
                )
            )

            # Second button (if exists)
            if i + 1 < len(sorted_formats):
                fmt = sorted_formats[i + 1]
                quality = int(fmt["quality"])
                row.append(
                    InlineKeyboardButton(
                        text=f"📹 {quality}p",
                        callback_data=f"{video_id}|quality|{i + 1}"
                    )
                )

            buttons.append(row)

        # Add MP3 button if it's audio capable
        buttons.append([
            InlineKeyboardButton(
                text="🎵 MP3",
                callback_data=f"{video_id}|mp3|0"
            )
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        title = info.get('title', 'Видео')[:100]
        duration = info.get('duration', 0)

        try:
            duration = int(duration)
            duration_str = f"{duration // 60}:{duration % 60:02d}"
        except (ValueError, TypeError):
            duration_str = "?"

        all_qualities = sorted([int(f["quality"]) for f in formats if isinstance(f.get("quality"), (int, float))])
        min_q = int(min(all_qualities)) if all_qualities else "?"
        max_q = int(max(all_qualities)) if all_qualities else "?"

        # Count available qualities
        quality_count = len(all_qualities)

        await status_msg.edit_text(
            f"📹 <b>{title}</b>\n"
            f"🔗 {source_name} | ⏱️ {duration_str} мин\n"
            f"📊 Доступно качеств: {quality_count} ({min_q}p - {max_q}p)\n\n"
            f"<b>Выбери качество:</b>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error: {error_msg}")

        is_tiktok = "tiktok" in url

        if is_tiktok:
            await status_msg.edit_text(
                "⚠️ <b>TikTok видео недоступно</b>\n\n"
                "😕 К сожалению, TikTok активно блокирует загрузки ботами.\n\n"
                "<b>Это ограничение TikTok, не нашего бота.</b>\n\n"
                "Попробуй:\n"
                "• Другое видео\n"
                "• Позже (через 5-10 минут)\n"
                "• Приватные боты TikTok (они используют специальные API)\n\n"
                "Боты на других платформах работают намного лучше! 👍"
            )
        elif "Sign in" in error_msg or "log in" in error_msg:
            await status_msg.edit_text(
                "⚠️ Сайт требует авторизацию.\n"
                "Попробуй через несколько секунд."
            )
        elif "No video" in error_msg or "not available" in error_msg or "removed" in error_msg.lower():
            await status_msg.edit_text(
                "⚠️ Видео недоступно или удалено.\n"
                "Проверь, что ссылка корректна и видео публичное."
            )
        elif "429" in error_msg or "Too Many" in error_msg or "rate" in error_msg.lower():
            await status_msg.edit_text(
                "⚠️ Слишком частые запросы.\n"
                "Подожди 3-5 минут и попробуй снова."
            )
        elif "Connection" in error_msg or "timeout" in error_msg.lower():
            await status_msg.edit_text(
                "⚠️ Ошибка соединения.\n"
                "Проверь интернет и попробуй снова через несколько секунд."
            )
        else:
            await status_msg.edit_text(f"❌ Ошибка: {error_msg[:100]}")


@dp.callback_query(F.data)
async def callback(call: types.CallbackQuery):
    """Handle quality selection"""
    try:
        parts = call.data.split("|")
        video_id = parts[0]
        action = parts[1]
        param = int(parts[2]) if len(parts) > 2 else 0

        video_info = video_data.get(video_id)

        if not video_info:
            await call.message.edit_text("❌ Данные видео не найдены")
            return

        is_audio = action == "mp3"

        if is_audio:
            status = await call.message.edit_text("⬇️ Скачиваю MP3...")
            format_id = None
        else:
            # Get format by index
            sorted_formats = sorted(video_info["formats"], key=lambda x: x["quality"], reverse=True)

            if param >= len(sorted_formats):
                await call.message.edit_text("❌ Формат не найден")
                return

            selected_format = sorted_formats[param]
            format_id = selected_format["format_id"]
            quality = int(selected_format["quality"])
            status = await call.message.edit_text(f"⬇️ Скачиваю {quality}p...")

        temp_dir = os.path.join(TEMP_DIR, "video_downloads")
        base_name = video_id

        loop = asyncio.get_event_loop()

        filename = await loop.run_in_executor(
            None,
            download_video,
            video_info["url"],
            format_id,
            temp_dir,
            base_name,
            is_audio
        )

        if not os.path.exists(filename):
            raise FileNotFoundError(f"Файл не найден: {filename}")

        file_size = os.path.getsize(filename)

        if file_size > 2 * 1024 * 1024 * 1024:
            os.remove(filename)
            await status.edit_text("❌ Файл слишком большой (макс 2GB)")
            return

        await status.edit_text(f"📤 Загружаю ({format_file_size(file_size)})...")

        title = video_info["info"].get('title', 'Медиа')[:100]

        if is_audio:
            await call.message.answer_audio(
                FSInputFile(filename),
                title=title,
                caption=f"✅ MP3 ({format_file_size(file_size)})"
            )
        else:
            quality = int(selected_format["quality"])
            await call.message.answer_video(
                FSInputFile(filename),
                caption=f"✅ {quality}p ({format_file_size(file_size)})"
            )

        if os.path.exists(filename):
            os.remove(filename)

        try:
            await status.delete()
        except:
            pass

    except Exception as e:
        logger.error(f"Error in callback: {e}")
        error_msg = str(e)

        msg = f"❌ Ошибка: {error_msg[:100]}"

        try:
            await call.message.edit_text(msg)
        except:
            await call.message.answer(msg)

        try:
            if 'filename' in locals() and os.path.exists(filename):
                os.remove(filename)
        except:
            pass


async def main():
    """Start bot"""
    logger.info("🤖 Bot starting...")
    logger.info(f"FFmpeg: {FFMPEG_LOCATION}")
    logger.info("✅ Bot is running 24/7!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
