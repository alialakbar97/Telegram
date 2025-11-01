import os
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# قراءة توكن البوت بشكل آمن
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ خطأ: لم يتم تعيين متغير البيئة BOT_TOKEN!")

# أمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلًا! أرسل لي رابط فيديو من تيك توك وسأنزله لك بدون علامة مائية 🎥"
    )

# تحميل فيديو تيك توك
async def download_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if "tiktok.com" not in url:
        await update.message.reply_text("⚠️ أرسل رابط صحيح من تيك توك.")
        return

    await update.message.reply_text("⏳ جاري التحميل...")

    try:
        api_url = "https://www.tikwm.com/api/"
        response = requests.post(api_url, data={"url": url})
        data = response.json()

        if data.get("data") and "play" in data["data"]:
            video_url = data["data"]["play"]
            await update.message.reply_video(video_url, caption="✅ تم التنزيل بنجاح بدون علامة مائية!")
        else:
            await update.message.reply_text("❌ تعذر تحميل الفيديو. حاول رابط آخر.")

    except Exception as e:
        print("❌ خطأ:", e)
        await update.message.reply_text("🚫 حدث خطأ أثناء التحميل. تحقق من الرابط أو أعد المحاولة لاحقًا.")

# تشغيل البوت
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # إضافة الأوامر والمعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), download_tiktok))

    print("✅ البوت يعمل الآن وينتظر الروابط...")
    app.run_polling()

if __name__ == "__main__":
    main()