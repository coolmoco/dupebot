import os
import io
import random
import time
import re
import subprocess
import shutil
from threading import Thread
from flask import Flask
from dotenv import load_dotenv
from telegram import Update, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
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
        "-crf", "16",
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
# Commands
# ------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Welcome!\n\n"
        "Just send me any image or video and I will give you a modified version.\n"
        "You can also send Instagram / YouTube / TikTok links.\n\n"
        "Commands: /help /about /how\n\n"
        "In groups: mention me with the media or link.\n\n"
        "Contact: @coolmoco"
    )
    await update.message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send photo → unique version\n"
        "Send video → unique version\n"
        "Send YouTube / TikTok / Instagram link → download\n\n"
        "• YouTube Shorts → direct download\n"
        "• Normal YouTube videos → quality select\n\n"
        "In groups mention the bot."
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot modifies photos & videos uniquely.\n"
        "Also downloads from YouTube, TikTok, Instagram.\n\n"
        "Contact: @coolmoco"
    )

async def how(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Photo/Video → I modify them\n"
        "Link → I download them\n"
        "That's it."
    )

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
# YouTube Shorts - Direct download
# ------------------------------------------------------
async def download_youtube_shorts(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    status_msg = await update.message.reply_text("⏳ Downloading YouTube Short...")
    unique_id = str(int(time.time() * 1000))
    output_template = f"shorts_{unique_id}.%(ext)s"

    try:
        ydl_opts = {
            "outtmpl": output_template,
            "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 40,
            "retries": 8,
            "fragment_retries": 8,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            },
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            base = filename.rsplit(".", 1)[0]
            for ext in [".mp4", ".mkv", ".webm"]:
                if os.path.exists(base + ext):
                    filename = base + ext
                    break

        if not os.path.exists(filename):
            await status_msg.edit_text("❌ Download failed.")
            return

        with open(filename, "rb") as video:
            await update.message.reply_video(
                video=video,
                caption="✅ Here’s your YouTube Short",
                supports_streaming=True,
            )

        try:
            await status_msg.delete()
        except:
            pass

    except Exception as e:
        print(f"Shorts error: {e}")
        try:
            await status_msg.edit_text(f"❌ Failed to download Short.\n{str(e)[:100]}")
        except:
            pass
    finally:
        for f in os.listdir("."):
            if f.startswith(f"shorts_{unique_id}"):
                try:
                    os.remove(f)
                except:
                    pass

# ------------------------------------------------------
# YouTube quality buttons (only normal long videos)
# ------------------------------------------------------
async def show_quality_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    context.user_data["yt_url"] = url
    keyboard = [
        [
            InlineKeyboardButton("360p", callback_data="dl_360"),
            InlineKeyboardButton("480p", callback_data="dl_480"),
        ],
        [
            InlineKeyboardButton("720p", callback_data="dl_720"),
            InlineKeyboardButton("1080p", callback_data="dl_1080"),
        ],
        [
            InlineKeyboardButton("Audio Only", callback_data="dl_audio"),
        ]
    ]
    await update.message.reply_text(
        "Select quality:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if not data.startswith("dl_"):
        return

    quality = data.replace("dl_", "")
    url = context.user_data.get("yt_url")
    if not url:
        await query.edit_message_text("❌ Session expired. Send link again.")
        return

    await query.edit_message_text(f"⏳ Downloading {quality}...")
    unique_id = str(int(time.time() * 1000))
    output_template = f"dl_{unique_id}.%(ext)s"

    try:
        ydl_opts = {
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "retries": 8,
            "fragment_retries": 8,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            },
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        }

        if quality == "audio":
            ydl_opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            })
        else:
            height = {"360": 360, "480": 480, "720": 720, "1080": 1080}.get(quality, 720)
            ydl_opts.update({
                "format": f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best",
                "merge_output_format": "mp4",
            })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            if quality == "audio":
                base = filename.rsplit(".", 1)[0]
                filename = base + ".mp3"
            else:
                base = filename.rsplit(".", 1)[0]
                for ext in [".mp4", ".mkv", ".webm"]:
                    if os.path.exists(base + ext):
                        filename = base + ext
                        break

        if not os.path.exists(filename):
            await query.edit_message_text("❌ Download failed.")
            return

        if quality == "audio":
            with open(filename, "rb") as audio:
                await query.message.reply_audio(audio=audio, caption="🎵 Audio ready")
        else:
            with open(filename, "rb") as video:
                await query.message.reply_video(
                    video=video,
                    caption=f"✅ {quality} video ready",
                    supports_streaming=True,
                )
        await query.edit_message_text("✅ Done!")
    except Exception as e:
        print(f"YouTube error: {e}")
        await query.edit_message_text(f"❌ Failed: {str(e)[:100]}")
    finally:
        for f in os.listdir("."):
            if f.startswith(f"dl_{unique_id}"):
                try:
                    os.remove(f)
                except:
                    pass
        context.user_data.pop("yt_url", None)

# ------------------------------------------------------
# TikTok (Video + Photo Slides) with proper cleanup
# ------------------------------------------------------
async def download_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    status_msg = await update.message.reply_text("⏳ Downloading TikTok...")
    unique_id = str(int(time.time() * 1000))
    folder = f"tt_{unique_id}_dir"
    os.makedirs(folder, exist_ok=True)
    paths = []
    opened_files = []

    try:
        # 1. Try yt-dlp (videos)
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

        # 2. Agar video nahi mila to gallery-dl try karo (photo slides)
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

        # 3. Send media
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
                await status_msg.delete()
            except:
                pass
        else:
            await status_msg.edit_text("❌ Failed to download. Make sure the link is public.")

    except Exception as e:
        print(f"TikTok error: {e}")
        try:
            await status_msg.edit_text(f"❌ Failed to download TikTok.\n{str(e)[:120]}")
        except:
            pass
    finally:
        # Pehle files close karo
        for f in opened_files:
            try:
                f.close()
            except:
                pass

        # Strong cleanup
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
# Text handler
# ------------------------------------------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()

    if not text.startswith("http"):
        await message.reply_text(
            "About this Bot:\n\n"
            "• Send any image or video → modified version\n"
            "• Send Instagram / YouTube / TikTok link → download\n\n"
            "In groups: mention me.\n\n"
            "Contact: @coolmoco"
        )
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

    # YouTube
    if "youtube.com" in lower or "youtu.be" in lower:
        if "/shorts/" in lower:
            await download_youtube_shorts(update, context, text)
        else:
            await show_quality_buttons(update, context, text)
        return

    # TikTok
    if "tiktok.com" in lower or "vt.tiktok.com" in lower or "vm.tiktok.com" in lower:
        await download_tiktok(update, context, text)
        return

    # Instagram
    if "instagram.com" in lower:
        clean_url = re.sub(r"[?&](utm_|igshid|stkn|igsh)=[^&]+", "", text)
        clean_url = clean_url.split("?")[0].rstrip("/")
        status_msg = await message.reply_text("⚡ Downloading from Instagram…")
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
                    await status_msg.delete()
                except:
                    pass
            else:
                await status_msg.edit_text("❌ Failed. Make sure link is public.")
        except Exception as e:
            print(f"IG error: {e}")
            try:
                await status_msg.edit_text("❌ Failed to download.")
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

    await message.reply_text("❌ Only Instagram, YouTube and TikTok links supported.")

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
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(quality_callback))
    print("Bot started successfully...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
