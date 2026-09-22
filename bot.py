import os
import io
import random
import time
from threading import Thread
from flask import Flask
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables!")

# --- Flask Server setup for Render (24/7 Keep Alive) ---
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Bot is alive and running!"

def run_flask():
    # Render assigns a dynamic port via environment variable PORT
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
# ------------------------------------------------------


def enhance_image(image: Image.Image) -> Image.Image:
    if image.mode != "RGB":
        image = image.convert("RGB")

    width, height = image.size

    crop = random.uniform(0.025, 0.055)
    left = int(width * crop * random.uniform(0.25, 0.85))
    top = int(height * crop * random.uniform(0.25, 0.85))
    right = width - int(width * crop * random.uniform(0.25, 0.85))
    bottom = height - int(height * crop * random.uniform(0.25, 0.85))
    image = image.crop((left, top, right, bottom))

    angle = random.uniform(-1.4, 1.4)
    image = image.rotate(angle, resample=Image.BICUBIC, expand=False)

    image = ImageEnhance.Color(image).enhance(random.uniform(1.08, 1.18))
    image = ImageEnhance.Brightness(image).enhance(random.uniform(1.02, 1.07))
    image = ImageEnhance.Contrast(image).enhance(random.uniform(1.04, 1.12))

    r, g, b = image.split()
    r = r.point(lambda i: min(255, max(0, i + random.randint(-4, 5))))
    g = g.point(lambda i: min(255, max(0, i + random.randint(-3, 4))))
    b = b.point(lambda i: min(255, max(0, i + random.randint(-5, 4))))
    image = Image.merge("RGB", (r, g, b))

    arr = np.array(image).astype(np.int16)
    noise = np.random.randint(-2, 3, arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    image = Image.fromarray(arr)

    image = image.filter(ImageFilter.UnsharpMask(radius=1.3, percent=130, threshold=2))

    scale = random.uniform(1.01, 1.04)
    image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)

    return image


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
            if message.reply_to_message.from_user.is_bot and message.reply_to_message.from_user.username.lower() == bot_username:
                is_reply_to_bot = True

        if not mentioned and not is_reply_to_bot:
            return

    start = time.time()

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
        quality = random.randint(95, 98)
        result.save(output, format="JPEG", quality=quality, optimize=True, progressive=True, subsampling=0)
        output.seek(0)

        elapsed = round(time.time() - start, 2)

        await message.reply_photo(
            photo=output,
            caption=f"✅ Done\n⏱ {elapsed}s | Quality: {quality}"
        )

    except Exception as e:
        print(f"Error: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Just send any image and I’ll return a strong unique version in high quality."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Available Commands:\n\n"
        "/start - Start the bot\n"
        "/help - Show all commands\n"
        "/about - About this bot\n"
        "/how - How this bot works\n\n"
        "Just send any photo to process it.\n"
        "In groups: Send photo with @dupe_img_bot in caption."
    )
    await update.message.reply_text(text)


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "About this Bot:\n\n"
        "Send me any image and I will slightly modify it "
        "to make it unique while keeping high visual quality.\n\n"
        "I change colors, sharpness, crop and small details "
        "so the image becomes different from the original.\n\n"
        "In groups: You must mention me with the image "
        "(@dupe_img_bot) otherwise I will not reply.\n\n"
        "For any help contact: @coolmoco"
    )
    await update.message.reply_text(text)


async def how(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "How it works:\n\n"
        "1. You send me any image\n"
        "2. I process it with multiple small changes\n"
        "3. I return a new version that looks almost the same "
        "but is technically unique\n\n"
        "In groups: Mention me with the photo (@dupe_img_bot)"
    )
    await update.message.reply_text(text)


async def unknown_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    text = (
        "I didn't understand that.\n\n"
        "Available commands:\n"
        "/start\n"
        "/help\n"
        "/about\n"
        "/how\n\n"
        "Or just send me an image to process."
    )
    await update.message.reply_text(text)


def main():
    # Start Flask server in background thread for 24/7 uptime
    keep_alive()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("how", how))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_text))

    print("Final Bot started...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
