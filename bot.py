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

# --- स्टाइलिश फॉन्ट फंक्शन (पूरी तरह फिक्स किया गया) ---
def style_txt(text):
    normal =  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    stylish = "𝗮𝖻𝗰𝖽𝗲𝖿𝗴𝗁𝗶𝗷𝗸𝗅𝗺𝗻𝗼𝗽𝗊𝗿𝘀𝘁𝘂𝗏𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    if len(normal) != len(stylish): return text # सुरक्षा के लिए
    trans = str.maketrans(normal, stylish)
    return str(text).translate(trans)

def sync_db():
    global DB_CACHE
    try:
        r = requests.get(f"{GITHUB_URL}?t={int(time.time())}", timeout=15)
        if r.status_code == 200:
            DB_CACHE = r.json()
            return True
    except: return False
    return False

# --- /refresh कमांड (Stylish Inventory) ---
async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    msg = await update.message.reply_text("🔄 `Syncing with GitHub Vault...`", parse_mode="Markdown")
    if sync_db():
        total_topics = len(DB_CACHE.keys())
        total_qs = sum(len(v) for v in DB_CACHE.values())
        
        table = "┌──────────────────┐\n"
        table += "   📦  MY INVENTORY   \n"
        table += "├──────────────────┤\n"
        icons = ["💎", "🔥", "⚡", "🎯", "🌈", "🔮"]
        for t, q in DB_CACHE.items():
            # टॉपिक का नाम छोटा रखना ताकि टेबल न बिगड़े
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
            "👉 **अब /start दबाकर शुरू करें!**"
        )
        await msg.edit_text(res, parse_mode="Markdown")
    else:
        await msg.edit_text("❌ **ERROR:** GitHub सिंक फेल हो गया।")

# --- डेटा अपडेट सिस्टम ---
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # अगर डॉक्यूमेंट है
    if update.message.document:
        doc = update.message.document
        if doc.file_name.endswith(('.json', '.txt')):
            file = await context.bot.get_file(doc.file_id)
            content = await file.download_as_bytearray()
            json_text = content.decode('utf-8')
        else: return
    # अगर टेक्स्ट है
    elif update.message.text and "variations" in update.message.text:
        json_text = update.message.text
    else: return

    try:
        new_data = json.loads(json_text.replace('```json', '').replace('```', '').strip())
        m = await update.message.reply_text("⚡ `Processing Data...`", parse_mode="Markdown")
        
        g = Github(GITHUB_TOKEN); repo = g.get_repo(REPO_NAME); file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode()); db.update(new_data)
        repo.update_file(file.path, "Bot Bulk Update", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
        sync_db()
        
        res = (
            "🚀 **SAFTAPURVAK JODA GYA**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ आपका डेटा गिटहब पर सुरक्षित सेव हो गया है।\n\n"
            "👉 अब **रिफ्रेश** करें: /refresh\n"
            "👉 फिर **स्टार्ट** करें: /start"
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
            sync_db(); await update.message.reply_text(f"🗑️ **SUCCESS:** `{t}` को तिजोरी से हटा दिया गया।")
        else: await update.message.reply_text("❌ यह टॉपिक नहीं मिला।")
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

# --- क्विज़ लॉजिक ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear() # फोर्स रिसेट
    if not DB_CACHE: sync_db()
    if not DB_CACHE: return await update.message.reply_text("❌ डेटाबेस खाली है! कृपया JSON फाइल भेजें।")
    
    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "🟠", "💎", "⚡"]
    keyboard = []
    for t in sorted(DB_CACHE.keys()): # नाम के हिसाब से सार्ट करना
        btn_txt = f"{random.choice(icons)} {style_txt(t)}"
        keyboard.append([InlineKeyboardButton(btn_txt, callback_data=t)])
    
    welcome = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "   👑 **PANKAJ QUIZ BOT 2.0** 👑\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎯 **तैयारी ऐसी करो कि सफलता शोर मचा दे!**\n\n"
        "👉 अपना विषय चुनें:"
    )
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    topic = query.data
    qs = list(DB_CACHE.get(topic, []))
    
    if not qs:
        await query.message.reply_text(f"⚠️ `{topic}` खाली है।")
        return

    random.shuffle(qs)
    context.user_data.update({'qs': qs, 'idx': 0, 'score': 0, 'busy': True, 'topic': topic})
    await query.delete_message()
    await send_q(context, query.message.chat_id)

async def send_q(context, chat_id):
    ud = context.user_data
    idx, qs = ud.get('idx', 0), ud.get('qs', [])
    total = len(qs)

    if idx >= total:
        score = ud.get('score', 0); per = int((score/total)*100)
        medal = "🏆" if per >= 80 else "🥇" if per >= 60 else "🥈"
        res = (
            f"╔══════════════════╗\n   📊 **FINAL REPORT** {medal}  \n╚══════════════════╝\n"
            f"📝 विषय: `{ud['topic']}`\n✅ सही: `{score}` | ❌ गलत: `{total-score}`\n🏆 स्कोर: `{per}%` \n━━━━━━━━━━━━━━━━━━━━\n🔥 /start - Play Again"
        )
        await context.bot.send_message(chat_id, res, parse_mode="Markdown")
        ud.clear(); return

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
    
    # कमांड्स को सबसे पहले रखें
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(PollAnswerHandler(handle_ans))
    
    # डेटा अपलोड हैंडलर (टेक्स्ट और फाइल)
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_input))

    p = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0", port=p, url_path=TOKEN, 
        webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}",
        drop_pending_updates=False 
    )

if __name__ == '__main__':
    main()
