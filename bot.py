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

# लॉगिंग सेटअप
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CACHE = {}
STYLED_NAMES_CACHE = {} # नया: फॉन्ट स्टाइल को पहले से सेव रखने के लिए

# --- सुपर स्टाइलिश फॉन्ट (𝗣𝗔𝗡𝗞𝗔𝗝 𝗤𝗨𝗜𝗭) ---
def style_txt(text):
    if text in STYLED_NAMES_CACHE: return STYLED_NAMES_CACHE[text]
    normal =  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    stylish = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    trans = str.maketrans(normal, stylish)
    res = str(text).translate(trans)
    STYLED_NAMES_CACHE[text] = res # कैश में डालना ताकि बॉट स्लो न हो
    return res

async def sync_db():
    global DB_CACHE, STYLED_NAMES_CACHE
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{GITHUB_URL}?t={int(time.time())}", timeout=15.0)
            if r.status_code == 200:
                DB_CACHE = r.json()
                STYLED_NAMES_CACHE.clear() # पुराना कैश साफ़ करें
                return True
    except: return False
    return False

SHAYARIS = [
    "✨ *मंज़िल उन्हीं को मिलती है, जिनके सपनों में जान होती है!*",
    "🔥 *हौसले के तरकश में कोशिश का तीर ज़िंदा रख!*",
    "💎 *संघर्ष जितना कठिन होगा, जीत उतनी ही शानदार होगी!*"
]

# --- ⚡ जादुई रिसेट कमांड ---
async def reset_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text("🌀 `Hard Rebooting...`", parse_mode="Markdown")
    try:
        await context.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(1)
        await context.bot.set_webhook(url=f"{RENDER_URL}/{TOKEN}", drop_pending_updates=True)
        await sync_db()
        context.user_data.clear()
        res = "╔════════════════════╗\n   ⚡ **BOT IS ALIVE NOW** ⚡   \n╚════════════════════╝\n✅ **सारे जाम साफ़ हो गए हैं!**"
        await m.edit_text(res, parse_mode="Markdown")
    except Exception as e: await m.edit_text(f"❌ `Failed: {e}`")

# --- स्टाइलिश रिफ्रेश ---
async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📡 `Syncing Database...`", parse_mode="Markdown")
    if await sync_db():
        total_topics = len(DB_CACHE.keys())
        total_qs = sum(len(v) for v in DB_CACHE.values())
        table = "┌──────────────────┐\n   📦  MY INVENTORY   \n├──────────────────┤\n"
        for t, q in list(DB_CACHE.items())[:15]:
            table += f" 🔅 {t[:10]} | {len(q)}Q\n"
        table += "└──────────────────┘"
        res = (
            "╔════════════════════╗\n   🔄 **REFRESH SUCCESS** 🔄  \n╚════════════════════╝\n"
            f"```\n{table}\n```\n📂 विषय: `{total_topics}` | 📊 सवाल: `{total_qs}`"
        )
        await msg.edit_text(res, parse_mode="Markdown")
    else: await msg.edit_text("❌ `Sync Failed!`")

# --- डेटा अपलोड ---
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document:
        f = await context.bot.get_file(update.message.document.file_id)
        c = await f.download_as_bytearray(); json_text = c.decode('utf-8')
    elif update.message.text and "variations" in update.message.text:
        json_text = update.message.text
    else: return

    try:
        new_data = json.loads(json_text.replace('```json', '').replace('```', '').strip())
        m = await update.message.reply_text("🌀 `Processing Vault...`", parse_mode="Markdown")
        loop = asyncio.get_event_loop()
        def gh_push():
            g = Github(GITHUB_TOKEN); r = g.get_repo(REPO_NAME); fl = r.get_contents(DB_FILE)
            db = json.loads(fl.decoded_content.decode()); db.update(new_data)
            r.update_file(fl.path, "Bot Sync", json.dumps(db, indent=4, ensure_ascii=False), fl.sha)
        await loop.run_in_executor(None, gh_push)
        await sync_db()
        await m.edit_text("╔════════════════════╗\n   ✅ **VAULT UPDATED** 🚀  \n╚════════════════════╝\n👉 /refresh then /start", parse_mode="Markdown")
    except Exception as e: await update.message.reply_text(f"❌ `Error: {e}`")

# --- स्टाइलिश डिलीट ---
async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = " ".join(context.args)
    if not t: return await update.message.reply_text("💡 `/delete TopicName` लिखें।")
    try:
        g = Github(GITHUB_TOKEN); r = g.get_repo(REPO_NAME); fl = r.get_contents(DB_FILE)
        db = json.loads(fl.decoded_content.decode())
        if t in db:
            del db[t]; r.update_file(fl.path, f"Deleted {t}", json.dumps(db, indent=4, ensure_ascii=False), fl.sha)
            await sync_db(); await update.message.reply_text(f"🗑️ **REMOVED:** `{t}`")
    except Exception as e: await update.message.reply_text(f"❌ {e}")

# --- क्विज़ लॉजिक (सुपर फास्ट बटन जेनरेशन) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # सबसे पहला काम: टेलीग्राम को 'OK' भेजना ताकि गोल घेरा न आए
    if update.message: await update.message.reply_chat_action("typing")
    context.user_data.clear()
    
    if not DB_CACHE: await sync_db()
    if not DB_CACHE: return await update.message.reply_text("❌ डेटाबेस खाली है!")
    
    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "💎", "⚡", "🔥"]
    keyboard = []
    # बटन्स को बैच में बनाना ताकि लैग न हो
    sorted_topics = sorted(DB_CACHE.keys())
    for t in sorted_topics:
        keyboard.append([InlineKeyboardButton(f"{random.choice(icons)} {style_txt(t)}", callback_data=t)])
    
    keyboard.append([InlineKeyboardButton("⚡ SUPER RESET ⚡", callback_data="super_reset")])
    
    welcome = (
        "╔════════════════════╗\n"
        f"   👑 **{style_txt('PANKAJ QUIZ BOT 2.0')}** 👑\n"
        "╚════════════════════╝\n\n"
        f"{random.choice(SHAYARIS)}\n\n"
        "🎯 **अपनी पसंद का विषय चुनें:** 👇"
    )
    # वेबहुक को तुरंत जवाब देने के लिए reply_text
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == "super_reset":
        class TU:
            def __init__(self, m): self.message = m
        await reset_bot(TU(query.message), context); return

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
        score, total = ud['score'], len(qs); per = int((score/total)*100)
        medal = "🏆" if per >= 80 else "🥇"
        res = (
            f"╔══════════════════╗\n   📊   **{style_txt('REPORT CARD')}**  {medal}  \n╚══════════════════╝\n"
            f"📝 विषय: `{ud['topic']}`\n✅ सही: `{score}` | ❌ गलत: `{total-score}`\n🏆 स्कोर: `{per}%` \n━━━━━━━━━━━━━━━━━━━━\n🔥 /start - फिर से खेलें"
        )
        await context.bot.send_message(chat_id, res, parse_mode="Markdown")
        ud.clear(); return

    q = qs[idx]
    bar = "🔹" * (idx + 1) + "▫️" * (len(qs) - idx - 1)
    try:
        await context.bot.send_poll(chat_id=chat_id, question=f"✨ ({idx+1}/{len(qs)}) {q['variations'][0]}\n{bar}", options=q['options'], type=Poll.QUIZ, correct_option_id=q['answer'], is_anonymous=False)
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
    # --- सुरक्षा चक्र 1: Concurrent Updates (एक साथ कई काम संभालना) ---
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh_cmd))
    app.add_handler(CommandHandler("reset", reset_bot))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(PollAnswerHandler(handle_ans))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_input))

    # --- सुरक्षा चक्र 2: Webhook with Queue Clearance ---
    p = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0", port=p, url_path=TOKEN,
        webhook_url=f"{RENDER_URL}/{TOKEN}",
        drop_pending_updates=True # सुरक्षा चक्र 3: पुराना जाम साफ़ करना
    )

if __name__ == '__main__':
    main()
