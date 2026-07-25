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

# --- रेंडर Environment Variables ---
TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = "12jaat24-wq/pankaj-bot"
DB_FILE = "quiz_database.json"
GITHUB_URL = f"https://raw.githubusercontent.com/{REPO_NAME}/main/{DB_FILE}"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CACHE = {}

def sync_db():
    global DB_CACHE
    try:
        r = requests.get(f"{GITHUB_URL}?t={int(time.time())}", timeout=20)
        if r.status_code == 200:
            DB_CACHE = r.json()
            return True
    except: return False

# --- डेटा प्रोसेसिंग (Text or File) ---
async def process_and_upload(update, context, json_text):
    try:
        new_data = json.loads(json_text.replace('```json', '').replace('```', '').strip())
        msg = await update.message.reply_text("⚡ **डेटा प्रोसेस हो रहा है...**")
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode())
        db.update(new_data)
        repo.update_file(file.path, "Update via Bot 2.0", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
        sync_db()
        await msg.edit_text("✅ **गिटहब अपडेट सफल!** अब /start दबाएँ।")
    except Exception as e:
        await update.message.reply_text(f"❌ **Error:** {str(e)}")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and "variations" in update.message.text:
        await process_and_upload(update, context, update.message.text)

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if doc.file_name.endswith(('.json', '.txt')):
        file = await context.bot.get_file(doc.file_id)
        content = await file.download_as_bytearray()
        await process_and_upload(update, context, content.decode('utf-8'))

# --- /refresh और /delete ---
async def refresh_cmd(u, c):
    if sync_db(): await u.message.reply_text("🔄 **सिस्टम रिफ्रेश हो गया!**")
async def delete_cmd(u, c):
    if not c.args: return await u.message.reply_text("💡 `/delete Topic_Name` लिखें।")
    t = " ".join(c.args)
    try:
        g = Github(GITHUB_TOKEN); repo = g.get_repo(REPO_NAME); file = repo.get_contents(DB_FILE)
        db = json.loads(file.decoded_content.decode())
        if t in db:
            del db[t]
            repo.update_file(file.path, f"Deleted {t}", json.dumps(db, indent=4, ensure_ascii=False), file.sha)
            sync_db(); await u.message.reply_text(f"🗑️ **'{t}' उड़ गया!**")
    except Exception as e: await u.message.reply_text(f"❌ {e}")

# --- क्विज़ लॉजिक (पंकज क्विज़ पोल 2.0) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_CACHE: sync_db()
    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "💎", "🔥", "🌈", "⚡", "🏆"]
    keyboard = [[InlineKeyboardButton(f"{random.choice(icons)} {t}", callback_data=t)] for t in DB_CACHE.keys()]
    welcome = (
        "╔════════════════╗\n"
        "   ✨ **पंकज क्विज़ पोल 2.0** ✨\n"
        "╚════════════════╝\n\n"
        "🚀 **अपनी तैयारी को नई उड़ान दें!**\n"
        "🎯 अपना विषय चुनें और शुरू करें: 👇"
    )
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "next_q":
        user_id = query.from_user.id
        ud = context.application.user_data.get(user_id)
        if ud and ud.get('busy'):
            try: await query.delete_message()
            except: pass
            class TC: 
                def __init__(self, u, b): self.user_data=u; self.bot=b
            await send_q(TC(ud, context.bot), user_id)
        return
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
        score = ud['score']
        per = int((score/total)*100)
        medal = "🏆" if per >= 80 else "🥇" if per >= 60 else "🥈" if per >= 40 else "🥉"
        
        # स्टाइलिश स्कोर कार्ड टेबल
        res = (
            f"╔══════════════════╗\n"
            f"   📊 **आपका रिपोर्ट कार्ड** {medal}  \n"
            f"╚══════════════════╝\n"
            f"📝 **विषय:** `{ud['topic']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ **सही जवाब:**  `{score}`\n"
            f"❌ **गलत जवाब:**  `{total - score}`\n"
            f"📈 **कुल सवाल:**  `{total}`\n"
            f"🏆 **सफलता दर:** `{per}%` \n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💫 *तैयारी जारी रखें!* /start"
        )
        await context.bot.send_message(chat_id, res, parse_mode="Markdown")
        ud['busy'] = False
        return

    q = qs[idx]
    bar = "🔹" * (idx + 1) + "▫️" * (total - idx - 1)
    await context.bot.send_poll(
        chat_id=chat_id, 
        question=f"✨ ({idx+1}/{total}) {q['variations'][0]}\n{bar}", 
        options=q['options'], 
        type=Poll.QUIZ, 
        correct_option_id=q['answer'], 
        is_anonymous=False
    )
    ud['idx'] = idx + 1
    
    # "Next" बटन को बैकअप के तौर पर नीचे एक छोटे मैसेज में रखना (जरूरत पड़ने पर)
    kb = [[InlineKeyboardButton("⏭️ अगला सवाल", callback_data="next_q")]]
    await context.bot.send_message(chat_id, "⏱️ *ऑटो-नेक्स्ट लोड हो रहा है...*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    uid = ans.user.id
    ud = context.application.user_data.get(uid)
    if ud and ud.get('busy'):
        if ans.option_ids[0] == ud['qs'][ud['idx']-1]['answer']: ud['score'] += 1
        
        # यहाँ असली जादू: 0.5 सेकंड का सुपर फास्ट ऑटो-नेक्स्ट
        await asyncio.sleep(0.5)
        
        # पुराना "Next" बटन मैसेज डिलीट करना ताकि स्क्रीन साफ़ रहे
        # (यह थोड़ा मुश्किल है बिना मैसेज आईडी के, पर हमने अगला पोल भेजकर इसे रिप्लेस कर देना है)
        
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
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_msg))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))

    p = int(os.environ.get("PORT", 10000))
    app.run_webhook(listen="0.0.0.0", port=p, url_path=TOKEN, webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}")

if __name__ == '__main__':
    main()
