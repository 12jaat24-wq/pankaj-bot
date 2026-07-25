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
        r = requests.get(f"{GITHUB_URL}?t={int(time.time())}", timeout=20)
        if r.status_code == 200:
            DB_CACHE = r.json()
            return True
    except: return False

# --- 1. रिफ्रेश और डिलीट कमांड्स ---
async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ **डेटा ताज़ा किया जा रहा है...**")
    if sync_db():
        await msg.edit_text(f"✅ **सफलता!** अब आप नए सवाल देख सकते हैं।")
    else:
        await msg.edit_text("❌ **फेल!** गिटहब चेक करें।")

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
            await msg.edit_text(f"💥 **डिलीट सफल!**")
        else: await msg.edit_text("❌ विषय नहीं मिला।")
    except Exception as e: await msg.edit_text(f"❌ गड़बड़: {str(e)}")

# --- 2. डेटा जोड़ने का सिस्टम ---
async def handle_json_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "variations" not in text: return 
    msg = await update.message.reply_text("⏳ **गिटहब अपडेट हो रहा है...**")
    try:
        new_data = json.loads(text.replace('```json', '').replace('```', '').strip())
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode())
        db.update(new_data)
        repo.update_file(file.path, "Bot Update", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
        sync_db()
        await msg.edit_text("✅ **सेव हो गया!** अब /start दबाएँ।")
    except Exception as e: await msg.edit_text(f"❌ गड़बड़: {str(e)}")

# --- 3. रंगीन UI और क्विज़ लॉजिक ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_CACHE: sync_db()
    if not DB_CACHE: return await update.message.reply_text("❌ **डेटाबेस खाली है!**")
    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "💎", "🔥", "🌈", "⚡"]
    keyboard = [[InlineKeyboardButton(f"{random.choice(icons)} {t}", callback_data=t)] for t in DB_CACHE.keys()]
    welcome = "━━━━━━━━━━━━━━\n✨ **PANKAJ QUIZ BOT** ✨\n━━━━━━━━━━━━━━\n\n🎯 अपना विषय चुनें और शुरू करें: 👇"
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # अगर "Next" बटन दबाया गया है
    if query.data == "next_q":
        user_id = query.from_user.id
        ud = context.application.user_data.get(user_id)
        if ud and ud.get('busy'):
            # पुराना 'Next' मैसेज डिलीट करना (साफ़-सफाई के लिए)
            try: await query.delete_message()
            except: pass
            # अगला सवाल भेजना
            class TempContext:
                def __init__(self, user_data, bot): self.user_data = user_data; self.bot = bot
            await send_q(TempContext(ud, context.bot), user_id)
        return

    # विषय चुनने पर
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

    # क्विज़ समाप्त होने पर
    if idx >= total:
        score = ud['score']
        msg = (
            "━━━━━━━━━━━━━━\n🎊 **क्विज़ संपन्न!** 🎊\n━━━━━━━━━━━━━━\n\n"
            f"📊 विषय: `{ud['topic']}`\n"
            f"🏆 स्कोर: `{score}/{total}` ({int((score/total)*100)}%)\n\n"
            "नया टॉपिक चुनने के लिए /start दबाएँ। 🔥"
        )
        await context.bot.send_message(chat_id, msg, parse_mode="Markdown")
        ud['busy'] = False
        return

    q = qs[idx]
    progress = "🔹" * (idx + 1) + "▫️" * (total - idx - 1)
    
    # पोल भेजना
    await context.bot.send_poll(
        chat_id=chat_id,
        question=f"✨ ({idx+1}/{total}) {q['variations'][0]}\n{progress}",
        options=q['options'],
        type=Poll.QUIZ,
        correct_option_id=q['answer'],
        is_anonymous=False,
        explanation="सही उत्तर ही सफलता की कुंजी है! 📚"
    )
    ud['idx'] = idx + 1

    # रंगीन "NEXT" बटन भेजना (ताकि नेट स्लो होने पर काम आए)
    next_btn = [[InlineKeyboardButton("⏭️ अगे बढ़ें (Next) ⏩", callback_data="next_q")]]
    await context.bot.send_message(
        chat_id, 
        "💡 *अगर अगला सवाल खुद न आए, तो नीचे बटन दबाएँ:*", 
        reply_markup=InlineKeyboardMarkup(next_btn),
        parse_mode="Markdown"
    )

# --- 4. ऑटो-नेक्स्ट फंक्शन ---
async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    user_id = ans.user.id
    ud = context.application.user_data.get(user_id)
    
    if ud and ud.get('busy'):
        current_idx = ud['idx'] - 1
        if ans.option_ids[0] == ud['qs'][current_idx]['answer']:
            ud['score'] += 1
        
        # ऑटो-नेक्स्ट के लिए छोटा गैप
        await asyncio.sleep(1.2)
        class TempContext:
            def __init__(self, user_data, bot): self.user_data = user_data; self.bot = bot
        await send_q(TempContext(ud, context.bot), user_id)

def main():
    sync_db()
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh_command))
    app.add_handler(CommandHandler("delete", delete_topic))
    app.add_handler(CallbackQueryHandler(handle_callback)) # कंबाइंड हैंडलर
    app.add_handler(PollAnswerHandler(handle_ans))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_json_input))

    port = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0", port=port, url_path=TOKEN,
        webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}"
    )

if __name__ == '__main__':
    main()
