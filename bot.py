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
STYLED_CACHE = {}

def style_txt(text):
    if text in STYLED_CACHE: return STYLED_CACHE[text]
    n = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    s = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    trans = str.maketrans(n, s)
    res = str(text).translate(trans)
    STYLED_CACHE[text] = res
    return res

async def sync_db():
    global DB_CACHE
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{GITHUB_URL}?t={int(time.time())}", timeout=10.0)
            if r.status_code == 200:
                DB_CACHE = r.json()
                STYLED_CACHE.clear()
                return True
    except: return False
    return False

# --- 🚀 सुपर रिसेट (टेलीग्राम का जाम साफ़ करने के लिए) ---
async def reset_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text("⚡ `FLUSHING QUEUE...`", parse_mode="Markdown")
    try:
        # वेबहुक को डिलीट करके फिर से सेट करना (सारे पेंडिंग मैसेज डिलीट हो जाएंगे)
        await context.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(1)
        await context.bot.set_webhook(url=f"{RENDER_URL}/{TOKEN}", drop_pending_updates=True)
        await sync_db()
        context.user_data.clear()
        await m.edit_text("╔════════════════════╗\n   ✨ **BOT REBORN** ✨   \n╚════════════════════╝\n✅ **रास्ता साफ़ है! अब डबल टिक आएगा।**")
    except Exception as e: await m.edit_text(f"❌ Error: {e}")

async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔄 `Syncing...`")
    if await sync_db():
        t, q = len(DB_CACHE.keys()), sum(len(v) for v in DB_CACHE.values())
        res = f"╔════════════════════╗\n   ✅ **REFRESH SUCCESS**   \n╚════════════════════╝\n📂 विषय: `{t}` | 📊 सवाल: `{q}`\n👉 /start दबाएँ।"
        await msg.edit_text(res, parse_mode="Markdown")
    else: await msg.edit_text("❌ Sync Failed!")

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document:
        f = await context.bot.get_file(update.message.document.file_id)
        c = await f.download_as_bytearray(); json_text = c.decode('utf-8')
    elif update.message.text and "variations" in update.message.text:
        json_text = update.message.text
    else: return
    try:
        new_data = json.loads(json_text.replace('```json', '').replace('```', '').strip())
        m = await update.message.reply_text("🌀 `Updating GitHub Vault...`")
        loop = asyncio.get_event_loop()
        def gh_push():
            g = Github(GITHUB_TOKEN); r = g.get_repo(REPO_NAME); fl = r.get_contents(DB_FILE)
            db = json.loads(fl.decoded_content.decode()); db.update(new_data)
            r.update_file(fl.path, "Bot Update", json.dumps(db, indent=4, ensure_ascii=False), fl.sha)
        await loop.run_in_executor(None, gh_push)
        await sync_db(); await m.edit_text("✅ **DATA SAVED!**\n👉 /refresh then /start")
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

# --- हल्का और तेज़ /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # मैसेज मिलते ही तुरंत रसीद भेजना
    context.user_data.clear()
    if not DB_CACHE: await sync_db()
    
    # कीबोर्ड बनाना (Limit 15 topics to avoid lag)
    keyboard = []
    topics = sorted(DB_CACHE.keys())
    for t in topics[:20]: # एक बार में 20 से ज्यादा बटन न दिखाएँ
        keyboard.append([InlineKeyboardButton(f"📖 {style_txt(t)}", callback_data=t)])
    
    keyboard.append([InlineKeyboardButton("⚡ SUPER RESET ⚡", callback_data="super_reset")])
    
    welcome = (
        "╔════════════════════╗\n"
        f"   👑 **{style_txt('PANKAJ QUIZ 2.0')}** 👑\n"
        "╚════════════════════╝\n\n"
        "🎯 **अपनी तैयारी का विषय चुनें:** 👇"
    )
    # वेबहुक को 200 OK भेजने के लिए सबसे तेज़ तरीका
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
        s, t = ud['score'], len(qs); p = int((s/t)*100)
        res = f"📊 **REPORT CARD**\n📝 विषय: `{ud['topic']}`\n✅ सही: `{s}/{t}` ({p}%)\n🔥 /start"
        await context.bot.send_message(chat_id, res, parse_mode="Markdown")
        ud.clear(); return

    q = qs[idx]
    try:
        await context.bot.send_poll(chat_id=chat_id, question=f"✨ ({idx+1}/{len(qs)}) {q['variations'][0]}", options=q['options'], type=Poll.QUIZ, correct_option_id=q['answer'], is_anonymous=False)
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
    # concurrent_updates को हटा दिया ताकि रेंडर क्रैश न हो
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh_cmd))
    app.add_handler(CommandHandler("reset", reset_bot))
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
