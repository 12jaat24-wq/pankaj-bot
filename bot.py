import os
import json
import random
import logging
import asyncio
import httpx
import time
from github import Github
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, MessageHandler, filters, ContextTypes

# --- कॉन्फ़िगरेशन ---
TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = "12jaat24-wq/pankaj-bot"
DB_FILE = "quiz_database.json"
RENDER_URL = "https://pankaj-bot.onrender.com"
GITHUB_URL = f"https://raw.githubusercontent.com/{REPO_NAME}/main/{DB_FILE}"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CACHE = {}

# --- स्टाइलिश फॉन्ट ---
def style_txt(text):
    normal =  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    stylish = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    trans = str.maketrans(normal, stylish)
    return str(text).translate(trans)

SHAYARIS = [
    "✨ *मंज़िल उन्हीं को मिलती है, जिनके सपनों में जान होती है!*",
    "🔥 *हौसले के तरकश में कोशिश का तीर ज़िंदा रख!*",
    "🚀 *जीतने का असली मज़ा तब है, जब दुनिया हारने का इंतज़ार करे!*",
    "💎 *संघर्ष जितना कठिन होगा, जीत उतनी ही शानदार होगी!*"
]

async def sync_db():
    global DB_CACHE
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{GITHUB_URL}?t={int(time.time())}", timeout=15.0)
            if r.status_code == 200:
                DB_CACHE = r.json()
                return True
    except: return False
    return False

# --- 🛠️ जादुई रिसेट कमांड (बॉट को होश में लाने के लिए) ---
async def reset_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⚡ `REBOOTING NEURAL NETWORK...`", parse_mode="Markdown")
    try:
        # 1. पुराना वेबहुक डिलीट करना
        await context.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(1)
        # 2. नया फ्रेश वेबहुक सेट करना
        await context.bot.set_webhook(url=f"{RENDER_URL}/{TOKEN}", drop_pending_updates=True)
        # 3. डेटा सिंक करना
        await sync_db()
        context.user_data.clear()
        
        res = (
            "╔════════════════════╗\n"
            "   ⚡ **SUPER RESET DONE** ⚡   \n"
            "╚════════════════════╝\n\n"
            "✅ **बॉट अब पूरी तरह होश में है!**\n"
            "🚀 सारे जाम साफ़ कर दिए गए हैं।\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👉 अब /start दबाकर धमाका करें!"
        )
        await msg.edit_text(res, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ `Reset Failed: {e}`")

# --- स्टाइलिश रिफ्रेश ---
async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    msg = await update.message.reply_text("📡 `Syncing Vault...`", parse_mode="Markdown")
    if await sync_db():
        total_topics = len(DB_CACHE.keys())
        total_qs = sum(len(v) for v in DB_CACHE.values())
        table = "┌──────────────────┐\n   📋  SUBJECT  |  MCQS   \n├──────────────────┤\n"
        for t, q in list(DB_CACHE.items()):
            short_t = (t[:10] + '..') if len(t) > 10 else t.ljust(12)
            table += f" 🔅 {short_t} | {len(q)} Q\n"
        table += "└──────────────────┘"
        res = (
            "╔════════════════════╗\n"
            "   🔄 **REFRESH SUCCESS** 🔄  \n"
            "╚════════════════════╝\n\n"
            f"```\n{table}\n```\n"
            f"📂 कुल विषय:  `{total_topics}`\n"
            f"📊 कुल सवाल: `{total_qs}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👉 /start दबाएँ!"
        )
        await msg.edit_text(res, parse_mode="Markdown")
    else: await msg.edit_text("❌ `Sync Failed!`")

# --- डेटा अपडेट (The Vault Design) ---
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
        loop = asyncio.get_event_loop()
        def gh_push():
            g = Github(GITHUB_TOKEN); repo = g.get_repo(REPO_NAME); file = repo.get_contents(DB_FILE)
            db = json.loads(file.decoded_content.decode()); db.update(new_data)
            repo.update_file(file.path, "Vault Update", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
        await loop.run_in_executor(None, gh_push)
        await sync_db()
        res = (
            "╔════════════════════╗\n"
            "   📦 **DATABASE UPDATED** 🚀  \n"
            "╚════════════════════╝\n\n"
            "✅ **नया खजाना तिजोरी में जड़ दिया गया!** 🔐\n"
            "👉 लोड करें: /refresh\n"
            "👉 शुरू करें: /start"
        )
        await m.edit_text(res, parse_mode="Markdown")
    except Exception as e: await update.message.reply_text(f"❌ **Error:** `{e}`")

# --- स्टाइलिश डिलीट ---
async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = " ".join(context.args)
    if not t: return await update.message.reply_text("💡 `/delete TopicName` लिखें।")
    try:
        g = Github(GITHUB_TOKEN); repo = g.get_repo(REPO_NAME); file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode())
        if t in db:
            del db[t]
            repo.update_file(file.path, f"Deleted {t}", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
            await sync_db()
            await update.message.reply_text(f"🗑️ **SUCCESS:** `{t}` उड़ गया।")
    except Exception as e: await update.message.reply_text(f"❌ {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if not DB_CACHE: await sync_db()
    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "💎", "⚡", "🔥"]
    keyboard = [[InlineKeyboardButton(f"{random.choice(icons)} {style_txt(t)}", callback_data=t)] for t in sorted(DB_CACHE.keys())]
    # रिसेट बटन भी जोड़ दिया
    keyboard.append([InlineKeyboardButton("⚡ SUPER RESET ⚡", callback_data="super_reset")])
    
    welcome = (
        "╔════════════════════╗\n"
        f"   👑 **{style_txt('PANKAJ QUIZ BOT 2.0')}** 👑\n"
        "╚════════════════════╝\n\n"
        f"{random.choice(SHAYARIS)}\n\n"
        "🎯 **विषय चुनें और धमाका शुरू करें:** 👇"
    )
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == "super_reset":
        # अगर कोई बटन से रिसेट करना चाहे
        class TempUpdate:
            def __init__(self, m): self.message = m
        await reset_bot(TempUpdate(query.message), context)
        return

    topic = query.data
    qs = list(DB_CACHE.get(topic, []))
    if not qs: return 
    random.shuffle(qs)
    context.user_data.update({'qs': qs, 'idx': 0, 'score': 0, 'busy': True, 'topic': topic})
    await query.delete_message()
    await send_q(context, query.message.chat_id)

async def send_q(context, chat_id):
    ud = context.user_data
    idx, qs = ud.get('idx', 0), ud['qs']
    if idx >= len(qs):
        score = ud['score']; total = len(qs); per = int((score/total)*100)
        medal = "🏆" if per >= 80 else "🥇"
        res = (
            f"╔══════════════════╗\n"
            f"   📊   **{style_txt('REPORT CARD')}**  {medal}  \n"
            f"╚══════════════════╝\n"
            f"📝 विषय:  `{ud['topic']}`\n"
            f"✅ सही:   `{score}` | ❌ गलत: `{total-score}`\n"
            f"🏆 स्कोर:  `{per}%` \n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 /start - फिर से खेलें"
        )
        await context.bot.send_message(chat_id, res, parse_mode="Markdown")
        ud.clear(); return

    q = qs[idx]
    bar = "🔹" * (idx + 1) + "▫️" * (len(qs) - idx - 1)
    try:
        await context.bot.send_poll(
            chat_id=chat_id, question=f"✨ ({idx+1}/{len(qs)}) {q['variations'][0]}\n{bar}", 
            options=q['options'], type=Poll.QUIZ, correct_option_id=q['answer'], is_anonymous=False
        )
        ud['idx'] = idx + 1
    except: await asyncio.sleep(1); await send_q(context, chat_id)

async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer; uid = ans.user.id
    ud = context.application.user_data.get(uid)
    if ud and ud.get('busy'):
        if ans.option_ids[0] == ud['qs'][ud['idx']-1]['answer']: ud['score'] += 1
        await asyncio.sleep(0.5)
        class TC:
            def __init__(self, u, b): self.user_data=u; self.bot=b
        await send_q(TC(ud, context.bot), uid)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh_cmd))
    app.add_handler(CommandHandler("reset", reset_bot)) # नयी जादुई कमांड
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(PollAnswerHandler(handle_ans))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_input))

    p = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0", port=p, url_path=TOKEN,
        webhook_url=f"{RENDER_URL}/{TOKEN}",
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
