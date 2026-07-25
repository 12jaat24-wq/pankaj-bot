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

# --- कॉन्फ़िगरेशन ---
TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = "12jaat24-wq/pankaj-bot"
DB_FILE = "quiz_database.json"
GITHUB_URL = f"https://raw.githubusercontent.com/{REPO_NAME}/main/{DB_FILE}"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CACHE = {}

# --- जादुई फॉन्ट कन्वर्टर (बटन और टेक्स्ट के लिए) ---
def style_txt(text):
    # यह फंक्शन सादे अक्षरों को स्टाइलिश (Math Bold) में बदल देगा
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    stylish = "𝗮𝖻𝗰𝖽𝗲𝖿𝗴𝗁𝗶𝗷𝗸𝗅𝗺𝗻𝗼𝗽𝗊𝗿𝘀𝘁𝘂𝗏𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    trans = str.maketrans(normal, stylish)
    return text.translate(trans)

def sync_db():
    global DB_CACHE
    try:
        r = requests.get(f"{GITHUB_URL}?t={int(time.time())}", timeout=15)
        if r.status_code == 200:
            DB_CACHE = r.json()
            return True
    except: return False
    return False

# --- स्टाइलिश रिफ्रेश (Table Style) ---
async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 `Connecting to GitHub...`", parse_mode="Markdown")
    if sync_db():
        total_topics = len(DB_CACHE.keys())
        total_qs = sum(len(v) for v in DB_CACHE.values())
        
        # टेबल जैसा लुक
        table_content = "┌───────────────┐\n"
        table_content += "   📚 विषय सूची (Inventory)   \n"
        table_content += "├───────────────┤\n"
        
        icons = ["🔥", "⚡", "💎", "🎯", "🌟", "🚀"]
        for t, q in DB_CACHE.items():
            table_content += f" {random.choice(icons)} {t[:12]}.. | {len(q)} Q\n"
        
        table_content += "└───────────────┘"

        res = (
            "╔════════════════════╗\n"
            "   ✅ **SYSTEM REFRESHED**   \n"
            "╚════════════════════╝\n\n"
            f"```\n{table_content}\n```\n"
            f"📂 **TOTAL TOPICS:**  `{total_topics}`\n"
            f"📊 **TOTAL MCQS:**    `{total_qs}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👉 **अब /start दबाकर शुरू करें!**"
        )
        await msg.edit_text(res, parse_mode="Markdown")
    else:
        await msg.edit_text("❌ **ERROR:** Sync Failed!")

# --- डेटा सेविंग सिस्टम ---
async def process_and_upload(update, context, json_text):
    try:
        new_data = json.loads(json_text.replace('```json', '').replace('```', '').strip())
        m = await update.message.reply_text("⚡ `Processing...`", parse_mode="Markdown")
        
        g = Github(GITHUB_TOKEN); repo = g.get_repo(REPO_NAME); file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode()); db.update(new_data)
        repo.update_file(file.path, "Update via Bot", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
        sync_db()
        
        res = (
            "🚀 **DATA SAVED SUCCESSFULLY**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ आपका नया टॉपिक तिजोरी में सेव हो गया है।\n\n"
            "✨ **आगे क्या करें?**\n"
            "1️⃣ /refresh दबाकर लोड करें\n"
            "2️⃣ /start दबाकर क्विज़ खेलें"
        )
        await m.edit_text(res, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ **JSON ERROR:** {str(e)}")

# --- स्टाइलिश डिलीट ---
async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("💡 `/delete TopicName` लिखें।")
    t = " ".join(context.args)
    try:
        g = Github(GITHUB_TOKEN); repo = g.get_repo(REPO_NAME); file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode())
        if t in db:
            del db[t]
            repo.update_file(file.path, f"Deleted {t}", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
            sync_db()
            await update.message.reply_text(f"🗑️ **REMOVED:** `{t}` has been deleted from GitHub.")
        else: await update.message.reply_text("❌ Topic not found.")
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

# --- क्विज़ लॉजिक (Stylish Buttons) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_CACHE: sync_db()
    if not DB_CACHE: return await update.message.reply_text("❌ Data Empty!")
    
    # टॉपिक बटन्स को स्टाइलिश बनाना
    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "🟠", "🌈"]
    keyboard = []
    for t in DB_CACHE.keys():
        btn_text = f"{random.choice(icons)} {style_txt(t)}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=t)])
    
    welcome = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "   👑 **PANKAJ QUIZ BOT 2.0** 👑\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "✨ **अपने सपनों को साकार करने के लिए तैयार?**\n\n"
        "🎯 **नीचे से अपना विषय (Topic) चुनें:**"
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
        medal = "🏆" if per >= 80 else "🥈"
        res = (
            f"╔══════════════════╗\n"
            f"   📊 **FINAL REPORT** {medal}  \n"
            f"╚══════════════════╝\n"
            f"📝 **TOPIC:**  `{ud['topic']}`\n"
            f"✅ **CORRECT:** `{score}`\n"
            f"❌ **WRONG:**   `{total-score}`\n"
            f"🏆 **SCORE:**   `{per}%` \n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 /start - Play Again"
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
        await asyncio.sleep(0.5) # 0.5s Fast Auto-Next
        
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

    p = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0", port=p, url_path=TOKEN, 
        webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}",
        drop_pending_updates=False # ताकि कोई कमांड मिस न हो
    )

if __name__ == '__main__':
    main()
