import os
import re
import requests
import asyncio
import instaloader
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ---------------------- إعدادات البوت ----------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
IG_USER = os.environ.get("IG_USER")
IG_PASS = os.environ.get("IG_PASS")

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

# تسجيل الدخول ديناميكياً
if IG_USER and IG_PASS:
    try:
        L.login(IG_USER, IG_PASS)
        print("✅ تسجيل دخول Instagram ناجح")
    except Exception as e:
        print(f"❌ فشل تسجيل الدخول: {e}")
else:
    print("⚠️ IG_USER أو IG_PASS غير موجود")

# ---------------------- أوامر البوت ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 مرحبًا! أرسل رابط:\n"
        "- تيك توك\n"
        "- منشور/ريلز/ستوريات إنستغرام\n"
        "- فيديو فيسبوك\n\n"
        "وسأقوم بتنزيله لك."
    )

# ---------------------- تحميل فيديو تيك توك ----------------------
async def download_tiktok(url: str):
    api_url = "https://www.tikwm.com/api/"
    try:
        response = requests.post(api_url, data={"url": url})
        data = response.json()
        return data.get("data", {}).get("play")
    except:
        return None

# ---------------------- تحميل فيديو فيسبوك ----------------------
async def download_facebook(url: str):
    api = "https://api.y2meta.com/api/v1/facebook"
    try:
        r = requests.post(api, json={"url": url})
        data = r.json()
        return data.get("video", {}).get("url")
    except:
        return None

# ---------------------- تحميل منشور إنستغرام ----------------------
async def download_instagram_post_async(url: str):
    shortcode_match = re.search(r'/(reel|p|tv)/([A-Za-z0-9_-]+)', url)
    if not shortcode_match:
        return None, "❌ رابط إنستغرام غير صالح."

    shortcode = shortcode_match.group(2)
    target_folder = os.path.join(DOWNLOAD_DIR, shortcode)
    os.makedirs(target_folder, exist_ok=True)
    L.dirname_pattern = target_folder

    def download_post():
        try:
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            L.download_post(post, shortcode)
            files = [os.path.join(target_folder, f) for f in os.listdir(target_folder)
                     if f.endswith(('.mp4', '.jpg'))]
            files.sort()
            return files, None
        except Exception as e:
            return None, f"❌ خطأ أثناء التحميل: {e}"

    return await asyncio.to_thread(download_post)

# ---------------------- تحميل ستوريات إنستغرام ----------------------
async def download_instagram_story_async(username: str):
    try:
        profile = instaloader.Profile.from_username(L.context, username)
        story_dir = os.path.join(DOWNLOAD_DIR, f"story_{username}")
        os.makedirs(story_dir, exist_ok=True)

        def download_story():
            media_files = []
            for story in L.get_stories([profile.userid]):
                for item in story.get_items():
                    filename = os.path.join(story_dir, f"{item.mediaid}.mp4" if item.is_video else f"{item.mediaid}.jpg")
                    L.download_storyitem(item, story_dir)
                    media_files.append(filename)
            return media_files

        media_files = await asyncio.to_thread(download_story)

        if not media_files:
            return None, "❌ لا توجد ستوريات حالياً."
        return media_files, None

    except Exception as e:
        return None, f"❌ خطأ أثناء جلب الستوري: {e}"

# ---------------------- معالجة الرسائل ----------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    # ----- تيك توك -----
    if "tiktok.com" in text:
        await update.message.reply_text("⏳ جاري تحميل فيديو تيك توك...")
        v = await download_tiktok(text)
        if v:
            await update.message.reply_video(v)
        else:
            await update.message.reply_text("❌ فشل تحميل تيك توك.")
        return

    # ----- فيسبوك -----
    if "facebook.com" in text or "fb.watch" in text:
        await update.message.reply_text("⏳ جاري تحميل فيديو فيسبوك...")
        v = await download_facebook(text)
        if v:
            await update.message.reply_video(v)
        else:
            await update.message.reply_text("❌ لم يتم العثور على فيديو.")
        return

    # ----- ستوريات إنستغرام -----
    if "instagram.com/stories" in text:
        try:
            username = re.search(r"stories/([^/]+)", text).group(1)
            await update.message.reply_text(f"⏳ جاري تحميل ستوريات @{username} ...")
            media, err = await download_instagram_story_async(username)
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

    # ----- منشورات إنستغرام -----
    if "instagram.com" in text:
        msg = await update.message.reply_text("⏳ جاري تحميل منشور إنستغرام...")
        media, error = await download_instagram_post_async(text)
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
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("✅ البوت يعمل الآن...")
    app.run_polling()

if __name__ == "__main__":
    main()