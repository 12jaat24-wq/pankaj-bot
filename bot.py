import os
import json
import random
import logging
import requests
import time
import asyncio
from github import Github
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, MessageHandler, filters, ContextTypes

# --- रेंडर की सेटिंग्स से जानकारी उठाना ---
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
        r = requests.get(f"{GITHUB_URL}?cb={int(time.time())}", timeout=20)
        if r.status_code == 200:
            DB_CACHE = r.json()
            return True
    except: return False

# --- टॉपिक जोड़ने का फंक्शन ---
async def handle_json_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "variations" not in text: return 

    msg = await update.message.reply_text("⏳ **डेटा मिल गया! गिटहब की तिजोरी में सुरक्षित रख रहा हूँ...** 🔐")
    try:
        new_data = json.loads(text.replace('```json', '').replace('```', '').strip())
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        file = repo.get_contents(DB_FILE)
        current_db = json.loads(file.decoded_content.decode())
        current_db.update(new_data)
        repo.update_file(file.path, "Added topic via Bot", json.dumps(current_db, indent=4, ensure_ascii=False), file.sha)
        sync_db()
        await msg.edit_text("✅ **बधाई हो! नया टॉपिक जुड़ गया है।**\n\nअब /start दबाकर अपना जादू देखें! ✨")
    except Exception as e:
        await msg.edit_text(f"❌ **गड़बड़:** {str(e)}")

# --- टॉपिक डिलीट करना ---
async def delete_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("💡 **तरीका:** `/delete Topic_Name` लिखें।")
    
    topic = " ".join(context.args)
    msg = await update.message.reply_text(f"🗑️ **'{topic}' को जड़ से मिटा रहा हूँ...**")
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode())
        if topic in db:
            del db[topic]
            repo.update_file(file.path, f"Deleted {topic}", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
            sync_db()
            await msg.edit_text(f"💥 **उड़ गया!** '{topic}' अब इतिहास बन चुका है।")
        else:
            await msg.edit_text("❌ यह टॉपिक मुझे कहीं नहीं मिला।")
    except Exception as e:
        await msg.edit_text(f"❌ गड़बड़: {str(e)}")

# --- रंगीन स्टार्ट मैसेज ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sync_db()
    if not DB_CACHE: return await update.message.reply_text("❌ **डेटाबेस खाली है!**")
    
    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "💎", "🔥", "🌈", "⚡"]
    keyboard = [[InlineKeyboardButton(f"{random.choice(icons)} {t}", callback_data=t)] for t in DB_CACHE.keys()]
    
    welcome_text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✨ **पंकज क्विज़ बॉट में आपका स्वागत है!** ✨\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎯 **नीचे दिए गए बटन से अपना विषय चुनें और धमाका शुरू करें!** 👇"
    )
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- क्विज़ शुरू करना ---
async def handle_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = query.data
    qs = list(DB_CACHE.get(topic, []))
    random.shuffle(qs)
    context.user_data.update({'qs': qs, 'idx': 0, 'score': 0, 'busy': True, 'topic': topic})
    await query.delete_message()
    await send_q(context, query.message.chat_id)

# --- सवाल भेजना (रंगीन प्रोग्रेस बार के साथ) ---
async def send_q(context, chat_id):
    ud = context.user_data
    idx = ud.get('idx', 0)
    qs = ud['qs']
    total = len(qs)

    if idx >= total:
        score = ud['score']
        msg = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🎊 **रिवीजन संपन्न हुआ!** 🎊\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 **विषय:** `{ud['topic']}`\n"
            f"✅ **सही उत्तर:** `{score}`\n"
            f"❌ **गलत उत्तर:** `{total - score}`\n"
            f"🏆 **स्कोर:** `{int((score/total)*100)}%` \n\n"
            "नया टॉपिक चुनने के लिए /start दबाएँ। 🔥"
        )
        await context.bot.send_message(chat_id, msg, parse_mode="Markdown")
        ud['busy'] = False
        return

    q = qs[idx]
    # रंगीन प्रोग्रेस बार बनाना
    progress = "🔹" * (idx + 1) + "▫️" * (total - idx - 1)
    
    try:
        await context.bot.send_poll(
            chat_id=chat_id,
            question=f"✨ ({idx+1}/{total}) {q['variations'][0]}\n{progress}",
            options=q['options'],
            type=Poll.QUIZ,
            correct_option_id=q['answer'],
            is_anonymous=False,
            explanation="मेहनत का फल मीठा होता है! 📚✨"
        )
        ud['idx'] = idx + 1
    except Exception as e:
        logger.error(f"Poll Error: {e}")

# --- ऑटो-नेक्स्ट फंक्शन (टिक करते ही अगला सवाल) ---
async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    user_id = ans.user.id
    # यहाँ Bot-level user_data का इस्तेमाल होगा
    ud = context.application.user_data.get(user_id)
    
    if ud and ud.get('busy'):
        idx = ud['idx'] - 1
        if ans.option_ids[0] == ud['qs'][idx]['answer']:
            ud['score'] += 1
        
        # 1 सेकंड का इंतज़ार ताकि छात्र सही/गलत देख सके, फिर अगला सवाल
        await asyncio.sleep(0.8)
        await send_q(context, user_id)

def main():
    sync_db()
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("delete", delete_topic))
    app.add_handler(CallbackQueryHandler(handle_topic))
    app.add_handler(PollAnswerHandler(handle_ans))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_json_input))

    port = int(os.environ.get("PORT", 10000))
    # वेबहुक सेटअप - यह पक्का करता है कि बॉट कभी न अटके
    app.run_webhook(
        listen="0.0.0.0", 
        port=port, 
        url_path=TOKEN, 
        webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}"
    )

if __name__ == '__main__':
    main()
