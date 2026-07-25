import os
import json
import random
import logging
import requests
import time
from github import Github
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, MessageHandler, filters, ContextTypes

# --- सिर्फ ये 3 चीज़ें भरें ---
TOKEN = "7908449655:AAFU5S4qmv223fQ0ffK6g80acVxGX3SpO7A"
# अब टोकन सीधे कोड में नहीं होगा
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

# --- यह फंक्शन सीधे JSON को GitHub पर चढ़ाएगा ---
async def handle_json_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        # चेक करना कि क्या यह सही JSON है
        new_data = json.loads(text.replace('```json', '').replace('```', '').strip())
        
        msg = await update.message.reply_text("⏳ JSON मिल गया है! गिटहब अपडेट कर रहा हूँ...")

        # GitHub अपडेट
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        file = repo.get_contents(DB_FILE)
        current_db = json.loads(file.decoded_content.decode())
        current_db.update(new_data)
        repo.update_file(file.path, "Manual JSON Update", json.dumps(current_db, indent=4, ensure_ascii=False), file.sha)

        sync_db()
        await msg.edit_text("✅ सफलता! बिना किसी API के नया टॉपिक जुड़ गया है। /start दबाएँ।")
    except Exception as e:
        await update.message.reply_text(f"❌ गड़बड़: यह सही JSON नहीं है। कृपया जेमिनी वेब से मिला कोड ही भेजें।\nError: {str(e)}")

# --- बॉट लॉजिक ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sync_db()
    if not DB_CACHE: return await update.message.reply_text("❌ डेटाबेस खाली है।")
    keyboard = [[InlineKeyboardButton(t, callback_data=t)] for t in DB_CACHE.keys()]
    await update.message.reply_text("🎯 **विषय चुनें:**", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = query.data
    qs = list(DB_CACHE.get(topic, []))
    random.shuffle(qs)
    context.user_data.update({'qs': qs, 'idx': 0, 'score': 0, 'busy': True})
    await query.delete_message()
    await send_q(context, query.message.chat_id)

async def send_q(context, chat_id):
    ud = context.user_data
    idx = ud.get('idx', 0)
    qs = ud['qs']
    if idx >= len(qs):
        await context.bot.send_message(chat_id, f"🎊 क्विज़ खत्म! स्कोर: {ud['score']}/{len(qs)}")
        return
    q = qs[idx]
    await context.bot.send_poll(chat_id=chat_id, question=q['variations'][0], options=q['options'], type=Poll.QUIZ, correct_option_id=q['answer'], is_anonymous=False)
    ud['idx'] = idx + 1

async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    ud = context.application.user_data.get(ans.user.id)
    if ud and ud.get('busy'):
        if ans.option_ids[0] == ud['qs'][ud['idx']-1]['answer']: ud['score'] += 1
        await asyncio.sleep(1)
        await send_q(context, ans.user.id)

def main():
    sync_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_topic))
    app.add_handler(PollAnswerHandler(handle_ans))
    # अब यह किसी भी टेक्स्ट मैसेज को JSON मानकर पढ़ेगा
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_json_input))

    port = int(os.environ.get("PORT", 10000))
    app.run_webhook(listen="0.0.0.0", port=port, url_path=TOKEN, webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}")

if __name__ == '__main__':
    main()
