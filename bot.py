import os
import json
import random
import logging
import asyncio
from flask import Flask
from threading import Thread
from github import Github
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

# --- रेंडर को जगाए रखने के लिए (Keep-Alive) ---
flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "⚡ Bot is Ultra Fast"

def run_flask():
    flask_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# --- सेटिंग्स ---
TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = "12jaat24-wq/pankaj-bot"
DB_FILE = "quiz_database.json"

logging.basicConfig(level=logging.ERROR) # सिर्फ एरर दिखाएगा ताकि स्पीड बढ़े
DB_CACHE = {}

def style_txt(text):
    n = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    s = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝘅𝗬𝘡𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    return str(text).translate(str.maketrans(n, s))

# --- सुपर फ़ास्ट डेटा लोडर ---
async def load_db():
    global DB_CACHE
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        DB_CACHE = json.loads(repo.get_contents(DB_FILE).decoded_content.decode())
    except: pass

# --- मास्टर फिक्स: ये कमांड कभी जाम नहीं होगी ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. तुरंत जवाब दो ताकि 'घड़ी' का निशान हट जाए
    chat_id = update.effective_chat.id
    
    # 2. बैकग्राउंड में काम शुरू करें (Non-Blocking)
    asyncio.create_task(process_start(update, context))

async def process_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not DB_CACHE: await load_db()
        
        keyboard = [[InlineKeyboardButton(f"⭐ {style_txt(t)}", callback_data=t)] for t in sorted(DB_CACHE.keys())]
        
        text = (
            "╔════════════════════╗\n"
            f"   👑  {style_txt('PANKAJ QUIZ 2.0')}  👑\n"
            "╚════════════════════╝\n\n"
            "🚀 **सुपर-फ़ास्ट इंजन एक्टिवेटिड!**\n"
            "नीचे से अपना विषय चुनें: 👇"
        )
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except: pass

# --- क्विज़ इंजन (बिना रुके) ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # तुरंत टेलीग्राम को बताओ कि मैसेज मिल गया
    
    topic = query.data
    qs = list(DB_CACHE.get(topic, []))
    if not qs: return
    
    random.shuffle(qs)
    context.user_data.update({'qs': qs, 'idx': 0, 'score': 0, 'topic': topic})
    
    await query.delete_message()
    await send_next_poll(context, query.message.chat_id)

async def send_next_poll(context, chat_id):
    ud = context.user_data
    idx, qs = ud['idx'], ud['qs']
    
    if idx >= len(qs):
        await context.bot.send_message(chat_id, f"🏆 **स्कोर:** `{ud['score']}/{len(qs)}`\n/start - फिर खेलें")
        return

    q = qs[idx]
    await context.bot.send_poll(
        chat_id=chat_id,
        question=f"❓ ({idx+1}/{len(qs)}) {q['variations'][0]}",
        options=q['options'],
        type=Poll.QUIZ,
        correct_option_id=q['answer'],
        is_anonymous=False
    )
    ud['idx'] += 1

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    uid = ans.user.id
    ud = context.application.user_data.get(uid)
    
    if ud and 'qs' in ud:
        if ans.option_ids[0] == ud['qs'][ud['idx']-1]['answer']:
            ud['score'] += 1
        
        # 0.5 सेकंड का इंतज़ार और अगला सवाल
        await asyncio.sleep(0.5)
        
        # सुरक्षित कॉल
        class Dummy: pass
        ctx = Dummy()
        ctx.user_data = ud; ctx.bot = context.bot
        await send_next_poll(ctx, uid)

# --- मेन कंट्रोल ---
def main():
    # रेंडर को सुलाने से रोकने के लिए
    Thread(target=run_flask, daemon=True).start()

    # 'concurrent_updates' को बहुत बढ़ा दिया है ताकि एक साथ 50 लोग भी आएँ तो बॉट न रुके
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(PollAnswerHandler(handle_answer))
    app.add_handler(CommandHandler("refresh", lambda u, c: load_db()))

    print("--- ULTRA FAST MODE ON ---")
    
    # drop_pending_updates: शुरू होते ही पुराने सारे 'घड़ी' वाले मैसेज साफ़ कर देगा
    app.run_polling(drop_pending_updates=True, poll_interval=0.1)

if __name__ == '__main__':
    main()
