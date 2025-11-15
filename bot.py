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
)

# 🟢 تحميل الجلسة بدلاً من كلمة المرور
try:
    L.load_session_from_file("session-instagram")
    print("✅ تم تحميل جلسة انستغرام بنجاح.")
except Exception as e:
    print(f"❌ لم يتم العثور على جلسة: {e}")

# ---------------------- TikTok ----------------------
async def download_tiktok(url: str):
    api_url = "https://www.tikwm.com/api/"
    try:
        response = requests.post(api_url, data={"url": url})
        data = response.json()
        return data.get("data", {}).get("play")
    except:
        return None

# ---------------------- Facebook ----------------------
async def download_facebook(url: str):
    api = "https://api.y2meta.com/api/v1/facebook"
    try:
        r = requests.post(api, json={"url": url})
        data = r.json()

        if "video" in data:
            return data["video"]["url"]
    except:
        return None
    return None

# ---------------------- Instagram Post ----------------------
async def download_instagram_post(url: str):
    shortcode_match = re.search(r'/(reel|p|tv)/([A-Za-z0-9_-]+)', url)
    if not shortcode_match:
        return None, "❌ رابط إنستغرام غير صالح."

    shortcode = shortcode_match.group(2)

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)

        target_folder = os.path.join(DOWNLOAD_DIR, shortcode)
        if not os.path.exists(target_folder):
            os.makedirs(target_folder)

        L.dirname_pattern = target_folder
        L.download_post(post, shortcode)

        files = os.listdir(target_folder)
        media = []

        for f in files:
            path = os.path.join(target_folder, f)

            if f.endswith(".mp4"):            # فيديو فقط
                media.append(path)
            elif f.endswith(".jpg") and "UTC" in f:  # صور حقيقية فقط
                media.append(path)

        media.sort()
        return media, None

    except Exception as e:
        return None, f"❌ خطأ: {e}"

# ---------------------- Instagram Stories ----------------------
async def download_instagram_story(username: str):
    try:
        profile = instaloader.Profile.from_username(L.context, username)

        story_dir = os.path.join(DOWNLOAD_DIR, f"story_{username}")
        if not os.path.exists(story_dir):
            os.makedirs(story_dir)

        media_files = []

        for story in L.get_stories([profile.userid]):
            for item in story.get_items():
                filename = os.path.join(story_dir, f"{item.mediaid}.mp4" if item.is_video else f"{item.mediaid}.jpg")
                instaloader Story item saved in folder
                L.download_storyitem(item, story_dir)
                media_files.append(filename)

        if not media_files:
            return None, "❌ لا توجد ستوريات حالياً."

        return media_files, None

    except Exception as e:
        return None, f"❌ خطأ أثناء جلب الستوري: {e}"

# ---------------------- معالجة الرسائل ----------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    # ----- TikTok -----
    if "tiktok.com" in text:
        await update.message.reply_text("⏳ جاري التحميل...")
        v = await download_tiktok(text)
        if v:
            await update.message.reply_video(v)
        else:
            await update.message.reply_text("❌ فشل تحميل تيك توك.")
        return

    # ----- Facebook -----
    if "facebook.com" in text or "fb.watch" in text:
        await update.message.reply_text("⏳ جاري تحميل فيديو فيسبوك...")
        v = await download_facebook(text)
        if v:
            await update.message.reply_video(v)
        else:
            await update.message.reply_text("❌ لم يتم العثور على فيديو.")
        return

    # ----- Instagram Stories -----
    if "instagram.com/stories" in text:
        try:
            username = re.search(r"stories/([^/]+)", text).group(1)
            await update.message.reply_text(f"⏳ جاري تحميل ستوريات @{username} ...")

            media, err = await download_instagram_story(username)
            if err:
                await update.message.reply_text(err)
                return

            for m in media:
                with open(m, "rb") as f:
                    if m.endswith(".mp4"):
                        await context.bot.send_video(chat_id, f)
                    else:
                        await context.bot.send_photo(chat_id, f)
        except:
            await update.message.reply_text("❌ رابط ستوري غير صالح.")
        return

    # ----- Instagram Posts -----
    if "instagram.com" in text:
        msg = await update.message.reply_text("⏳ جاري التحميل...")

        media, error = await download_instagram_post(text)
        if error:
            await context.bot.edit_message_text(chat_id, msg.message_id, text=error)
            return

        for m in media:
            with open(m, "rb") as f:
                if m.endswith('.mp4'):
                    await context.bot.send_video(chat_id, f)
                else:
                    await context.bot.send_photo(chat_id, f)

        await context.bot.delete_message(chat_id, msg.message_id)
        return

    await update.message.reply_text("⚠️ أرسل رابط تيك توك / إنستغرام / فيسبوك فقط.")

# ---------------------- تشغيل البوت ----------------------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u,c: u.message.reply_text("مرحباً 👋")))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("✅ البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()