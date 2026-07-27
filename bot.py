import os
import json
import random
import logging
import asyncio
import httpx
import time
import base64
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# --- कॉन्फ़िगरेशन ---
TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = "12jaat24-wq/pankaj-bot"
DB_FILE = "quiz_database.json"
RENDER_URL = "https://pankaj-bot.onrender.com"
GITHUB_URL = f"https://raw.githubusercontent.com/{REPO_NAME}/main/{DB_FILE}"
GITHUB_API_URL = f"https://api.github.com/repos/{REPO_NAME}/contents/{DB_FILE}"

# लॉगिंग सेटअप
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CACHE = {}
STYLED_NAMES_CACHE = {}
TOPICS_PER_PAGE = 10  # प्रति पेज बटन्स की संख्या

# --- सुपर स्टाइलिश फॉन्ट ---
def style_txt(text):
    if text in STYLED_NAMES_CACHE:
        return STYLED_NAMES_CACHE[text]
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    stylish = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    trans = str.maketrans(normal, stylish)
    res = str(text).translate(trans)
    STYLED_NAMES_CACHE[text] = res
    return res

# --- फास्ट गिटहब और डेटाबेस सिंक ---
async def sync_db():
    global DB_CACHE, STYLED_NAMES_CACHE
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{GITHUB_URL}?t={int(time.time())}", timeout=5.0)
            if r.status_code == 200:
                DB_CACHE = r.json()
                STYLED_NAMES_CACHE.clear()
                return True
    except Exception as e:
        logger.error(f"Sync failed: {e}")
    return False

async def update_github_file(new_db, commit_msg):
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    async with httpx.AsyncClient() as client:
        res = await client.get(GITHUB_API_URL, headers=headers, timeout=10.0)
        sha = res.json()["sha"] if res.status_code == 200 else None

        content_str = json.dumps(new_db, indent=4, ensure_ascii=False)
        base64_content = base64.b64encode(content_str.encode('utf-8')).decode('utf-8')

        data = {
            "message": commit_msg,
            "content": base64_content
        }
        if sha:
            data["sha"] = sha

        await client.put(GITHUB_API_URL, headers=headers, json=data, timeout=10.0)

SHAYARIS = [
    "✨ मंज़िल उन्हीं को मिलती है, जिनके सपनों में जान होती है!",
    "🔥 हौसले के तरकश में कोशिश का तीर ज़िंदा रख!",
    "💎 संघर्ष जितना कठिन होगा, जीत उतनी ही शानदार होगी!"
]

# --- कीबोर्ड जेनरेशन ---
def build_topics_keyboard(page: int = 0):
    topics = sorted(list(DB_CACHE.keys()))
    if not topics:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔄 डेटाबेस खाली है - Refresh", callback_data="noop")]])

    total_topics = len(topics)
    total_pages = max(1, (total_topics + TOPICS_PER_PAGE - 1) // TOPICS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))

    start_idx = page * TOPICS_PER_PAGE
    end_idx = start_idx + TOPICS_PER_PAGE
    current_topics = topics[start_idx:end_idx]

    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "💎", "⚡", "🔥"]
    keyboard = []

    for t in current_topics:
        q_count = len(DB_CACHE[t])
        btn_text = f"{random.choice(icons)} {style_txt(t)} [{q_count}Q]"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"tp_{t}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{page+1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("⚡ SUPER RESET ⚡", callback_data="super_reset")])
    return InlineKeyboardMarkup(keyboard)

# --- कमांड्स ---

async def reset_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text("🌀 Hard Rebooting...", parse_mode="Markdown")
    try:
        await context.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(0.3)
        await context.bot.set_webhook(url=f"{RENDER_URL}/{TOKEN}", drop_pending_updates=True)
        await sync_db()
        context.user_data.clear()
        res = "╔════════════════════╗\n  ⚡ BOT IS ALIVE NOW ⚡ \n╚════════════════════╝\n✅ सारे जाम साफ़ हो गए हैं!"
        await m.edit_text(res, parse_mode="Markdown")
    except Exception as e:
        await m.edit_text(f"❌ Failed: {e}")

async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📡 Syncing Database...", parse_mode="Markdown")
    if await sync_db():
        total_topics = len(DB_CACHE.keys())
        total_qs = sum(len(v) for v in DB_CACHE.values())
        res = (
            "╔════════════════════╗\n 🔄 REFRESH SUCCESS 🔄 \n╚════════════════════╝\n"
            f"\n📂 विषय: {total_topics} | 📊 सवाल: {total_qs}\n\n/start पर क्लिक करें।"
        )
        await msg.edit_text(res, parse_mode="Markdown")
    else:
        await msg.edit_text("❌ Sync Failed!")

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    json_text = ""
    if update.message.document:
        f = await context.bot.get_file(update.message.document.file_id)
        c = await f.download_as_bytearray()
        json_text = c.decode('utf-8')
    elif update.message.text and ("variations" in update.message.text or "options" in update.message.text):
        json_text = update.message.text
    else:
        return

    m = await update.message.reply_text("🌀 `Safely Merging Vault...`", parse_mode="Markdown")
    try:
        clean_text = json_text.replace('```json', '').replace('```', '').strip()
        new_data = json.loads(clean_text)

        global DB_CACHE
        for topic, questions in new_data.items():
            if topic in DB_CACHE:
                DB_CACHE[topic].extend(questions)
            else:
                DB_CACHE[topic] = questions

        # बैकग्राउंड में Async GitHub पुश
        asyncio.create_task(update_github_file(DB_CACHE, "Safe Merge Update"))

        total_topics = len(DB_CACHE.keys())
        await m.edit_text(
            "╔════════════════════╗\n"
            "  ✅ **INSTANT UPLOAD SUCCESS** 🚀  \n"
            "╚════════════════════╝\n"
            f"📦 अब कुल विषय: **{total_topics}**\n\n"
            "👉 तुरंत देखें: /start",
            parse_mode="Markdown"
        )
    except Exception as e:
        await m.edit_text(f"❌ `Data Format Error: {e}`", parse_mode="Markdown")

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = " ".join(context.args).strip()
    if not t:
        return await update.message.reply_text("💡 उपयोग: `/delete TopicName`", parse_mode="Markdown")

    m = await update.message.reply_text(f"🗑️ Deleting `{t}`...", parse_mode="Markdown")
    global DB_CACHE
    if t in DB_CACHE:
        del DB_CACHE[t]  # तुरंत Memory से डिलीट
        STYLED_NAMES_CACHE.clear()
        
        # बैकग्राउंड में GitHub से हटाना
        asyncio.create_task(update_github_file(DB_CACHE, f"Deleted {t}"))
        
        await m.edit_text(f"✅ **INSTANTLY REMOVED:** `{t}`\n\n/start चलाकर बटन देखें।", parse_mode="Markdown")
    else:
        await m.edit_text(f"❌ विषय `{t}` डेटाबेस में नहीं मिला!", parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_chat_action("typing")
    context.user_data.clear()

    if not DB_CACHE:
        await sync_db()
    if not DB_CACHE:
        return await update.message.reply_text("❌ डेटाबेस खाली है!")

    welcome = (
        "╔════════════════════╗\n"
        f"   👑 **{style_txt('PANKAJ QUIZ BOT 2.0')}** 👑\n"
        "╚════════════════════╝\n\n"
        f"{random.choice(SHAYARIS)}\n\n"
        "🎯 **अपनी पसंद का विषय चुनें:** 👇"
    )
    markup = build_topics_keyboard(page=0)
    await update.message.reply_text(welcome, reply_markup=markup, parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # ⚡ 1. तुरंत Answer करना ताकि बटन का घूमना/अटकना बंद हो जाए
    try:
        await query.answer()
    except Exception:
        pass

    data = query.data
    if data == "noop":
        return

    if data == "super_reset":
        class TU:
            def __init__(self, m):
                self.message = m
        await reset_bot(TU(query.message), context)
        return

    if data.startswith("page_"):
        page = int(data.split("_")[1])
        markup = build_topics_keyboard(page=page)
        try:
            await query.edit_message_reply_markup(reply_markup=markup)
        except Exception:
            pass
        return

    if data.startswith("tp_"):
        topic = data[3:]
        qs = list(DB_CACHE.get(topic, []))
        if not qs:
            await query.message.reply_text("❌ इस विषय में कोई सवाल नहीं हैं!")
            return
        random.shuffle(qs)
        context.user_data.update({'qs': qs, 'idx': 0, 'score': 0, 'busy': True, 'topic': topic})
        try:
            await query.delete_message()
        except Exception:
            pass
        await send_q(context, query.message.chat_id)

async def send_q(context, chat_id):
    ud = context.user_data
    if not ud or not ud.get('busy'):
        return

    idx, qs = ud.get('idx', 0), ud['qs']
    if idx >= len(qs):
        score, total = ud['score'], len(qs)
        per = int((score / total) * 100) if total > 0 else 0
        medal = "🏆" if per >= 80 else "🥇"
        res = (
            f"╔══════════════════╗\n  📊 {style_txt('REPORT CARD')} {medal} \n╚══════════════════╝\n"
            f"📝 विषय: {ud['topic']}\n✅ सही: {score} | ❌ गलत: {total - score}\n🏆 स्कोर: {per}%\n━━━━━━━━━━━━━━━━━━━━\n🔥 /start - फिर से खेलें"
        )
        await context.bot.send_message(chat_id, res, parse_mode="Markdown")
        ud.clear()
        return

    q = qs[idx]
    bar = "🔹" * (idx + 1) + "▫️" * (len(qs) - idx - 1)
    q_text = q['variations'][0] if isinstance(q.get('variations'), list) and len(q['variations']) > 0 else q.get('question', '')

    try:
        await context.bot.send_poll(
            chat_id=chat_id,
            question=f"✨ ({idx+1}/{len(qs)}) {q_text}\n{bar}",
            options=q['options'],
            type=Poll.QUIZ,
            correct_option_id=q['answer'],
            is_anonymous=False
        )
        ud['idx'] = idx + 1
    except Exception as e:
        logger.error(f"Poll Send Error: {e}")
        # क्विज़ न रुके इसलिए 0.5 सेकंड बाद अगला प्रयास
        await asyncio.sleep(0.5)
        await send_q(context, chat_id)

async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    uid = ans.user.id
    ud = context.application.user_data.get(uid)
    if ud and ud.get('busy'):
        current_idx = ud['idx'] - 1
        if 0 <= current_idx < len(ud['qs']):
            if ans.option_ids[0] == ud['qs'][current_idx]['answer']:
                ud['score'] += 1
            await asyncio.sleep(0.2)  # तेज़ रिस्पांस के लिए घटाया गया टाइमर
            await send_q(context, uid)

def main():
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh_cmd))
    app.add_handler(CommandHandler("reset", reset_bot))
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
