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

# --- सुपर स्टाइलिश फॉन्ट फंक्शन (Ghra Bold) ---
def style_txt(text):
    normal =  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    stylish = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
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

# --- मोटिवेशनल शायरियां ---
SHAYARIS = [
    "✨ *मंज़िल उन्हीं को मिलती है, जिनके सपनों में जान होती है,*\n*पंखों से कुछ नहीं होता, हौसलों से उड़ान होती है।*",
    "🔥 *हौसले के तरकश में कोशिश का वो तीर ज़िंदा रख,*\n*हार जा चाहे ज़िंदगी में सब कुछ, मगर फिर से जीतने की उम्मीद ज़िंदा रख।*",
    "🚀 *शुरुआत करने के लिए महान होना ज़रूरी नहीं,*\n*लेकिन महान होने के लिए शुरुआत करना ज़रूरी है।*",
    "💎 *मैदान में हारा हुआ इंसान फिर से जीत सकता है,*\n*लेकिन मन से हारा हुआ इंसान कभी नहीं जीत सकता।*",
    "🌈 *वक्त से लड़कर जो नसीब बदल दे, इंसान वही जो अपनी तकदीर बदल दे।*"
]

# --- स्टाइलिश डेटा अपलोड मैसेज ---
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document:
        file = await context.bot.get_file(update.message.document.file_id)
        content = await file.download_as_bytearray()
        json_text = content.decode('utf-8')
    elif update.message.text and "variations" in update.message.text:
        json_text = update.message.text
    else: return

    try:
        new_data = json.loads(json_text.replace('```json', '').replace('```', '').strip())
        m = await update.message.reply_text("🌀 `Processing Vault...`", parse_mode="Markdown")
        
        g = Github(GITHUB_TOKEN); repo = g.get_repo(REPO_NAME); file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode()); db.update(new_data)
        repo.update_file(file.path, "Vault Updated", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
        sync_db()
        
        res = (
            "╔════════════════════╗\n"
            "   📦 **DATABASE UPDATED** 🚀  \n"
            "╚════════════════════╝\n\n"
            "✅ **ज्ञान का नया खजाना सुरक्षित जड़ दिया गया है!**\n\n"
            "🌀 अब पहले **लोड (Refresh)** करें: /refresh\n"
            "🔥 फिर अपनी **तैयारी (Start)** करें: /start\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        await m.edit_text(res, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ **ERROR:** `{e}`")

# --- स्टाइलिश रिफ्रेश (Inventory) ---
async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    msg = await update.message.reply_text("📡 `Syncing Data Centers...`", parse_mode="Markdown")
    if sync_db():
        total_topics = len(DB_CACHE.keys())
        total_qs = sum(len(v) for v in DB_CACHE.values())
        
        table = "┌──────────────────┐\n"
        table += "   📋  SUBJECT  |  MCQS   \n"
        table += "├──────────────────┤\n"
        icons = ["🔅", "🔱", "⚛️", "💠", "🌀", "🛰️"]
        for t, q in DB_CACHE.items():
            short_t = (t[:10] + '..') if len(t) > 10 else t.ljust(12)
            table += f" {random.choice(icons)} {short_t} | {len(q)} Q\n"
        table += "└──────────────────┘"

        res = (
            "╔════════════════════╗\n"
            "   🔄 **REFRESH SUCCESS** 🔄  \n"
            "╚════════════════════╝\n\n"
            f"```\n{table}\n```\n"
            f"📂 कुल विषय:   `{total_topics}`\n"
            f"📚 कुल सवाल:  `{total_qs}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🌟 **सब कुछ तैयार है!** अब /start दबाएँ।"
        )
        await msg.edit_text(res, parse_mode="Markdown")
    else:
        await msg.edit_text("❌ **FAILED:** सिंक अधूरा रह गया।")

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
            sync_db()
            res = (
                "╔════════════════════╗\n"
                "   🗑️ **TOPIC DELETED** 🔥  \n"
                "╚════════════════════╝\n\n"
                f"💥 विषय: `{t}` अब इतिहास बन गया है।\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔄 अपडेट देखें: /refresh\n"
                "🎯 नया शुरू करें: /start"
            )
            await update.message.reply_text(res, parse_mode="Markdown")
        else: await update.message.reply_text("❌ यह विषय नहीं मिला।")
    except Exception as e: await update.message.reply_text(f"❌ {e}")

# --- क्विज़ लॉजिक ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if not DB_CACHE: sync_db()
    if not DB_CACHE: return await update.message.reply_text("❌ डेटाबेस खाली है!")
    
    # बटन्स को और भी गहरा और स्टाइलिश बनाया
    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "🟠", "💎", "⚡", "🔥"]
    keyboard = []
    for t in sorted(DB_CACHE.keys()):
        keyboard.append([InlineKeyboardButton(f"{random.choice(icons)} {style_txt(t)}", callback_data=t)])
    
    welcome = (
        "╔════════════════════╗\n"
        f"   👑 **{style_txt('PANKAJ QUIZ BOT 2.0')}** 👑\n"
        "╚════════════════════╝\n\n"
        f"{random.choice(SHAYARIS)}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 **अपनी पसंद का विषय चुनें और शुरू करें:** 👇"
    )
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    topic = query.data
    qs = list(DB_CACHE.get(topic, []))
    if not qs: return await query.message.reply_text("⚠️ खाली बटन है!")
    
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
            score = ud['score']; per = int((score/total)*100)
            medal = "🏆" if per >= 80 else "🥇" if per >= 60 else "🥈"
            res = (
                f"╔══════════════════╗\n"
                f"   📊   **{style_txt('REPORT CARD')}**  {medal}  \n"
                f"╚══════════════════╝\n"
                f"📝 विषय:  `{ud['topic']}`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ सही:   `{score}` | ❌ गलत: `{total-score}`\n"
                f"📈 स्कोर:  `{per}%` \n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔥 /start - फिर से खेलें"
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
        cur = ud['idx'] - 1
        if ans.option_ids[0] == ud['qs'][cur]['answer']: ud['score'] += 1
        
        # 0.5 सेकंड का सुपर फास्ट ऑटो-नेक्स्ट
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

    p = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0", port=p, url_path=TOKEN,
        webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}",
        drop_pending_updates=True 
    )

if __name__ == '__main__':
    main()
