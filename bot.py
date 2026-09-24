import os
import io
import random
import time
import re
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
# Strong unique image processing
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
# Commands
# ------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Welcome!\n\n"
        "I can do two things:\n\n"
        "1️⃣ Send any photo → I will modify it so it looks different from the original.\n\n"
        "2️⃣ Send any Instagram link (Post / Reel / Carousel) → "
        "I will download the original high-quality media.\n\n"
        "Just send a photo or an Instagram link."
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
        "• Send Instagram Post / Reel / Carousel link → get original media\n\n"
        "In groups: mention me with the photo or link."
    )
    await update.message.reply_text(text)


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "About this Bot:\n\n"
        "Send me any image and I will modify it so it becomes different from the original "
        "while keeping high visual quality. This helps avoid Instagram’s duplicate / "
        "unoriginal content restrictions.\n\n"
        "You can also send any Instagram Post, Reel or Carousel link "
        "and I will download the original high-quality media for you.\n\n"
        "In groups: You must mention me with the photo or link.\n\n"
        "For any help contact: @coolmoco"
    )
    await update.message.reply_text(text)


async def how(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "How it works:\n\n"
        "📷 Photo mode:\n"
        "1. You send a photo\n"
        "2. I modify it to make it unique\n"
        "3. You get a new version\n\n"
        "🔗 Instagram link mode:\n"
        "1. You send a Post / Reel / Carousel link\n"
        "2. I download the original media\n"
        "3. You receive it in high quality\n\n"
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

        is_reply_to_bot = False
        if message.reply_to_message and message.reply_to_message.from_user:
            if (
                message.reply_to_message.from_user.is_bot
                and message.reply_to_message.from_user.username
                and message.reply_to_message.from_user.username.lower() == bot_username
            ):
                is_reply_to_bot = True

        if not mentioned and not is_reply_to_bot:
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
# Instagram downloader (using instaloader - better for posts)
# ------------------------------------------------------
def download_instagram(url: str, unique_id: str):
    """Returns list of file paths"""
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
        # Download the post
        L.download_post(post, target=folder)

        # Collect all downloaded media
        for file in os.listdir(folder):
            full = os.path.join(folder, file)
            if file.endswith((".jpg", ".jpeg", ".png", ".webp", ".mp4")):
                paths.append(full)

    except Exception as e:
        print(f"Download post error: {e}")

    return paths


# ------------------------------------------------------
# Text handler
# ------------------------------------------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()

    # Random text → About
    if not text.startswith("http"):
        about_text = (
            "About this Bot:\n\n"
            "Send me any image and I will modify it so it becomes different from the original "
            "while keeping high visual quality. This helps avoid Instagram’s duplicate / "
            "unoriginal content restrictions.\n\n"
            "You can also send any Instagram Post, Reel or Carousel link "
            "and I will download the original high-quality media for you.\n\n"
            "In groups: You must mention me with the photo or link.\n\n"
            "For any help contact: @coolmoco"
        )
        await message.reply_text(about_text)
        return

    if "instagram.com" not in text.lower():
        await message.reply_text("❌ Only Instagram links are supported.")
        return

    # Group check
    if message.chat.type in ["group", "supergroup"]:
        bot_username = (await context.bot.get_me()).username.lower()
        mentioned = f"@{bot_username}" in text.lower()

        is_reply_to_bot = False
        if message.reply_to_message and message.reply_to_message.from_user:
            if (
                message.reply_to_message.from_user.is_bot
                and message.reply_to_message.from_user.username
                and message.reply_to_message.from_user.username.lower() == bot_username
            ):
                is_reply_to_bot = True

        if not mentioned and not is_reply_to_bot:
            return

    clean_url = re.sub(r"[?&](utm_|igshid|stkn|igsh)=[^&]+", "", text)
    clean_url = clean_url.split("?")[0].rstrip("/")

    status_msg = await message.reply_text("⚡ Downloading from Instagram…")

    unique_id = str(int(time.time() * 1000))
    paths = []
    success = False

    try:
        paths = download_instagram(clean_url, unique_id)

        if not paths:
            # Fallback to yt-dlp for reels if instaloader fails
            ydl_opts = {
                "outtmpl": f"ig_{unique_id}.%(ext)s",
                "quiet": True,
                "no_warnings": True,
                "format": "best",
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                },
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
                media = []
                for p in images[:10]:
                    media.append(InputMediaPhoto(open(p, "rb")))
                await message.reply_media_group(media=media)
                success = True

            for v in videos:
                with open(v, "rb") as vid:
                    await message.reply_video(
                        video=vid,
                        caption="✨ Original quality video",
                        supports_streaming=True,
                    )
                success = True

        if success:
            try:
                await status_msg.delete()
            except:
                pass
        else:
            await status_msg.edit_text(
                "❌ Failed to download.\n"
                "Make sure the Instagram link is public."
            )

    except Exception as e:
        print(f"Error: {e}")
        try:
            await status_msg.edit_text(
                "❌ Failed to download.\n"
                "Make sure the Instagram link is public."
            )
        except:
            pass

    finally:
        # Cleanup
        for p in paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except:
                pass
        folder = f"temp_{unique_id}"
        if os.path.exists(folder):
            try:
                import shutil
                shutil.rmtree(folder)
            except:
                pass


# ------------------------------------------------------
# Main
# ------------------------------------------------------
def main():
    keep_alive()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("how", how))

    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot started successfully...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
