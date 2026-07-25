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

# --- स्टाइलिश फॉन्ट ---
def style_txt(text):
    normal =  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    stylish = "𝗮𝖻𝗰𝖽𝗲𝖿𝗴𝗁𝗶𝗷𝗸𝗅𝗺𝗻𝗼𝗽𝗊𝗿𝘀𝘁𝘂𝗏𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    trans = str.maketrans(normal, stylish)
    return str(text).translate(trans)

def sync_db():
    global DB_CACHE
    try:
        # टाइमस्टैम्प के साथ फ्रेश डेटा लोड
        r = requests.get(f"{GITHUB_URL}?t={int(time.time())}", timeout=15)
        if r.status_code == 200:
            DB_CACHE = r.json()
            return True
    except: return False
    return False

# --- स्टाइलिश रिफ्रेश ---
async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    msg = await update.message.reply_text("🔄 `Cleaning Queue & Syncing...`", parse_mode="Markdown")
    if sync_db():
        total_topics = len(DB_CACHE.keys())
        total_qs = sum(len(v) for v in DB_CACHE.values())
        
        table = "┌──────────────────┐\n"
        table += "   📦  MY INVENTORY   \n"
        table += "├──────────────────┤\n"
        icons = ["💎", "🔥", "⚡", "🎯", "🌈"]
        for t, q in DB_CACHE.items():
            short_t = (t[:12] + '..') if len(t) > 12 else t.ljust(14)
            table += f" {random.choice(icons)} {short_t} | {len(q)}Q\n"
        table += "└──────────────────┘"

        res = (
            "╔════════════════════╗\n"
            "   ✅ **REFRESH SUCCESS**   \n"
            "╚════════════════════╝\n\n"
            f"```\n{table}\n```\n"
            f"📂 कुल विषय: `{total_topics}`\n"
            f"📊 कुल प्रश्न: `{total_qs}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👉 **अब /start दबाएँ!**"
        )
        await msg.edit_text(res, parse_mode="Markdown")
    else:
        await msg.edit_text("❌ **ERROR:** सिंक फेल।")

# --- डेटा अपडेट सिस्टम ---
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document:
        doc = update.message.document
        if doc.file_name.endswith(('.json', '.txt')):
            file = await context.bot.get_file(doc.file_id)
            content = await file.download_as_bytearray()
            json_text = content.decode('utf-8')
        else: return
    elif update.message.text and "variations" in update.message.text:
        json_text = update.message.text
    else: return

    try:
        new_data = json.loads(json_text.replace('```json', '').replace('```', '').strip())
        m = await update.message.reply_text("⚡ `Updating GitHub Vault...`", parse_mode="Markdown")
        
        g = Github(GITHUB_TOKEN); repo = g.get_repo(REPO_NAME); file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode()); db.update(new_data)
        repo.update_file(file.path, "Bot Sync", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
        sync_db()
        
        await m.edit_text("🚀 **SAFTAPURVAK JODA GYA**\n━━━━━━━━━━━━━━━━━━━━\n✅ डेटा सुरक्षित सेव हो गया।\n👉 लोड करें: /refresh")
    except Exception as e:
        await update.message.reply_text(f"❌ **JSON ERROR:** {str(e)}")

# --- स्टाइलिश डिलीट ---
async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = " ".join(context.args)
    if not t: return await update.message.reply_text("💡 `/delete TopicName` लिखें।")
    try:
        g = Github(GITHUB_TOKEN); repo = g.get_repo(REPO_NAME); file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode())
        if t in db:
            del db[t]
            repo.update_file(file.path, f"Removed {t}", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
            sync_db(); await update.message.reply_text(f"🗑️ **SUCCESS:** `{t}` हट गया।")
        else: await update.message.reply_text("❌ विषय नहीं मिला।")
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

# --- क्विज़ लॉजिक ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if not DB_CACHE: sync_db()
    if not DB_CACHE: return await update.message.reply_text("❌ डेटाबेस खाली है!")
    
    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "🟠", "💎"]
    keyboard = []
    for t in sorted(DB_CACHE.keys()):
        keyboard.append([InlineKeyboardButton(f"{random.choice(icons)} {style_txt(t)}", callback_data=t)])
    
    welcome = "━━━━━━━━━━━━━━━━━━━━\n   👑 **PANKAJ QUIZ BOT 2.0** 👑\n━━━━━━━━━━━━━━━━━━━━\n\n🎯 विषय चुनकर तैयारी शुरू करें:"
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    topic = query.data
    qs = list(DB_CACHE.get(topic, []))
    if not qs: return await query.message.reply_text("⚠️ खाली है।")
    
    random.shuffle(qs)
    context.user_data.update({'qs': qs, 'idx': 0, 'score': 0, 'busy': True, 'topic': topic})
    await query.delete_message()
    await send_q(context, query.message.chat_id)

async def send_q(context, chat_id):
    ud = context.user_data
    idx, qs = ud.get('idx', 0), ud.get('qs', [])
    total = len(qs)

    if idx >= total:
        if total > 0:
            score = ud.get('score', 0); per = int((score/total)*100)
            res = f"📊 **REPORT CARD**\n━━━━━━━━━━\n📝 विषय: `{ud['topic']}`\n✅ सही: `{score}/{total}`\n🏆 स्कोर: `{per}%` \n━━━━━━━━━━\n🔥 /start"
            await context.bot.send_message(chat_id, res, parse_mode="Markdown")
        ud.clear(); return

    q = qs[idx]
    bar = "🔹" * (idx + 1) + "▫️" * (total - idx - 1)
    try:
        await context.bot.send_poll(chat_id=chat_id, question=f"✨ ({idx+1}/{total}) {q['variations'][0]}\n{bar}", options=q['options'], type=Poll.QUIZ, correct_option_id=q['answer'], is_anonymous=False)
        ud['idx'] = idx + 1
    except:
        await asyncio.sleep(1); await send_q(context, chat_id)

async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer; uid = ans.user.id
    ud = context.application.user_data.get(uid)
    if ud and ud.get('busy'):
        cur = ud['idx'] - 1
        if ans.option_ids[0] == ud['qs'][cur]['answer']: ud['score'] += 1
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
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_input))

    # --- महत्वपूर्ण बदलाव (The Fix) ---
    p = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0", port=p, url_path=TOKEN,
        webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}",
        drop_pending_updates=True # यह अटके हुए मैसेज साफ़ कर देगा
    )

if __name__ == '__main__':
    main()
