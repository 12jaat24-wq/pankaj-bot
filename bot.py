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

# लॉगिंग
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CACHE = {}
STYLED_NAMES_CACHE = {}
PAGE_SIZE = 10 # एक बार में कितने बटन दिखेंगे

def style_txt(text):
    if text in STYLED_NAMES_CACHE: return STYLED_NAMES_CACHE[text]
    normal =  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    stylish = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝘫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    trans = str.maketrans(normal, stylish)
    res = str(text).translate(trans)
    STYLED_NAMES_CACHE[text] = res
    return res

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

# बैकग्राउंड में GitHub अपडेट करने के लिए
def push_to_github(data, message="Update"):
    try:
        g = Github(GITHUB_TOKEN)
        r = g.get_repo(REPO_NAME)
        fl = r.get_contents(DB_FILE)
        r.update_file(fl.path, message, json.dumps(data, indent=4, ensure_ascii=False), fl.sha)
        return True
    except Exception as e:
        logger.error(f"GitHub Push Error: {e}")
        return False

# --- बटन बनाने का लॉजिक (Pagination के साथ) ---
def get_topic_keyboard(page=0):
    topics = sorted(list(DB_CACHE.keys()))
    total_pages = (len(topics) + PAGE_SIZE - 1) // PAGE_SIZE
    
    start_idx = page * PAGE_SIZE
    end_idx = start_idx + PAGE_SIZE
    current_topics = topics[start_idx:end_idx]
    
    keyboard = []
    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "💎", "⚡", "🔥"]
    
    for t in current_topics:
        count = len(DB_CACHE[t])
        keyboard.append([InlineKeyboardButton(f"{random.choice(icons)} {style_txt(t)} ({count})", callback_data=f"sel_{t}")])
    
    # नेविगेशन बटन
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=f"page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
        
    keyboard.append([InlineKeyboardButton("🔄 Refresh List", callback_data="page_0")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_CACHE: await sync_db()
    
    text = f"╔════════════════════╗\n   👑 **{style_txt('PANKAJ QUIZ BOT 2.0')}** 👑\n╚════════════════════╝\n\n🎯 **अपना विषय चुनें:**"
    
    if update.message:
        await update.message.reply_text(text, reply_markup=get_topic_keyboard(0), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=get_topic_keyboard(0), parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()

    if data.startswith("page_"):
        page = int(data.split("_")[1])
        await query.edit_message_reply_markup(reply_markup=get_topic_keyboard(page))
    
    elif data.startswith("sel_"):
        topic = data[4:]
        qs = list(DB_CACHE.get(topic, []))
        if not qs: return
        random.shuffle(qs)
        context.user_data.update({'qs': qs, 'idx': 0, 'score': 0, 'topic': topic})
        await query.message.delete()
        await send_q(context, query.message.chat_id)

async def send_q(context, chat_id):
    ud = context.user_data
    idx, qs = ud.get('idx', 0), ud.get('qs', [])
    
    if idx >= len(qs):
        res = f"📊 **RESULT: {ud['topic']}**\n\n✅ Score: {ud['score']}/{len(qs)}\n🔥 /start - फिर से खेलें"
        await context.bot.send_message(chat_id, res, parse_mode="Markdown")
        return

    q = qs[idx]
    await context.bot.send_poll(
        chat_id=chat_id,
        question=f"❓ ({idx+1}/{len(qs)}) {q['variations'][0]}",
        options=q['options'],
        type=Poll.QUIZ,
        correct_option_id=q['answer'],
        is_anonymous=False
    )
    ud['idx'] = idx + 1

async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    ud = context.application.user_data.get(ans.user.id)
    if ud and 'qs' in ud:
        if ans.option_ids[0] == ud['qs'][ud['idx']-1]['answer']:
            ud['score'] += 1
        await asyncio.sleep(0.5) # हल्का सा डिले स्मूथनेस के लिए
        await send_q(context, ans.user.id)

# --- इंस्टेंट डिलीट और अपलोड ---
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.document:
        f = await context.bot.get_file(update.message.document.file_id)
        c = await f.download_as_bytearray()
        json_text = c.decode('utf-8')
    elif update.message.text and "variations" in update.message.text:
        json_text = update.message.text
    else: return

    try:
        new_data = json.loads(json_text.replace('```json', '').replace('```', '').strip())
        DB_CACHE.update(new_data) # इंस्टेंट अपडेट (1 सेकंड के अंदर काम करेगा)
        await update.message.reply_text("✅ **Instant Update Success!**\nGitHub syncing in background...")
        # बैकग्राउंड में GitHub पर भेजें
        asyncio.create_task(asyncio.to_thread(push_to_github, DB_CACHE, "Manual Upload"))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic: return await update.message.reply_text("💡 `/delete TopicName` लिखें।")
    
    if topic in DB_CACHE:
        del DB_CACHE[topic] # इंस्टेंट डिलीट
        await update.message.reply_text(f"🗑️ **{topic}** deleted instantly!")
        asyncio.create_task(asyncio.to_thread(push_to_github, DB_CACHE, f"Deleted {topic}"))
    else:
        await update.message.reply_text("❌ Topic not found in cache.")

# --- मुख्य फ़ंक्शन ---
def main():
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()
    
    app.add_handler(CommandHandler("start", start))
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
