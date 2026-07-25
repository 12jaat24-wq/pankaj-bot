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

# --- रेंडर Environment Variables ---
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
        # '?t=' लगाने से गिटहब मजबूरन नयी फाइल भेजता है
        r = requests.get(f"{GITHUB_URL}?t={int(time.time())}", timeout=20)
        if r.status_code == 200:
            DB_CACHE = r.json()
            logger.info("Database synced successfully.")
            return True
    except Exception as e:
        logger.error(f"Sync error: {e}")
        return False

# --- 1. /refresh कमांड (पलक झपकते ही नया डेटा) ---
async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ **गिटहब की तिजोरी से ताज़ा सवाल निकाल रहा हूँ...**")
    if sync_db():
        total_topics = len(DB_CACHE.keys())
        await msg.edit_text(f"✅ **रिफ्रेश सफल!**\n\n📂 कुल विषय: `{total_topics}`\n✨ अब आप /start दबाकर नया डेटा देख सकते हैं।")
    else:
        await msg.edit_text("❌ **रिफ्रेश फेल!**\nचेक करें कि गिटहब पर फाइल सही है या नहीं।")

# --- 2. डेटा जोड़ने और डिलीट करने का लॉजिक ---
async def handle_json_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "variations" not in text: return 
    msg = await update.message.reply_text("⏳ **गिटहब पर डेटा सेव हो रहा है...**")
    try:
        new_data = json.loads(text.replace('```json', '').replace('```', '').strip())
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        file = repo.get_contents(DB_FILE)
        current_db = json.loads(file.decoded_content.decode())
        current_db.update(new_data)
        repo.update_file(file.path, "Update via Bot", json.dumps(current_db, indent=4, ensure_ascii=False), file.sha)
        sync_db()
        await msg.edit_text("✅ **सेव हो गया!** अब /refresh दबाएँ और फिर /start")
    except Exception as e:
        await msg.edit_text(f"❌ **गड़बड़:** {str(e)}")

async def delete_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("💡 `/delete Topic_Name` लिखें।")
    topic = " ".join(context.args)
    msg = await update.message.reply_text(f"🗑️ **'{topic}' को हटा रहा हूँ...**")
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode())
        if topic in db:
            del db[topic]
            repo.update_file(file.path, f"Deleted {topic}", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
            sync_db()
            await msg.edit_text(f"💥 **उड़ गया!** '{topic}' डिलीट हो गया।")
        else: await msg.edit_text("❌ विषय नहीं मिला।")
    except Exception as e: await msg.edit_text(f"❌ गड़बड़: {str(e)}")

# --- 3. रंगीन UI और क्विज़ लॉजिक ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_CACHE: sync_db()
    if not DB_CACHE: return await update.message.reply_text("❌ **डेटाबेस खाली है!**")
    
    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "💎", "🔥", "🌈", "⚡"]
    keyboard = [[InlineKeyboardButton(f"{random.choice(icons)} {t}", callback_data=t)] for t in DB_CACHE.keys()]
    
    welcome_text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✨ **पंकज क्विज़ बॉट v2.0** ✨\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎯 **विषय चुनकर अपनी तैयारी जांचें:** 👇"
    )
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
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
        score = ud['score']
        msg = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🎊 **क्विज़ समाप्त!** 🎊\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 **विषय:** `{ud['topic']}`\n"
            f"✅ **सही:** `{score}` | ❌ **गलत:** `{total - score}`\n"
            f"🏆 **परिणाम:** `{int((score/total)*100)}%` \n\n"
            "नया शुरू करने के लिए /start दबाएँ।"
        )
        await context.bot.send_message(chat_id, msg, parse_mode="Markdown")
        ud['busy'] = False
        return

    q = qs[idx]
    progress = "🔹" * (idx + 1) + "▫️" * (total - idx - 1)
    await context.bot.send_poll(
        chat_id=chat_id,
        question=f"✨ ({idx+1}/{total}) {q['variations'][0]}\n{progress}",
        options=q['options'],
        type=Poll.QUIZ,
        correct_option_id=q['answer'],
        is_anonymous=False,
        explanation="मेहनत कभी बेकार नहीं जाती! 💪"
    )
    ud['idx'] = idx + 1

# --- ऑटो-नेक्स्ट फंक्शन ---
async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    user_id = ans.user.id
    # Application-level user_data से डेटा निकालना
    ud = context.application.user_data.get(user_id)
    
    if ud and ud.get('busy'):
        current_idx = ud['idx'] - 1
        if ans.option_ids[0] == ud['qs'][current_idx]['answer']:
            ud['score'] += 1
        
        await asyncio.sleep(0.7) # छोटा गैप
        # यहाँ context.user_data काम नहीं करेगा, मैन्युअल पास करना होगा
        class TempContext:
            def __init__(self, user_data, bot):
                self.user_data = user_data
                self.bot = bot
        
        await send_q(TempContext(ud, context.bot), user_id)

def main():
    sync_db()
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh_command)) # नई रिफ्रेश कमांड
    app.add_handler(CommandHandler("delete", delete_topic))
    app.add_handler(CallbackQueryHandler(handle_topic))
    app.add_handler(PollAnswerHandler(handle_ans))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_json_input))

    port = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0", port=port, url_path=TOKEN,
        webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}"
    )

if __name__ == '__main__':
    main()
