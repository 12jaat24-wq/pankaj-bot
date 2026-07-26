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
GITHUB_URL = f"https://raw.githubusercontent.com/{REPO_NAME}/main/{DB_FILE}"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CACHE = {}

def style_txt(text):
    normal =  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    stylish = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝘫𝗬𝘡𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    trans = str.maketrans(normal, stylish)
    return str(text).translate(trans)

SHAYARIS = [
    "✨ *मंज़िल उन्हीं को मिलती है, जिनके सपनों में जान होती है,*\n*पंखों से कुछ नहीं होता, हौसलों से उड़ान होती है।*",
    "🔥 *हौसले के तरकश में कोशिश का वो तीर ज़िंदा रख,*\n*हार जा चाहे ज़िंदगी में सब कुछ, मगर फिर से जीतने की उम्मीद ज़िंदा रख।*‍",
    "🚀 *शुरुआत करने के लिए महान होना ज़रूरी नहीं,*\n*लेकिन महान होने के लिए शुरुआत करना ज़रूरी है।*",
    "💎 *मैदान में हारा हुआ इंसान फिर से जीत सकता है,*\n*लेकिन मन से हारा हुआ इंसान कभी नहीं जीत सकता।*"
]

# --- गारंटीड सिंक (Non-Blocking) ---
async def sync_db():
    global DB_CACHE
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{GITHUB_URL}?t={int(time.time())}", timeout=10.0)
            if r.status_code == 200:
                DB_CACHE = r.json()
                return True
    except Exception as e:
        logger.error(f"Sync Error: {e}")
    return False

# --- रिफ्रेश कमांड ---
async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🌀 `Neural Link Syncing...`")
    success = await sync_db()
    if success:
        total_topics = len(DB_CACHE.keys())
        total_qs = sum(len(v) for v in DB_CACHE.values())
        res = f"✅ **SYNC SUCCESSFUL**\n\n📚 Topics: `{total_topics}`\n📝 Questions: `{total_qs}`\n\n/start दबाएँ।"
        await msg.edit_text(res, parse_mode="Markdown")
    else:
        await msg.edit_text("❌ Sync Failed. Check GitHub Token/Repo.")

# --- स्टार्टअप और मेनू (Anti-Jam Logic) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # पुराने पेंडिंग टास्क साफ़ करना
    context.user_data.clear()
    
    if not DB_CACHE:
        await sync_db()

    # बटन्स का निर्माण
    keyboard = []
    topics = sorted(DB_CACHE.keys())
    for i in range(0, len(topics), 2):
        row = [InlineKeyboardButton(f"💠 {style_txt(topics[i])}", callback_data=topics[i])]
        if i + 1 < len(topics):
            row.append(InlineKeyboardButton(f"💠 {style_txt(topics[i+1])}", callback_data=topics[i+1]))
        keyboard.append(row)

    welcome = (
        "╔════════════════════╗\n"
        f"   👑 **{style_txt('PANKAJ QUIZ BOT 2.0')}** 👑\n"
        "╚════════════════════╝\n\n"
        f"{random.choice(SHAYARIS)}\n\n"
        "🎯 **विषय चुनें और शुरू करें:**"
    )
    
    # Send message with a slight delay if bombarded to prevent Telegram Kick
    try:
        await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Start Error: {e}")

# --- क्विज़ शुरू करना ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = query.data
    
    if topic not in DB_CACHE:
        return await query.message.reply_text("❌ डेटा नहीं मिला। /refresh करें।")

    qs = list(DB_CACHE[topic])
    random.shuffle(qs)
    
    # यूजर का डेटा फ्रेश सेट करें
    context.user_data.update({
        'qs': qs, 'idx': 0, 'score': 0, 'topic': topic, 'active': True
    })
    
    await query.delete_message()
    await send_q(context, query.message.chat_id)

# --- सवाल भेजने का फंक्शन (Non-Stop) ---
async def send_q(context, chat_id):
    ud = context.user_data
    if not ud.get('active'): return

    idx, qs = ud['idx'], ud['qs']
    total = len(qs)

    if idx >= total:
        score = ud['score']
        per = int((score/total)*100)
        medal = "🏆" if per >= 80 else "🥇"
        res = (
            f"╔══════════════════╗\n"
            f"   📊   **{style_txt('REPORT CARD')}**  {medal}  \n"
            f"╚══════════════════╝\n"
            f"📝 विषय:  `{ud['topic']}`\n"
            f"✅ सही:   `{score}/{total}` (`{per}%`)\n\n"
            f"🔥 /start - फिर से खेलें"
        )
        await context.bot.send_message(chat_id, res, parse_mode="Markdown")
        ud.clear()
        return

    q = qs[idx]
    bar = "🔹" * (idx + 1) + "▫️" * (total - idx - 1)
    
    try:
        await context.bot.send_poll(
            chat_id=chat_id,
            question=f"✨ ({idx+1}/{total}) {q['variations'][0]}\n{bar}",
            options=q['options'],
            type=Poll.QUIZ,
            correct_option_id=q['answer'],
            is_anonymous=False
        )
        ud['idx'] += 1
    except Exception as e:
        logger.error(f"Poll Error: {e}")
        await asyncio.sleep(1)
        await send_q(context, chat_id)

# --- 0.5 सेकंड ऑटो-नेक्स्ट ---
async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    uid = ans.user.id
    # Application level user data access
    ud = context.application.user_data.get(uid)
    
    if ud and ud.get('active'):
        cur_idx = ud['idx'] - 1
        if ans.option_ids[0] == ud['qs'][cur_idx]['answer']:
            ud['score'] += 1
        
        # 0.5s Fast Next
        await asyncio.sleep(0.5)
        
        # Fake context for send_q
        class MockContext:
            def __init__(self, ud, bot):
                self.user_data = ud
                self.bot = bot
        
        await send_q(MockContext(ud, context.bot), uid)

# --- डेटा अपडेट (GitHub) ---
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Admin check can be added here
    if update.message.document:
        file = await context.bot.get_file(update.message.document.file_id)
        content = await file.download_as_bytearray()
        json_text = content.decode('utf-8')
    elif update.message.text and "variations" in update.message.text:
        json_text = update.message.text
    else: return

    m = await update.message.reply_text("⏳ `Updating Database...`")
    try:
        new_data = json.loads(json_text.replace('```json', '').replace('```', '').strip())
        
        def gh_push():
            g = Github(GITHUB_TOKEN)
            repo = g.get_repo(REPO_NAME)
            f = repo.get_contents(DB_FILE)
            db = json.loads(f.decoded_content.decode())
            db.update(new_data)
            repo.update_file(f.path, "Update", json.dumps(db, indent=4, ensure_ascii=False), f.sha)
        
        await asyncio.get_event_loop().run_in_executor(None, gh_push)
        await sync_db()
        await m.edit_text("✅ **Database Updated!**\n/refresh करें।")
    except Exception as e:
        await m.edit_text(f"❌ Error: `{e}`")

# --- मेन इंजन (The Unstoppable Engine) ---
def main():
    # concurrent_updates=True सबसे जरूरी है जाम से बचने के लिए
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(PollAnswerHandler(handle_ans))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_input))

    # Render Webhook Settings
    PORT = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}",
        drop_pending_updates=True  # पुराने लटके हुए मैसेज साफ़ करें
    )

if __name__ == '__main__':
    main()
