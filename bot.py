import logging
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import requests

# -----------------------------
# اقرأ التوكن من بيئة Railway
# -----------------------------
BOT_TOKEN = os.environ["BOT_TOKEN"]

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# دالة start
async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔰 أرسل رابط تيك توك لتحميله الآن ✅")

# دالة لاستقبال أي رسالة نصية وتحميل الفيديو
async def download_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    # تحقق انه رابط تيك توك
    if "tiktok.com" not in url:
        await update.message.reply_text("❌ أرسل رابط TikTok صحيح فقط!")
        return

    await update.message.reply_text("⏳ جاري التحميل...")

    try:
        api = f"https://api.tiklydown.me/api/download?url={url}"
        r = requests.get(api).json()

        if r.get("video"):
            video = r["video"]["play"]
            await update.message.reply_video(video)
        else:
            await update.message.reply_text("❌ فشل التحميل، جرّب رابط آخر")

    except Exception as e:
        await update.message.reply_text("⚠ خطأ أثناء التحميل")

# main function
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, download_tiktok))

    app.run_polling()

if __name__ == "__main__":
    main()