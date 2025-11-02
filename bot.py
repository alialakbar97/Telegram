import os
import re
import requests
import instaloader
from telegram import Update, constants
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------------- إعدادات البوت ----------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ خطأ: لم يتم تعيين متغير البيئة BOT_TOKEN!")

DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# ---------------------- إعداد Instaloader ----------------------
L = instaloader.Instaloader(
    download_pictures=True,   # ✅ السماح بتنزيل الصور
    download_videos=True,     # ✅ السماح بتنزيل الفيديوهات
    download_comments=False,
    save_metadata=False,
    quiet=True,
    dirname_pattern=DOWNLOAD_DIR + "/{shortcode}"
)

# ---------------------- أوامر البوت ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلًا! أرسل لي رابط فيديو من تيك توك أو منشور/ريلز من إنستغرام وسأقوم بتنزيله لك.",
        parse_mode=constants.ParseMode.MARKDOWN
    )

# ---------------------- تحميل فيديو تيك توك ----------------------
async def download_tiktok(url: str):
    api_url = "https://www.tikwm.com/api/"
    try:
        response = requests.post(api_url, data={"url": url})
        data = response.json()
        if data.get("data") and "play" in data["data"]:
            return data["data"]["play"]
    except Exception:
        return None
    return None

# ---------------------- تحميل منشور إنستغرام (فيديو أو صورة) ----------------------
async def download_instagram(url: str):
    shortcode_match = re.search(r'/(p|reel|tv)/([a-zA-Z0-9_-]+)', url)
    if not shortcode_match:
        return None, "❌ لم يتم العثور على رمز المشاركة في الرابط."
    
    shortcode = shortcode_match.group(2)
    try:
        L.post_metadata_txt_pattern = ''  # لا ننشئ ملفات metadata
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        L.download_post(post, shortcode)
        
        post_dir = os.path.join(DOWNLOAD_DIR, shortcode)
        files = os.listdir(post_dir)
        media_files = [os.path.join(post_dir, f) for f in files if f.endswith(('.mp4', '.jpg', '.png'))]
        
        if not media_files:
            return None, "❌ لم يتم العثور على ملفات وسائط صالحة في المنشور."
        
        return media_files, None

    except instaloader.exceptions.PostException:
        return None, "❌ عذراً، هذا المنشور غير موجود أو خاص."
    except Exception as e:
        return None, f"❌ حدث خطأ غير متوقع: {e}"

# ---------------------- معالجة الرسائل ----------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.effective_chat.id

    if "tiktok.com" in url:
        await update.message.reply_text("⏳ جاري تحميل فيديو تيك توك...")
        video_url = await download_tiktok(url)
        if video_url:
            await update.message.reply_video(video_url, caption="✅ تم التنزيل بنجاح بدون علامة مائية!")
        else:
            await update.message.reply_text("❌ تعذر تحميل الفيديو من تيك توك. حاول رابط آخر.")

    elif "instagram.com" in url:
        message = await update.message.reply_text("⏳ جاري محاولة تحميل الوسائط من إنستغرام...")
        media_files, error = await download_instagram(url)
        if media_files:
            for media_path in media_files:
                with open(media_path, 'rb') as f:
                    if media_path.endswith('.mp4'):
                        await context.bot.send_video(chat_id=chat_id, video=f)
                    else:
                        await context.bot.send_photo(chat_id=chat_id, photo=f)
            # تنظيف الملفات
            post_dir = os.path.dirname(media_files[0])
            for f in os.listdir(post_dir):
                os.remove(os.path.join(post_dir, f))
            os.rmdir(post_dir)
            await context.bot.delete_message(chat_id=chat_id, message_id=message.message_id)
        else:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message.message_id, text=error)

    else:
        await update.message.reply_text("⚠️ أرسل رابط تيك توك أو إنستغرام صالح فقط.")

# ---------------------- تشغيل البوت ----------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("✅ البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()