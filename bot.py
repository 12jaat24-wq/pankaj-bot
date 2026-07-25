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
        r = requests.get(f"{GITHUB_URL}?t={int(time.time())}", timeout=20)
        if r.status_code == 200:
            DB_CACHE = r.json()
            return True
    except: return False
    return False

# --- स्टाइलिश डेटा सेविंग सिस्टम ---
async def process_and_upload(update, context, json_text):
    try:
        new_data = json.loads(json_text.replace('```json', '').replace('```', '').strip())
        msg = await update.message.reply_text("⚡ **डेटा प्रोसेस हो रहा है...**")
        
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode())
        db.update(new_data)
        repo.update_file(file.path, "AI Update 2.0", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
        sync_db()
        
        success_res = (
            "╔════════════════════╗\n"
            "   🎉 **गिटहब अपडेट सफल** ✨  \n"
            "╚════════════════════╝\n\n"
            "✅ **बधाई हो!** आपका डेटा गिटहब की तिजोरी में सुरक्षित जुड़ चुका है। 🔐\n\n"
            "🚀 **अगला कदम:** \n"
            "🔄 1. पहले /refresh दबाएँ (डेटा लोड करने के लिए)\n"
            "🎯 2. फिर /start दबाएँ (क्विज़ खेलने के लिए)\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        await msg.edit_text(success_res, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ **Error:** {str(e)}")

# --- /refresh कमांड (विस्तृत और रंगीन जानकारी) ---
async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ **गिटहब से जानकारी निकाल रहा हूँ...**")
    if sync_db():
        total_topics = len(DB_CACHE.keys())
        total_qs = sum(len(v) for v in DB_CACHE.values())
        
        # हर टॉपिक का विवरण तैयार करना
        detail_list = ""
        icons = ["💎", "🔥", "🌈", "⚡", "🔮", "🔅", "⭐"]
        for topic, questions in DB_CACHE.items():
            detail_list += f"{random.choice(icons)} `{topic}`: **{len(questions)}** सवाल\n"

        res = (
            "╔════════════════════╗\n"
            "   🔄 **सिस्टम रिफ्रेश सफल** 🔄  \n"
            "╚════════════════════╝\n\n"
            "📊 **आपकी लाइब्रेरी का विवरण:**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{detail_list}"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📂 **कुल विषय:**  `{total_topics}`\n"
            f"📚 **कुल सवाल:**  `{total_qs}`\n\n"
            "👉 अब /start दबाकर क्विज़ शुरू करें! 🔥"
        )
        await msg.edit_text(res, parse_mode="Markdown")
    else:
        await msg.edit_text("❌ **रिफ्रेश फेल!** इंटरनेट या गिटहब चेक करें।")

# --- स्टाइलिश डिलीट कमांड ---
async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("💡 `/delete TopicName` लिखें।")
    topic = " ".join(context.args)
    msg = await update.message.reply_text(f"🗑️ **'{topic}' को हटा रहा हूँ...**")
    try:
        g = Github(GITHUB_TOKEN); repo = g.get_repo(REPO_NAME); file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode())
        if topic in db:
            del db[topic]
            repo.update_file(file.path, f"Deleted {topic}", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
            sync_db()
            res = (
                "╔════════════════════╗\n"
                "   🗑️ **टॉपिक डिलीट सफल** \n"
                "╚════════════════════╝\n"
                f"💥 विषय: `{topic}` अब पूरी तरह हट गया है।\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "👉 नया स्टेटस देखने के लिए: /refresh"
            )
            await msg.edit_text(res, parse_mode="Markdown")
        else: await msg.edit_text("❌ यह विषय नहीं मिला।")
    except Exception as e: await msg.edit_text(f"❌ गड़बड़: {str(e)}")

# --- क्विज़ लॉजिक ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_CACHE: sync_db()
    if not DB_CACHE: return await update.message.reply_text("❌ डेटाबेस खाली है!")
    
    keyboard = [[InlineKeyboardButton(f"📖 {t}", callback_data=t)] for t in DB_CACHE.keys()]
    welcome = (
        "╔════════════════════╗\n"
        "   ✨ **पंकज क्विज़ पोल 2.0** ✨  \n"
        "╚════════════════════╝\n\n"
        "🚀 **मंज़िल उन्हीं को मिलती है, जिनके सपनों में जान होती है!**\n\n"
        "🎯 **विषय चुनकर अपनी तैयारी शुरू करें:** 👇"
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
            f"   📊 **आपका रिपोर्ट कार्ड** {medal}  \n"
            f"╚══════════════════╝\n"
            f"📝 विषय: `{ud['topic']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ सही: `{score}` | ❌ गलत: `{total-score}`\n"
            f"📈 कुल सवाल: `{total}`\n"
            f"🏆 स्कोर: `{per}%` \n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✨ तैयारी जारी रखें! /start"
        )
        await context.bot.send_message(chat_id, res, parse_mode="Markdown")
        ud['busy'] = False; return

    q = qs[idx]
    bar = "🔹" * (idx + 1) + "▫️" * (total - idx - 1)
    
    try:
        await context.bot.send_poll(
            chat_id=chat_id, 
            question=f"✨ ({idx+1}/{total}) {q['variations'][0]}\n{bar}", 
            options=q['options'], type=Poll.QUIZ, 
            correct_option_id=q['answer'], is_anonymous=False
        )
        ud['idx'] = idx + 1
    except:
        await asyncio.sleep(1); await send_q(context, chat_id)

async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer; uid = ans.user.id
    ud = context.application.user_data.get(uid)
    if ud and ud.get('busy'):
        current_idx = ud['idx'] - 1
        if ans.option_ids[0] == ud['qs'][current_idx]['answer']: ud['score'] += 1
        await asyncio.sleep(0.5) # 0.5 सेकंड का सुपर फास्ट ऑटो-नेक्स्ट
        
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
    
    # टेक्स्ट और फाइल दोनों के लिए ऑटो-अपलोड
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), lambda u, c: process_and_upload(u, c, u.message.text)))
    app.add_handler(MessageHandler(filters.Document.ALL, lambda u, c: process_and_upload(u, c, u.message.document.get_file().download_as_bytearray().decode())))

    # वेबहुक गारंटी (बिना अटके चलेगा)
    p = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0", port=p, url_path=TOKEN, 
        webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}",
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
