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
IG_USER = os.environ.get("IG_USER")  # 🆕 اسم مستخدم انستغرام
IG_PASS = os.environ.get("IG_PASS")  # 🆕 كلمة المرور

if not BOT_TOKEN:
    raise ValueError("❌ خطأ: لم يتم تعيين متغير البيئة BOT_TOKEN!")

DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# ---------------------- إعداد Instaloader ----------------------
L = instaloader.Instaloader(
    download_pictures=True,
    download_videos=True,
    download_comments=False,
    save_metadata=False,
    quiet=True,
    dirname_pattern=DOWNLOAD_DIR + "/{target}"
)

# 🆕 تسجيل الدخول لتنزيل الستوري
if IG_USER and IG_PASS:
    try:
        L.login(IG_USER, IG_PASS)
        print("✅ تم تسجيل الدخول إلى إنستغرام بنجاح.")
    except Exception as e:
        print(f"❌ فشل تسجيل الدخول: {e}")

# ---------------------- أمر البدء ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلًا! أرسل رابط فيديو تيك توك، أو رابط منشور/ريلز/ستوريات إنستغرام.\n\n"
        "🆕 **تم إضافة دعم تنزيل ستوريات إنستغرام أيضًا!**",
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

# ---------------------- تحميل منشور إنستغرام ----------------------
async def download_instagram_post(url: str):
    shortcode_match = re.search(r'/(p|reel|tv)/([a-zA-Z0-9_-]+)', url)
    if not shortcode_match:
        return None, "❌ لم يتم العثور على رمز المشاركة في الرابط."
    
    shortcode = shortcode_match.group(2)
    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        L.dirname_pattern = DOWNLOAD_DIR + f"/{shortcode}"
        L.download_post(post, shortcode)

        post_dir = os.path.join(DOWNLOAD_DIR, shortcode)
        files = os.listdir(post_dir)

        media_files = []
        for f in files:
            if f.endswith(('.mp4', '.jpg', '.png')):
                media_files.append(os.path.join(post_dir, f))

        if not media_files:
            return None, "❌ لم يتم العثور على ملفات الوسائط."

        media_files.sort()
        return media_files, None

    except Exception as e:
        return None, f"❌ حدث خطأ أثناء التحميل: {e}"

# ---------------------- 🆕 تحميل ستوريات إنستغرام ----------------------
async def download_instagram_story(username: str):
    try:
        profile = instaloader.Profile.from_username(L.context, username)

        # مجلد التخزين
        story_dir = os.path.join(DOWNLOAD_DIR, f"stories_{username}")
        if not os.path.exists(story_dir):
            os.makedirs(story_dir)

        media_files = []

        for story in L.get_stories(userids=[profile.userid]):
            for item in story.get_items():
                filename = os.path.join(story_dir, f"{item.mediaid}.mp4" if item.is_video else f"{item.mediaid}.jpg")
                L.download_storyitem(item, story_dir)
                media_files.append(filename)

        if not media_files:
            return None, "❌ لا توجد ستوريات لهذا الحساب الآن."

        return media_files, None

    except Exception as e:
        return None, f"❌ خطأ أثناء جلب الستوري: {e}"

# ---------------------- معالجة الرسائل ----------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    # ---------- تيك توك ----------
    if "tiktok.com" in text:
        await update.message.reply_text("⏳ جاري تحميل فيديو تيك توك...")
        url = await download_tiktok(text)
        if url:
            await update.message.reply_video(url)
        else:
            await update.message.reply_text("❌ تعذر التحميل.")
        return

    # ---------- ستوريات إنستغرام ----------
    if "instagram.com/stories/" in text:
        try:
            username = re.search(r"instagram.com/stories/([^/]+)", text).group(1)
            await update.message.reply_text(f"⏳ جاري تحميل ستوريات @{username} ...")

            media_files, error = await download_instagram_story(username)
            if error:
                await update.message.reply_text(error)
                return

            for m in media_files:
                with open(m, "rb") as f:
                    if m.endswith(".mp4"):
                        await context.bot.send_video(chat_id, f)
                    else:
                        await context.bot.send_photo(chat_id, f)

        except:
            await update.message.reply_text("❌ رابط ستوري غير صالح.")
        return

    # ---------- منشورات إنستغرام ----------
    if "instagram.com" in text:
        msg = await update.message.reply_text("⏳ جاري تحميل منشور إنستغرام...")
        media_files, error = await download_instagram_post(text)

        if error:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=error)
            return

        for m in media_files:
            with open(m, 'rb') as f:
                if m.endswith('.mp4'):
                    await context.bot.send_video(chat_id, f)
                else:
                    await context.bot.send_photo(chat_id, f)

        await context.bot.delete_message(chat_id, msg.message_id)
        return

    await update.message.reply_text("⚠️ أرسل رابط إنستغرام أو تيك توك فقط.")

# ---------------------- تشغيل البوت ----------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("✅ البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()