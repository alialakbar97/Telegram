import os
import re
import requests
import asyncio
import instaloader
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import shutil

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
    user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )
)

# قفل لتجنب تعارض عدة عمليات Instaloader معاً
INSTALOADER_LOCK = asyncio.Lock()

# تسجيل الدخول ديناميكياً
if IG_USER and IG_PASS:
    try:
        session_file = f"{IG_USER}.session"
        if os.path.exists(session_file):
            L.load_session_from_file(IG_USER, session_file)
            print("✅ تحميل جلسة Instagram ناجح")
        else:
            L.login(IG_USER, IG_PASS)
            L.save_session_to_file(session_file)
            print("✅ تسجيل دخول Instagram ناجح وتم حفظ الجلسة")
    except Exception as e:
        print(f"❌ فشل تسجيل الدخول أو تحميل الجلسة: {e}")
        if "Please re-run Instaloader" in str(e):
            print("⚠️ يُرجى إعادة تشغيل Instaloader مع حساب آخر أو بعد فترة لتجنب الحظر.")
else:
    print("⚠️ IG_USER أو IG_PASS غير موجود. Instaloader سيعمل بدون تسجيل دخول (محدود).")

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
        # تشغيل requests في ثريد منفصل حتى لا يحجب event loop
        response = await asyncio.to_thread(
            requests.post, api_url, data={"url": url}
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data", {}).get("play")
    except Exception as e:
        print(f"❌ خطأ في تحميل تيك توك: {e}")
        return None

# ---------------------- تحميل فيديو فيسبوك ----------------------
async def download_facebook(url: str):
    api = "https://fbdl.app/api/video/details"
    try:
        r = await asyncio.to_thread(
            requests.post, api, json={"url": url}
        )
        r.raise_for_status()
        data = r.json()
        result = data.get("result") or {}
        hd_url = result.get("hd")
        sd_url = result.get("sd")
        return hd_url if hd_url else sd_url
    except Exception as e:
        print(f"❌ خطأ في تحميل فيسبوك: {e}")
        return None

# ---------------------- تحميل منشور إنستغرام ----------------------
async def download_instagram_post_async(url: str):
    shortcode_match = re.search(r'/(reel|p|tv)/([A-Za-z0-9_-]+)', url)
    if not shortcode_match:
        return None, None, "❌ رابط إنستغرام غير صالح."

    shortcode = shortcode_match.group(2)
    target_folder = os.path.join(DOWNLOAD_DIR, shortcode)

    async with INSTALOADER_LOCK:
        def download_post():
            files = []
            try:
                os.makedirs(target_folder, exist_ok=True)
                original_dirname_pattern = L.dirname_pattern
                L.dirname_pattern = target_folder

                post = instaloader.Post.from_shortcode(L.context, shortcode)
                L.download_post(post, shortcode)

                files = [
                    os.path.join(target_folder, f)
                    for f in os.listdir(target_folder)
                    if f.lower().endswith((".mp4", ".jpg", ".jpeg"))
                ]
                files.sort()
                return files, None
            except Exception as e:
                return None, f"❌ خطأ أثناء التحميل: {e}"
            finally:
                # إعادة النمط الأصلي دائماً
                try:
                    L.dirname_pattern = original_dirname_pattern
                except Exception:
                    pass

        files, error = await asyncio.to_thread(download_post)

    return files, target_folder, error

# ---------------------- تحميل ستوريات إنستغرام ----------------------
async def download_instagram_story_async(username: str):
    story_dir = os.path.join(DOWNLOAD_DIR, f"story_{username}")

    async with INSTALOADER_LOCK:
        def download_story():
            media_files = []
            original_dirname_pattern = getattr(L, "dirname_pattern", ".")
            try:
                os.makedirs(story_dir, exist_ok=True)
                L.dirname_pattern = story_dir

                profile = instaloader.Profile.from_username(L.context, username)
                for story in L.get_stories([profile.userid]):
                    for item in story.get_items():
                        L.download_storyitem(item, story_dir)

                media_files = [
                    os.path.join(story_dir, f)
                    for f in os.listdir(story_dir)
                    if f.lower().endswith((".mp4", ".jpg", ".jpeg"))
                ]
                media_files.sort()
                return media_files, None
            except Exception as e:
                return None, f"❌ خطأ أثناء جلب الستوري: {e}"
            finally:
                # إعادة النمط الأصلي دائماً
                try:
                    L.dirname_pattern = original_dirname_pattern
                except Exception:
                    pass

        media_files, error = await asyncio.to_thread(download_story)

    if not media_files and not error:
        return None, story_dir, "❌ لا توجد ستوريات حالياً."

    return media_files, story_dir, error

# ---------------------- معالجة الرسائل ----------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    temp_dir_to_clean = None

    try:
        # ----- تيك توك -----
        if "tiktok.com" in text:
            await update.message.reply_text("⏳ جاري تحميل فيديو تيك توك...")
            v = await download_tiktok(text)
            if v:
                await update.message.reply_video(video=v)
            else:
                await update.message.reply_text(
                    "❌ فشل تحميل تيك توك. قد يكون الرابط غير صالح أو محظوراً."
                )
            return

        # ----- فيسبوك -----
        if "facebook.com" in text or "fb.watch" in text:
            await update.message.reply_text("⏳ جاري تحميل فيديو فيسبوك...")
            v = await download_facebook(text)
            if v:
                await update.message.reply_video(video=v)
            else:
                await update.message.reply_text(
                    "❌ لم يتم العثور على فيديو. قد يكون خاصاً أو الرابط غير صالح."
                )
            return

        # ----- ستوريات إنستغرام -----
        if "instagram.com/stories" in text:
            username_match = re.search(r"stories/([^/]+)", text)
            if not username_match:
                await update.message.reply_text("❌ رابط ستوري غير صالح.")
                return

            username = username_match.group(1)
            msg = await update.message.reply_text(f"⏳ جاري تحميل ستوريات @{username} ...")

            media, temp_dir_to_clean, error = await download_instagram_story_async(username)

            if error:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    text=error,
                )
                return

            if not media:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    text="❌ لا توجد ستوريات متاحة حالياً.",
                )
                return

            for m in media:
                with open(m, "rb") as f:
                    if m.lower().endswith(".mp4"):
                        await context.bot.send_video(chat_id=chat_id, video=f)
                    else:
                        await context.bot.send_photo(chat_id=chat_id, photo=f)

            await context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
            return

        # ----- منشورات إنستغرام -----
        if "instagram.com" in text:
            msg = await update.message.reply_text("⏳ جاري تحميل منشور إنستغرام...")
            media, temp_dir_to_clean, error = await download_instagram_post_async(text)

            if error:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    text=error,
                )
                return

            if media:
                for m in media:
                    with open(m, "rb") as f:
                        if m.lower().endswith(".mp4"):
                            await context.bot.send_video(chat_id=chat_id, video=f)
                        else:
                            await context.bot.send_photo(chat_id=chat_id, photo=f)
            else:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    text="❌ فشل تحميل المنشور أو لم يتم العثور على ملفات.",
                )
                return

            await context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
            return

        # إذا لم يكن الرابط لأي خدمة مدعومة
        await update.message.reply_text("⚠️ أرسل رابط تيك توك / إنستغرام / فيسبوك فقط.")

    except Exception as e:
        print(f"❌ خطأ عام في معالجة الرسالة: {e}")
        await update.message.reply_text("⚠️ حدث خطأ غير متوقع. حاول مرة أخرى.")

    finally:
        # حذف المجلد المؤقت بعد الانتهاء
        if temp_dir_to_clean and os.path.exists(temp_dir_to_clean):
            try:
                shutil.rmtree(temp_dir_to_clean)
                print(f"🗑️ تم حذف المجلد المؤقت: {temp_dir_to_clean}")
            except Exception as e:
                print(f"❌ فشل حذف المجلد المؤقت: {e}")

# ---------------------- تشغيل البوت ----------------------
def main():
    if not BOT_TOKEN:
        print("❌ يجب تعيين BOT_TOKEN في متغيرات البيئة.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("✅ البوت يعمل الآن...")
    try:
        app.run_polling()
    except Exception as e:
        print(f"❌ حدث خطأ أثناء تشغيل البوت: {e}")

if __name__ == "__main__":
    main()