import os
import re
import requests
import asyncio
import instaloader
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import shutil # 💡 جديد: لإزالة المجلدات بالكامل

# ---------------------- إعدادات البوت ----------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
IG_USER = os.environ.get("IG_USER")
IG_PASS = os.environ.get("IG_PASS")

DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# ---------------------- إعداد Instaloader ----------------------
# 💡 تصحيح الخطأ 1: إضافة user_agent لتجنب حجب Instaloader من قبل إنستغرام
L = instaloader.Instaloader(
    download_pictures=True,
    download_videos=True,
    download_comments=False,
    save_metadata=False,
    quiet=True,
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

# تسجيل الدخول ديناميكياً
if IG_USER and IG_PASS:
    try:
        # 💡 تصحيح الخطأ 2: استخدام load_session وحفظه لتجنب تكرار تسجيل الدخول
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
        # 💡 تصحيح الخطأ 3: يجب معالجة مشكلة "Too Many Requests" (HTTP 429)
        if "Please re-run Instaloader" in str(e):
             print("⚠️ يُرجى إعادة تشغيل Instaloader مع حساب آخر أو بعد فترة لتجنب الحظر.")
else:
    print("⚠️ IG_USER أو IG_PASS غير موجود. Instaloader سيعمل بدون تسجيل دخول.")

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
        response.raise_for_status() # 💡 إضافة: للتحقق من أخطاء HTTP
        data = response.json()
        # 💡 ملاحظة: 'play' يحتوي على رابط بدون علامة مائية، وهو جيد.
        return data.get("data", {}).get("play")
    except Exception as e:
        print(f"❌ خطأ في تحميل تيك توك: {e}")
        return None

# ---------------------- تحميل فيديو فيسبوك ----------------------
async def download_facebook(url: str):
    # 💡 تصحيح الخطأ 4: API المستخدم لم يعد يعمل غالباً، وتم استبداله بآخر شائع
    api = "https://fbdl.app/api/video/details"
    try:
        r = requests.post(api, json={"url": url})
        r.raise_for_status() # 💡 إضافة: للتحقق من أخطاء HTTP
        data = r.json()
        # 💡 استخدام الجودة الأعلى (HD) إذا كانت متوفرة، وإلا فالجودة القياسية (SD)
        hd_url = data.get("result", {}).get("hd")
        sd_url = data.get("result", {}).get("sd")
        return hd_url if hd_url else sd_url
    except Exception as e:
        print(f"❌ خطأ في تحميل فيسبوك: {e}")
        return None

# ---------------------- تحميل منشور إنستغرام ----------------------
async def download_instagram_post_async(url: str):
    shortcode_match = re.search(r'/(reel|p|tv)/([A-Za-z0-9_-]+)', url)
    if not shortcode_match:
        return None, None, "❌ رابط إنستغرام غير صالح." # 💡 إضافة: لإرجاع الملفات

    shortcode = shortcode_match.group(2)
    target_folder = os.path.join(DOWNLOAD_DIR, shortcode)
    # 💡 Instaloader يتطلب مجلدًا فريدًا في كل مرة، لذا يجب إزالته في النهاية

    def download_post():
        files = []
        try:
            os.makedirs(target_folder, exist_ok=True)
            L.dirname_pattern = target_folder
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            L.download_post(post, shortcode)
            files = [os.path.join(target_folder, f) for f in os.listdir(target_folder)
                     if f.endswith(('.mp4', '.jpg'))]
            files.sort()
            return files, None
        except Exception as e:
            return None, f"❌ خطأ أثناء التحميل: {e}"
        # 💡 تصحيح الخطأ 5: يجب أن يتم حذف المجلد بعد إرسال الملفات
        finally:
            return files, None # سيتم التعامل مع الحذف في handle_message

    files, error = await asyncio.to_thread(download_post)
    return files, target_folder, error # 💡 إرجاع مسار المجلد للحذف

# ---------------------- تحميل ستوريات إنستغرام ----------------------
async def download_instagram_story_async(username: str):
    story_dir = os.path.join(DOWNLOAD_DIR, f"story_{username}")

    def download_story():
        media_files = []
        try:
            os.makedirs(story_dir, exist_ok=True)
            # 💡 تصحيح: يجب إيقاف تشغيل نمط dir_pattern مؤقتًا
            original_dirname_pattern = L.dirname_pattern
            L.dirname_pattern = story_dir

            profile = instaloader.Profile.from_username(L.context, username)
            for story in L.get_stories([profile.userid]):
                for item in story.get_items():
                    # 💡 Instaloader يقوم بتحديد اسم الملف تلقائيًا في download_storyitem
                    L.download_storyitem(item, story_dir)
            
            # 💡 جمع الملفات التي تم تنزيلها
            media_files = [os.path.join(story_dir, f) for f in os.listdir(story_dir)
                     if f.endswith(('.mp4', '.jpg'))]
            media_files.sort()
            
            L.dirname_pattern = original_dirname_pattern # إرجاع النمط الأصلي
            return media_files, None
        except Exception as e:
            return None, f"❌ خطأ أثناء جلب الستوري: {e}"
        finally:
            return media_files, None # سيتم التعامل مع الحذف في handle_message

    media_files, error = await asyncio.to_thread(download_story)
    
    if not media_files and not error:
        return None, story_dir, "❌ لا توجد ستوريات حالياً."

    return media_files, story_dir, error # 💡 إرجاع مسار المجلد للحذف

# ---------------------- معالجة الرسائل ----------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    temp_dir_to_clean = None

    try:
        # ----- تيك توك -----
        if "tiktok.com" in text:
            await update.message.reply_text("⏳ جاري تحميل فيديو تيك توك...")
            v = await download_tiktok(text)
            if v:
                await update.message.reply_video(v)
            else:
                await update.message.reply_text("❌ فشل تحميل تيك توك. قد يكون الرابط غير صالح أو محظوراً.")
            return

        # ----- فيسبوك -----
        if "facebook.com" in text or "fb.watch" in text:
            await update.message.reply_text("⏳ جاري تحميل فيديو فيسبوك...")
            v = await download_facebook(text)
            if v:
                await update.message.reply_video(v)
            else:
                await update.message.reply_text("❌ لم يتم العثور على فيديو. قد يكون خاصاً أو الرابط غير صالح.")
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
                await context.bot.edit_message_text(chat_id, msg.message_id, text=error)
                return

            for m in media:
                with open(m, "rb") as f:
                    if m.endswith(".mp4"):
                        await context.bot.send_video(chat_id, f)
                    else:
                        await context.bot.send_photo(chat_id, f)
            await context.bot.delete_message(chat_id, msg.message_id)
            return

        # ----- منشورات إنستغرام -----
        if "instagram.com" in text:
            msg = await update.message.reply_text("⏳ جاري تحميل منشور إنستغرام...")
            media, temp_dir_to_clean, error = await download_instagram_post_async(text)

            if error:
                await context.bot.edit_message_text(chat_id, msg.message_id, text=error)
                return
            
            if media:
                for m in media:
                    with open(m, "rb") as f:
                        if m.endswith('.mp4'):
                            await context.bot.send_video(chat_id, f)
                        else:
                            await context.bot.send_photo(chat_id, f)
            else:
                await context.bot.edit_message_text(chat_id, msg.message_id, text="❌ فشل تحميل المنشور أو لم يتم العثور على ملفات.")
                return
            
            await context.bot.delete_message(chat_id, msg.message_id)
            return

        await update.message.reply_text("⚠️ أرسل رابط تيك توك / إنستغرام / فيسبوك فقط.")

    except Exception as e:
        print(f"❌ خطأ عام في معالجة الرسالة: {e}")
        await update.message.reply_text("⚠️ حدث خطأ غير متوقع. حاول مرة أخرى.")

    finally:
        # 💡 تصحيح الخطأ 5: التأكد من حذف المجلد المؤقت بعد إرسال الملفات
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

