import os
import json
import random
import logging
import asyncio
import threading
from flask import Flask # रेंडर को जगाए रखने के लिए
from github import Github
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, MessageHandler, filters, ContextTypes

# --- FLASK SERVER (Render Keep-Alive) ---
# रेंडर को लगेगा कि यह एक वेबसाइट है और वह इसे बंद नहीं करेगा
flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "Bot is Running..."

def run_flask():
    flask_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# --- बॉट का मुख्य हिस्सा ---
TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = "12jaat24-wq/pankaj-bot"
DB_FILE = "quiz_database.json"

logging.basicConfig(level=logging.INFO)
DB_CACHE = {}

def style_txt(text):
    normal =  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    stylish = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝘅𝗬𝘡𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    return str(text).translate(str.maketrans(normal, stylish))

# --- SUPER FAST SYNC ---
async def sync_db():
    global DB_CACHE
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        file = repo.get_contents(DB_FILE)
        DB_CACHE = json.loads(file.decoded_content.decode())
        return True
    except: return False

# --- ANTI-JAM START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_CACHE: await sync_db()
    
    keyboard = [[InlineKeyboardButton(f"🔥 {style_txt(t)}", callback_data=t)] for t in sorted(DB_CACHE.keys())]
    
    welcome = (
        "╔════════════════════╗\n"
        f"   👑 **{style_txt('PANKAJ QUIZ BOT 2.0')}** 👑\n"
        "╚════════════════════╝\n\n"
        "🚀 **बॉट पूरी तरह सुपर-फ़ास्ट मोड में है!**\n"
        "🎯 अपना विषय चुनें और शुरू हो जाएँ:"
    )
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# --- FAST QUIZ ENGINE ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = query.data
    qs = list(DB_CACHE.get(topic, []))
    random.shuffle(qs)
    
    context.user_data.update({'qs': qs, 'idx': 0, 'score': 0, 'active': True, 'topic': topic})
    await query.delete_message()
    await send_q(context, query.message.chat_id)

async def send_q(context, chat_id):
    ud = context.user_data
    if not ud.get('active'): return
    idx, qs = ud['idx'], ud['qs']
    
    if idx >= len(qs):
        res = f"🏁 **QUIZ FINISHED!**\n✅ Score: `{ud['score']}/{len(qs)}`\n\n/start दबाएँ।"
        await context.bot.send_message(chat_id, res, parse_mode="Markdown")
        ud.clear(); return

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

async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    uid = ans.user.id
    ud = context.application.user_data.get(uid)
    if ud and ud.get('active'):
        if ans.option_ids[0] == ud['qs'][ud['idx']-1]['answer']: ud['score'] += 1
        await asyncio.sleep(0.5) # 0.5s Fast Next
        
        # Create Dummy context for stability
        class TC:
            def __init__(self, u, b): self.user_data=u; self.bot=b
        await send_q(TC(ud, context.bot), uid)

# --- REFRESH ---
async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text("🔄 `Syncing Engine...`")
    if await sync_db(): await m.edit_text("✅ **Sync Complete!** /start")
    else: await m.edit_text("❌ Sync Failed!")

# --- MAIN ENGINE (The Real Fix) ---
def main():
    # 1. Flask को अलग Thread में चलाएं ताकि Render का पोर्ट ओपन रहे
    threading.Thread(target=run_flask, daemon=True).start()

    # 2. बॉट को Polling मोड में चलाएं (Webhook से 100 गुना ज्यादा भरोसेमंद)
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(PollAnswerHandler(handle_ans))

    print("--- BOT IS LIVE AND UNSTOPPABLE ---")
    
    # drop_pending_updates=True पुराने अटके हुए हज़ारों मैसेज को तुरंत डिलीट कर देगा
    app.run_polling(drop_pending_updates=True, poll_interval=0.5)

if __name__ == '__main__':
    main()
