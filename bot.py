import os
import io
import random
import time
import re
import subprocess
import shutil
import sqlite3
from datetime import datetime, date
from threading import Thread
from flask import Flask
from dotenv import load_dotenv
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)
from PIL import Image, ImageEnhance, ImageFilter, ImageTransform
import numpy as np
import yt_dlp
import instaloader
import requests

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in .env file!")

# ====================== CONFIG ======================
ADMIN_USERNAME = "pvnuo"          # sirf yeh user admin commands use kar sakta hai
DAILY_FREE_LIMIT = 5
DB_FILE = "bot_data.db"
# ====================================================

# ------------------------------------------------------
# Database
# ------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS lifetime_free (
            user_id INTEGER PRIMARY KEY
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_usage (
            user_id INTEGER,
            usage_date TEXT,
            count INTEGER,
            PRIMARY KEY (user_id, usage_date)
        )
    """)
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('global_free', '0')")
    conn.commit()
    conn.close()

def is_global_free() -> bool:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'global_free'")
    row = c.fetchone()
    conn.close()
    return row and row[0] == "1"

def set_global_free(enabled: bool):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('global_free', ?)", 
              ("1" if enabled else "0",))
    conn.commit()
    conn.close()

def is_lifetime_free(user_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM lifetime_free WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row)

def add_lifetime_free(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO lifetime_free (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def remove_lifetime_free(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM lifetime_free WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_lifetime_free_list() -> list:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM lifetime_free")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_today_usage(user_id: int) -> int:
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT count FROM daily_usage WHERE user_id = ? AND usage_date = ?", (user_id, today))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def increment_usage(user_id: int):
    today = date.today().isoformat()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO daily_usage (user_id, usage_date, count) VALUES (?, ?, 1)
        ON CONFLICT(user_id, usage_date) DO UPDATE SET count = count + 1
    """, (user_id, today))
    conn.commit()
    conn.close()

def can_use_bot(user_id: int, username: str = None) -> tuple[bool, str]:
    if username and username.lower() == ADMIN_USERNAME.lower():
        return True, ""

    if is_global_free():
        return True, ""

    if is_lifetime_free(user_id):
        return True, ""

    used = get_today_usage(user_id)
    if used < DAILY_FREE_LIMIT:
        return True, ""

    return False, (
        "You have used all 5 free links for today.\n"
        "Please try again tomorrow or contact @pvnuo for unlimited access."
    )

# ------------------------------------------------------
# Flask keep-alive
# ------------------------------------------------------
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "Bot is alive and running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

# ------------------------------------------------------
# Image enhance
# ------------------------------------------------------
def enhance_image(image: Image.Image) -> Image.Image:
    if image.mode != "RGB":
        image = image.convert("RGB")
    width, height = image.size
    crop = random.uniform(0.04, 0.08)
    left = int(width * crop * random.uniform(0.2, 0.9))
    top = int(height * crop * random.uniform(0.2, 0.9))
    right = width - int(width * crop * random.uniform(0.2, 0.9))
    bottom = height - int(height * crop * random.uniform(0.2, 0.9))
    image = image.crop((left, top, right, bottom))
    angle = random.uniform(-2.5, 2.5)
    image = image.rotate(angle, resample=Image.BICUBIC, expand=False)
    w, h = image.size
    dx = random.uniform(-0.01, 0.01) * w
    dy = random.uniform(-0.01, 0.01) * h
    coeffs = ImageTransform.AffineTransform(
        (
            1 + random.uniform(-0.007, 0.007),
            random.uniform(-0.005, 0.005),
            dx,
            random.uniform(-0.005, 0.005),
            1 + random.uniform(-0.007, 0.007),
            dy,
        )
    )
    image = image.transform(image.size, Image.AFFINE, coeffs.data, resample=Image.BICUBIC)
    image = ImageEnhance.Color(image).enhance(random.uniform(1.10, 1.25))
    image = ImageEnhance.Brightness(image).enhance(random.uniform(1.02, 1.09))
    image = ImageEnhance.Contrast(image).enhance(random.uniform(1.05, 1.15))
    image = ImageEnhance.Sharpness(image).enhance(random.uniform(1.15, 1.40))
    r, g, b = image.split()
    r = r.point(lambda i: min(255, max(0, i + random.randint(-8, 9))))
    g = g.point(lambda i: min(255, max(0, i + random.randint(-6, 7))))
    b = b.point(lambda i: min(255, max(0, i + random.randint(-9, 8))))
    image = Image.merge("RGB", (r, g, b))
    arr = np.array(image).astype(np.int16)
    noise = np.random.randint(-4, 5, arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    image = Image.fromarray(arr)
    if random.random() > 0.45:
        image = image.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.25, 0.6)))
    image = image.filter(
        ImageFilter.UnsharpMask(
            radius=random.uniform(1.3, 2.0),
            percent=random.randint(135, 180),
            threshold=random.randint(1, 3),
        )
    )
    scale = random.uniform(1.02, 1.07)
    image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
    return image

# ------------------------------------------------------
# Video enhance
# ------------------------------------------------------
def enhance_video(input_path: str, output_path: str) -> bool:
    brightness = random.uniform(-0.05, 0.07)
    contrast = random.uniform(1.07, 1.16)
    saturation = random.uniform(1.10, 1.22)
    gamma = random.uniform(0.94, 1.07)
    hue = random.uniform(-5, 5)
    noise_str = random.randint(5, 11)
    crop_pct = random.uniform(0.012, 0.022)
    vf = (
        f"crop=iw*(1-{crop_pct}):ih*(1-{crop_pct}),"
        f"scale=trunc(iw/2)*2:trunc(ih/2)*2,"
        f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}:gamma={gamma},"
        f"hue=h={hue},"
        f"noise=alls={noise_str}:allf=t,"
        f"unsharp=5:5:1.3:5:5:0.6,"
        f"format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "faster",
        "-crf", "18",
        "-c:a", "copy",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        output_path
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
            text=True
        )
        if result.returncode != 0:
            print("===== FFMPEG ERROR =====")
            print(result.stderr[-1500:] if result.stderr else "No stderr")
            return False
        return os.path.exists(output_path) and os.path.getsize(output_path) > 20000
    except Exception as e:
        print(f"FFmpeg Exception: {e}")
        return False

# ------------------------------------------------------
# Admin Commands
# ------------------------------------------------------
async def freeall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or (user.username or "").lower() != ADMIN_USERNAME.lower():
        return
    set_global_free(True)
    await update.message.reply_text("✅ Bot is now FREE for everyone.")

async def removefreeall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or (user.username or "").lower() != ADMIN_USERNAME.lower():
        return
    set_global_free(False)
    await update.message.reply_text("✅ Daily limit mode is now active again.")

async def freeuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or (user.username or "").lower() != ADMIN_USERNAME.lower():
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "/freeuser @username\n"
            "/freeuser 123456789\n\n"
            "Note: User must have started the bot at least once."
        )
        return

    target = context.args[0].lstrip("@")
    try:
        if target.isdigit():
            target_id = int(target)
            chat = await context.bot.get_chat(target_id)
        else:
            chat = await context.bot.get_chat(f"@{target}")
            target_id = chat.id

        add_lifetime_free(target_id)
        await update.message.reply_text(f"✅ @{chat.username or target_id} now has lifetime unlimited access.")

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="🎉 You now have unlimited access to this bot forever!\nEnjoy."
            )
        except:
            pass

    except Exception as e:
        await update.message.reply_text(
            f"❌ Could not find user.\n\n"
            f"Possible reasons:\n"
            f"• User has never started this bot\n"
            f"• Username is incorrect\n\n"
            f"Solution: Ask the user to send /start to the bot first, then try again.\n"
            f"Or use their numeric User ID."
        )

async def removefree(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or (user.username or "").lower() != ADMIN_USERNAME.lower():
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "/removefree @username\n"
            "/removefree 123456789"
        )
        return

    target = context.args[0].lstrip("@")
    try:
        if target.isdigit():
            target_id = int(target)
            chat = await context.bot.get_chat(target_id)
        else:
            chat = await context.bot.get_chat(f"@{target}")
            target_id = chat.id

        remove_lifetime_free(target_id)
        await update.message.reply_text(f"✅ Removed lifetime free from @{chat.username or target_id}")

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="Your unlimited access has been removed.\nYou are now on the free daily limit (5 links per day)."
            )
        except:
            pass

    except Exception as e:
        await update.message.reply_text(
            f"❌ Could not find user.\n\n"
            f"User must have started the bot at least once.\n"
            f"Try using their numeric User ID instead."
        )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or (user.username or "").lower() != ADMIN_USERNAME.lower():
        return

    global_free = is_global_free()
    free_list = get_lifetime_free_list()

    text = f"📊 Bot Status\n\n"
    text += f"Global Free Mode: {'ON ✅' if global_free else 'OFF (Daily limit active)'}\n"
    text += f"Daily Free Limit: {DAILY_FREE_LIMIT}\n\n"
    text += f"Lifetime Free Users ({len(free_list)}):\n"

    if free_list:
        for uid in free_list:
            text += f"• {uid}\n"
    else:
        text += "None\n"

    await update.message.reply_text(text)

# ------------------------------------------------------
# Commands
# ------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Welcome!\n\n"
        "Just send me any image or video and I will give you a modified version.\n"
        "The changes help make the content different from the original while keeping high visual quality.\n\n"
        "You can also send any 📸 Instagram, 🎵 TikTok or 𝕏 Twitter/X link and I will download it for you in original quality.\n\n"
        "Commands:\n"
        "/about - More information about this bot\n"
        "/help  - How to use\n"
        "/how   - How it works\n\n"
        "In groups: You must mention me with the photo, video or link.\n\n"
        "For any help contact: @pvnuo"
    )
    await update.message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Available Commands:\n\n"
        "/start  – Start the bot\n"
        "/help   – Show this help\n"
        "/about  – About this bot\n"
        "/how    – How it works\n\n"
        "How to use:\n"
        "• Send any photo → get a unique modified version\n"
        "• Send any video → get a unique high-quality version\n"
        "• Send 📸 Instagram / 🎵 TikTok / 𝕏 Twitter/X link → download media in original quality\n\n"
        "In groups: mention me with the photo, video or link."
    )
    await update.message.reply_text(text)

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "About this Bot:\n\n"
        "• Just send me any image or video and I will give you a modified version.\n"
        "• The changes help make the content different from the original while keeping high visual quality.\n"
        "• You can also send any 📸 Instagram, 🎵 TikTok or 𝕏 Twitter/X link and I will download the media for you in original quality.\n\n"
        "In groups: You must mention me with the photo, video or link.\n\n"
        "For any help contact: @pvnuo"
    )
    await update.message.reply_text(text)

async def how(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "How it works:\n\n"
        "Photo mode:\n"
        "1. You send a photo\n"
        "2. I apply unique modifications\n"
        "3. You get a new version\n\n"
        "Video mode:\n"
        "1. You send a video\n"
        "2. I apply unique changes (light crop, color, noise, sharpen)\n"
        "3. You get a high-quality unique version\n\n"
        "Link mode (📸 Instagram / 🎵 TikTok / 𝕏 Twitter/X):\n"
        "1. You send a link\n"
        "2. I download the media in original quality\n"
        "3. You receive it\n\n"
        "In groups: always mention me."
    )
    await update.message.reply_text(text)

# ------------------------------------------------------
# Image handler
# ------------------------------------------------------
async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if message.chat.type in ["group", "supergroup"]:
        bot_username = (await context.bot.get_me()).username.lower()
        caption = (message.caption or "").lower()
        mentioned = f"@{bot_username}" in caption
        is_reply = False
        if message.reply_to_message and message.reply_to_message.from_user:
            if (message.reply_to_message.from_user.is_bot and
                message.reply_to_message.from_user.username and
                message.reply_to_message.from_user.username.lower() == bot_username):
                is_reply = True
        if not mentioned and not is_reply:
            return

    start_time = time.time()
    try:
        if message.photo:
            file = await context.bot.get_file(message.photo[-1].file_id)
        elif message.document and message.document.mime_type and "image" in message.document.mime_type:
            file = await context.bot.get_file(message.document.file_id)
        else:
            return

        image_bytes = await file.download_as_bytearray()
        image = Image.open(io.BytesIO(image_bytes))
        result = enhance_image(image)

        output = io.BytesIO()
        quality = random.randint(93, 97)
        result.save(output, format="JPEG", quality=quality, optimize=True, progressive=True, subsampling=0)
        output.seek(0)

        elapsed = round(time.time() - start_time, 2)
        await message.reply_photo(
            photo=output,
            caption=f"✅ Unique version ready\n⏱ {elapsed}s | Quality: {quality}",
        )
    except Exception as e:
        print(f"Image error: {e}")
        await message.reply_text("❌ Failed to process the image.")

# ------------------------------------------------------
# Video handler
# ------------------------------------------------------
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if message.chat.type in ["group", "supergroup"]:
        bot_username = (await context.bot.get_me()).username.lower()
        caption = (message.caption or "").lower()
        mentioned = f"@{bot_username}" in caption
        is_reply = False
        if message.reply_to_message and message.reply_to_message.from_user:
            if (message.reply_to_message.from_user.is_bot and
                message.reply_to_message.from_user.username and
                message.reply_to_message.from_user.username.lower() == bot_username):
                is_reply = True
        if not mentioned and not is_reply:
            return

    status_msg = None
    unique_id = str(int(time.time() * 1000))
    input_path = f"input_{unique_id}.mp4"
    output_path = f"output_{unique_id}.mp4"

    try:
        status_msg = await message.reply_text("⏳ Processing video... (30-40 sec)")

        if message.video:
            file = await context.bot.get_file(message.video.file_id)
        elif message.document and message.document.mime_type and "video" in message.document.mime_type:
            file = await context.bot.get_file(message.document.file_id)
        else:
            await status_msg.edit_text("❌ Unsupported video format.")
            return

        await file.download_to_drive(input_path)
        success = enhance_video(input_path, output_path)

        if success and os.path.exists(output_path):
            file_size = os.path.getsize(output_path)

            if file_size > 48 * 1024 * 1024:
                compressed = f"compressed_{unique_id}.mp4"
                cmd = [
                    "ffmpeg", "-y", "-i", output_path,
                    "-c:v", "libx264", "-preset", "faster", "-crf", "23",
                    "-c:a", "copy", "-movflags", "+faststart",
                    compressed
                ]
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
                if os.path.exists(compressed) and os.path.getsize(compressed) > 20000:
                    os.remove(output_path)
                    output_path = compressed

            try:
                with open(output_path, "rb") as vid:
                    await message.reply_video(
                        video=vid,
                        caption="✅ Here’s your modified video",
                        supports_streaming=True,
                    )
                try:
                    await status_msg.delete()
                except:
                    pass
            except Exception as send_err:
                err_str = str(send_err).lower()
                if "413" in err_str or "too large" in err_str or "entity too large" in err_str:
                    await status_msg.edit_text("❌ Video too large after processing (Telegram 50MB limit).")
                else:
                    await status_msg.edit_text("❌ Failed to send the video.")
                    print(f"Send error: {send_err}")
        else:
            await status_msg.edit_text("❌ Failed to process the video.")
    except Exception as e:
        print(f"Video error: {e}")
        if status_msg:
            try:
                await status_msg.edit_text("❌ Failed to process the video.")
            except:
                pass
    finally:
        for p in [input_path, output_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass
        for f in os.listdir("."):
            if f.startswith(f"compressed_{unique_id}"):
                try:
                    os.remove(f)
                except:
                    pass

# ------------------------------------------------------
# Instagram
# ------------------------------------------------------
def download_instagram(url: str, unique_id: str):
    L = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        post_metadata_txt_pattern="",
        max_connection_attempts=3,
    )
    shortcode = None
    if "/p/" in url:
        shortcode = url.split("/p/")[1].split("/")[0].split("?")[0]
    elif "/reel/" in url:
        shortcode = url.split("/reel/")[1].split("/")[0].split("?")[0]
    elif "/tv/" in url:
        shortcode = url.split("/tv/")[1].split("/")[0].split("?")[0]
    if not shortcode:
        return []
    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
    except Exception as e:
        print(f"Instaloader error: {e}")
        return []
    paths = []
    folder = f"temp_{unique_id}"
    os.makedirs(folder, exist_ok=True)
    try:
        L.download_post(post, target=folder)
        for file in os.listdir(folder):
            full = os.path.join(folder, file)
            if file.endswith((".jpg", ".jpeg", ".png", ".webp", ".mp4")):
                paths.append(full)
    except Exception as e:
        print(f"Download post error: {e}")
    return paths

# ------------------------------------------------------
# TikTok
# ------------------------------------------------------
async def download_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    status_text = await update.message.reply_text("Downloading from 🎵 TikTok...")
    status_emoji = await update.message.reply_text("⌛")
    unique_id = str(int(time.time() * 1000))
    folder = f"tt_{unique_id}_dir"
    os.makedirs(folder, exist_ok=True)
    paths = []
    opened_files = []

    try:
        ydl_opts = {
            "outtmpl": os.path.join(folder, f"tt_{unique_id}.%(ext)s"),
            "format": "best",
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 40,
            "retries": 8,
            "fragment_retries": 8,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Referer": "https://www.tiktok.com/",
            },
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                base = filename.rsplit(".", 1)[0]
                for ext in [".mp4", ".mkv", ".webm", ".mp3", ".m4a"]:
                    candidate = base + ext
                    if os.path.exists(candidate):
                        paths.append(candidate)
                        break
        except Exception as e:
            print(f"yt-dlp TikTok: {e}")

        has_video = any(p.lower().endswith((".mp4", ".mkv", ".webm")) for p in paths)
        if not has_video:
            try:
                cmd = [
                    "gallery-dl",
                    "--dest", folder,
                    "--filename", "{id}_{num}.{extension}",
                    "--no-mtime",
                    url
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
                if result.returncode == 0:
                    for root, _, files in os.walk(folder):
                        for f in files:
                            full = os.path.join(root, f)
                            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mp3")):
                                paths.append(full)
            except Exception as e:
                print(f"gallery-dl error: {e}")

        images = [p for p in paths if p.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
        videos = [p for p in paths if p.lower().endswith((".mp4", ".mkv", ".webm"))]
        audios = [p for p in paths if p.lower().endswith((".mp3", ".m4a"))]

        success = False

        if images:
            media = []
            for p in images[:10]:
                f = open(p, "rb")
                opened_files.append(f)
                media.append(InputMediaPhoto(f))
            await update.message.reply_media_group(media=media)
            success = True

        for v in videos:
            with open(v, "rb") as vid:
                await update.message.reply_video(
                    video=vid,
                    caption="✅ Here’s your TikTok video",
                    supports_streaming=True,
                )
            success = True

        if not success and audios:
            with open(audios[0], "rb") as a:
                await update.message.reply_audio(audio=a, caption="🎵 TikTok audio")
            success = True

        if success:
            try:
                await status_text.delete()
                await status_emoji.delete()
            except:
                pass
        else:
            try:
                await status_text.edit_text("❌ Failed to download. Make sure the link is public.")
                await status_emoji.delete()
            except:
                pass

    except Exception as e:
        print(f"TikTok error: {e}")
        try:
            await status_text.edit_text(f"❌ Failed to download TikTok.\n{str(e)[:120]}")
            await status_emoji.delete()
        except:
            pass
    finally:
        for f in opened_files:
            try:
                f.close()
            except:
                pass

        if os.path.exists(folder):
            try:
                shutil.rmtree(folder, ignore_errors=True)
            except:
                pass

        try:
            for item in os.listdir("."):
                if item.startswith(f"tt_{unique_id}") or item.startswith(f"temp_{unique_id}"):
                    path = os.path.join(".", item)
                    try:
                        if os.path.isdir(path):
                            shutil.rmtree(path, ignore_errors=True)
                        else:
                            os.remove(path)
                    except:
                        pass
        except:
            pass

# ------------------------------------------------------
# Twitter / X
# ------------------------------------------------------
async def download_twitter(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    status_text = await update.message.reply_text("Downloading from 𝕏 Twitter/X...")
    status_emoji = await update.message.reply_text("⌛")
    unique_id = str(int(time.time() * 1000))
    folder = f"tw_{unique_id}_dir"
    os.makedirs(folder, exist_ok=True)
    paths = []
    opened_files = []

    try:
        ydl_opts = {
            "outtmpl": os.path.join(folder, f"tw_{unique_id}_%(id)s.%(ext)s"),
            "format": "best",
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 40,
            "retries": 8,
            "fragment_retries": 8,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Referer": "https://x.com/",
            },
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if "entries" in info:
                    for entry in info["entries"]:
                        if entry:
                            filename = ydl.prepare_filename(entry)
                            base = filename.rsplit(".", 1)[0]
                            for ext in [".mp4", ".mkv", ".webm", ".jpg", ".jpeg", ".png", ".webp"]:
                                candidate = base + ext
                                if os.path.exists(candidate):
                                    paths.append(candidate)
                else:
                    filename = ydl.prepare_filename(info)
                    base = filename.rsplit(".", 1)[0]
                    for ext in [".mp4", ".mkv", ".webm", ".jpg", ".jpeg", ".png", ".webp"]:
                        candidate = base + ext
                        if os.path.exists(candidate):
                            paths.append(candidate)
                            break
        except Exception as e:
            print(f"yt-dlp Twitter: {e}")

        if not paths:
            try:
                cmd = [
                    "gallery-dl",
                    "--dest", folder,
                    "--filename", "{id}_{num}.{extension}",
                    "--no-mtime",
                    url
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
                if result.returncode == 0:
                    for root, _, files in os.walk(folder):
                        for f in files:
                            full = os.path.join(root, f)
                            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mkv", ".webm")):
                                paths.append(full)
            except Exception as e:
                print(f"gallery-dl Twitter error: {e}")

        images = [p for p in paths if p.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
        videos = [p for p in paths if p.lower().endswith((".mp4", ".mkv", ".webm"))]

        success = False

        if images:
            media = []
            for p in images[:10]:
                f = open(p, "rb")
                opened_files.append(f)
                media.append(InputMediaPhoto(f))
            await update.message.reply_media_group(media=media)
            success = True

        for v in videos:
            with open(v, "rb") as vid:
                await update.message.reply_video(
                    video=vid,
                    caption="✅ Here’s your Twitter/X video",
                    supports_streaming=True,
                )
            success = True

        if success:
            try:
                await status_text.delete()
                await status_emoji.delete()
            except:
                pass
        else:
            try:
                await status_text.edit_text("❌ Failed to download. Make sure the link is public.")
                await status_emoji.delete()
            except:
                pass

    except Exception as e:
        print(f"Twitter error: {e}")
        try:
            await status_text.edit_text(f"❌ Failed to download Twitter/X.\n{str(e)[:120]}")
            await status_emoji.delete()
        except:
            pass
    finally:
        for f in opened_files:
            try:
                f.close()
            except:
                pass

        if os.path.exists(folder):
            try:
                shutil.rmtree(folder, ignore_errors=True)
            except:
                pass

        try:
            for item in os.listdir("."):
                if item.startswith(f"tw_{unique_id}") or item.startswith(f"temp_{unique_id}"):
                    path = os.path.join(".", item)
                    try:
                        if os.path.isdir(path):
                            shutil.rmtree(path, ignore_errors=True)
                        else:
                            os.remove(path)
                    except:
                        pass
        except:
            pass

# ------------------------------------------------------
# Text handler
# ------------------------------------------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()
    user = update.effective_user
    user_id = user.id if user else 0
    username = user.username if user else None

    if not text.startswith("http"):
        await message.reply_text(
            "About this Bot:\n\n"
            "• Just send me any image or video and I will give you a modified version.\n"
            "• The changes help make the content different from the original while keeping high visual quality.\n"
            "• You can also send any 📸 Instagram, 🎵 TikTok or 𝕏 Twitter/X link and I will download the media for you in original quality.\n\n"
            "In groups: You must mention me with the photo, video or link.\n\n"
            "For any help contact: @pvnuo"
        )
        return

    # ===== LIMIT CHECK =====
    allowed, limit_msg = can_use_bot(user_id, username)
    if not allowed:
        await message.reply_text(limit_msg)
        return

    if message.chat.type in ["group", "supergroup"]:
        bot_username = (await context.bot.get_me()).username.lower()
        mentioned = f"@{bot_username}" in text.lower()
        is_reply = False
        if message.reply_to_message and message.reply_to_message.from_user:
            if (message.reply_to_message.from_user.is_bot and
                message.reply_to_message.from_user.username and
                message.reply_to_message.from_user.username.lower() == bot_username):
                is_reply = True
        if not mentioned and not is_reply:
            return

    lower = text.lower()

    # Twitter / X
    if "twitter.com" in lower or "x.com" in lower or "t.co" in lower:
        increment_usage(user_id)
        await download_twitter(update, context, text)
        return

    # TikTok
    if "tiktok.com" in lower or "vt.tiktok.com" in lower or "vm.tiktok.com" in lower:
        increment_usage(user_id)
        await download_tiktok(update, context, text)
        return

    # Instagram
    if "instagram.com" in lower:
        increment_usage(user_id)
        clean_url = re.sub(r"[?&](utm_|igshid|stkn|igsh)=[^&]+", "", text)
        clean_url = clean_url.split("?")[0].rstrip("/")
        
        status_text = await message.reply_text("Downloading from 📸 Instagram...")
        status_emoji = await message.reply_text("⌛")
        
        unique_id = str(int(time.time() * 1000))
        paths = []
        try:
            paths = download_instagram(clean_url, unique_id)
            if not paths:
                ydl_opts = {
                    "outtmpl": f"ig_{unique_id}.%(ext)s",
                    "quiet": True,
                    "no_warnings": True,
                    "format": "best",
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(clean_url, download=True)
                    filename = ydl.prepare_filename(info)
                    if os.path.exists(filename):
                        paths = [filename]

            if paths:
                images = [p for p in paths if p.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
                videos = [p for p in paths if p.lower().endswith(".mp4")]
                if images:
                    media = [InputMediaPhoto(open(p, "rb")) for p in images[:10]]
                    await message.reply_media_group(media=media)
                for v in videos:
                    with open(v, "rb") as vid:
                        await message.reply_video(video=vid, caption="✨ Instagram video", supports_streaming=True)
                try:
                    await status_text.delete()
                    await status_emoji.delete()
                except:
                    pass
            else:
                try:
                    await status_text.edit_text("❌ Failed. Make sure link is public.")
                    await status_emoji.delete()
                except:
                    pass
        except Exception as e:
            print(f"IG error: {e}")
            try:
                await status_text.edit_text("❌ Failed to download.")
                await status_emoji.delete()
            except:
                pass
        finally:
            for p in paths:
                try:
                    os.remove(p)
                except:
                    pass
            folder = f"temp_{unique_id}"
            if os.path.exists(folder):
                try:
                    shutil.rmtree(folder, ignore_errors=True)
                except:
                    pass
            for f in os.listdir("."):
                if f.startswith(f"ig_{unique_id}"):
                    try:
                        os.remove(f)
                    except:
                        pass
        return

    await message.reply_text("❌ Only 📸 Instagram, 🎵 TikTok and 𝕏 Twitter/X links are supported.")

# ------------------------------------------------------
# Main
# ------------------------------------------------------
def main():
    init_db()
    keep_alive()
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )

    # Normal commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("how", how))

    # Admin commands
    app.add_handler(CommandHandler("freeall", freeall))
    app.add_handler(CommandHandler("removefreeall", removefreeall))
    app.add_handler(CommandHandler("freeuser", freeuser))
    app.add_handler(CommandHandler("removefree", removefree))
    app.add_handler(CommandHandler("status", status))

    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_image))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot started successfully...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
