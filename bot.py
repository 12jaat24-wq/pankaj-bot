import os
import json
import random
import logging
import asyncio
import requests
import time
from github import Github
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, MessageHandler, filters, ContextTypes

# --- कॉन्फ़िगरेशन (Render Environment Variables) ---
TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = "12jaat24-wq/pankaj-bot"
DB_FILE = "quiz_database.json"
GITHUB_URL = f"https://raw.githubusercontent.com/{REPO_NAME}/main/{DB_FILE}"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CACHE = {}

def sync_db():
    global DB_CACHE
    try:
        # कैश-बस्टर ताकि हर बार नया डेटा मिले
        r = requests.get(f"{GITHUB_URL}?t={int(time.time())}", timeout=20)
        if r.status_code == 200:
            DB_CACHE = r.json()
            return True
    except: return False
    return False

# --- डेटा अपडेट सिस्टम (Text/File) ---
async def process_and_upload(update, context, json_text):
    try:
        new_data = json.loads(json_text.replace('```json', '').replace('```', '').strip())
        msg = await update.message.reply_text("⚡ **डेटा प्रोसेस हो रहा है...**")
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode())
        db.update(new_data)
        repo.update_file(file.path, "Update 2.0", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
        sync_db()
        await msg.edit_text("✅ **गिटहब अपडेट सफल!** अब /start दबाएँ।")
    except Exception as e:
        await update.message.reply_text(f"❌ **Error:** {str(e)}")

# --- स्टाइलिश रिफ्रेश कमांड ---
async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ **सिस्टम ताज़ा किया जा रहा है...**")
    if sync_db():
        total_topics = len(DB_CACHE.keys())
        total_qs = sum(len(v) for v in DB_CACHE.values())
        res = (
            "╔════════════════════╗\n"
            "   🔄 **सिस्टम रिफ्रेश सफल** ✨  \n"
            "╚════════════════════╝\n"
            f"📂 **कुल विषय:**  `{total_topics}`\n"
            f"📚 **कुल सवाल:**  `{total_qs}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🚀 अब आप अपनी तैयारी शुरू कर सकते हैं!\n"
            "👉 /start दबाएँ।"
        )
        await msg.edit_text(res, parse_mode="Markdown")
    else:
        await msg.edit_text("❌ **रिफ्रेश फेल!** इंटरनेट या गिटहब चेक करें।")

# --- स्टाइलिश डिलीट कमांड ---
async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("💡 `/delete विषय_का_नाम` लिखें।")
    topic = " ".join(context.args)
    msg = await update.message.reply_text(f"🗑️ **'{topic}' को डिलीट कर रहा हूँ...**")
    try:
        g = Github(GITHUB_TOKEN); repo = g.get_repo(REPO_NAME); file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode())
        if topic in db:
            del db[topic]
            repo.update_file(file.path, f"Deleted {topic}", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
            sync_db()
            res = (
                "╔════════════════════╗\n"
                "   🗑️ **डेटा सफलतापूर्वक साफ़** \n"
                "╚════════════════════╝\n"
                f"💥 विषय: `{topic}` अब गिटहब से उड़ गया है।\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔄 नया डेटा देखने के लिए: /refresh\n"
                "🎯 क्विज़ शुरू करने के लिए: /start"
            )
            await msg.edit_text(res, parse_mode="Markdown")
        else: await msg.edit_text("❌ यह विषय लिस्ट में नहीं मिला।")
    except Exception as e: await msg.edit_text(f"❌ गड़बड़: {str(e)}")

# --- क्विज़ लॉजिक ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_CACHE: sync_db()
    if not DB_CACHE: return await update.message.reply_text("❌ डेटाबेस खाली है!")
    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "💎", "🔥", "🌈", "⚡", "🏆"]
    keyboard = [[InlineKeyboardButton(f"{random.choice(icons)} {t}", callback_data=t)] for t in DB_CACHE.keys()]
    welcome = (
        "╔════════════════════╗\n"
        "   ✨ **पंकज क्विज़ पोल 2.0** ✨  \n"
        "╚════════════════════╝\n\n"
        "🚀 **मंज़िल की ओर एक कदम और!**\n"
        "🎯 अपना विषय चुनें और धमाका करें: 👇"
    )
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    topic = query.data
    qs = list(DB_CACHE.get(topic, []))
    random.shuffle(qs)
    context.user_data.update({'qs': qs, 'idx': 0, 'score': 0, 'busy': True, 'topic': topic})
    await query.delete_message()
    await send_q(context, query.message.chat_id)

async def send_q(context, chat_id):
    ud = context.user_data
    idx, qs = ud.get('idx', 0), ud['qs']
    total = len(qs)

    if idx >= total:
        score = ud['score']; per = int((score/total)*100)
        medal = "🏆" if per >= 80 else "🥇" if per >= 60 else "🥈" if per >= 40 else "🥉"
        res = (
            f"╔══════════════════╗\n"
            f"   📊 **रिपोर्ट कार्ड** {medal}  \n"
            f"╚══════════════════╝\n"
            f"📝 विषय: `{ud['topic']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ सही: `{score}` | ❌ गलत: `{total-score}`\n"
            f"📈 कुल सवाल: `{total}`\n"
            f"🏆 स्कोर: `{per}%` \n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✨ /start - नया क्विज़ खेलें"
        )
        await context.bot.send_message(chat_id, res, parse_mode="Markdown")
        ud['busy'] = False; return

    q = qs[idx]
    bar = "🔹" * (idx + 1) + "▫️" * (total - idx - 1)
    
    # सवाल भेजने की कोशिश (Retry logic के साथ)
    try:
        await context.bot.send_poll(
            chat_id=chat_id, 
            question=f"✨ ({idx+1}/{total}) {q['variations'][0]}\n{bar}", 
            options=q['options'], type=Poll.QUIZ, 
            correct_option_id=q['answer'], is_anonymous=False
        )
        ud['idx'] = idx + 1
    except:
        # अगर नेटवर्क एरर आए तो 1 सेकंड बाद दोबारा कोशिश
        await asyncio.sleep(1)
        await send_q(context, chat_id)

async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer; uid = ans.user.id
    ud = context.application.user_data.get(uid)
    if ud and ud.get('busy'):
        current_idx = ud['idx'] - 1
        if ans.option_ids[0] == ud['qs'][current_idx]['answer']: ud['score'] += 1
        
        # 0.5 सेकंड का सुपर फास्ट ऑटो-नेक्स्ट
        await asyncio.sleep(0.5)
        
        class TC: 
            def __init__(self, u, b): self.user_data=u; self.bot=b
        await send_q(TC(ud, context.bot), uid)

def main():
    sync_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(PollAnswerHandler(handle_ans))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), lambda u, c: process_and_upload(u, c, u.message.text)))
    app.add_handler(MessageHandler(filters.Document.ALL, lambda u, c: process_and_upload(u, c, u.message.document.get_file().download_as_bytearray().decode())))

    # वेबहुक गारंटी: रेंडर पर बॉट कभी नहीं अटकेगा और कॉन्फ्लिक्ट नहीं करेगा
    p = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0", port=p, url_path=TOKEN, 
        webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}",
        drop_pending_updates=True # पुराने पेंडिंग मैसेज को साफ़ करने के लिए
    )

if __name__ == '__main__':
    main()
