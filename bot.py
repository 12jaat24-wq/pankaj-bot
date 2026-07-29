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
GITHUB_API_URL = f"https://api.github.com/repos/{REPO_NAME}/contents/{DB_FILE}"

# लॉगिंग सेटअप
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CACHE = {}
STYLED_NAMES_CACHE = {}
TOPICS_PER_PAGE = 10 

# --- स्टाइलिश फॉन्ट ---
def style_txt(text):
    if text in STYLED_NAMES_CACHE:
        return STYLED_NAMES_CACHE[text]
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    stylish = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    trans = str.maketrans(normal, stylish)
    res = str(text).translate(trans)
    STYLED_NAMES_CACHE[text] = res
    return res

# 🛡️ SAFE FETCH & SAVE FOR GITHUB
async def get_latest_github_db():
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{GITHUB_API_URL}?t={int(time.time())}", headers=headers, timeout=10.0)
            if res.status_code == 200:
                data = res.json()
                sha = data["sha"]
                content = base64.b64decode(data["content"]).decode('utf-8')
                return json.loads(content), sha
    except Exception as e:
        logger.error(f"GitHub Fetch Failed: {e}")
    return {}, None

async def save_to_github_safely(data_to_save, commit_msg):
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        _, sha = await get_latest_github_db()
        content_str = json.dumps(data_to_save, indent=4, ensure_ascii=False)
        base64_content = base64.b64encode(content_str.encode('utf-8')).decode('utf-8')

        put_data = {"message": commit_msg, "content": base64_content}
        if sha:
            put_data["sha"] = sha

        async with httpx.AsyncClient() as client:
            res = await client.put(GITHUB_API_URL, headers=headers, json=put_data, timeout=12.0)
            return res.status_code in [200, 201]
    except Exception as e:
        logger.error(f"GitHub Save Failed: {e}")
        return False

async def sync_db():
    global DB_CACHE, STYLED_NAMES_CACHE
    latest_db, _ = await get_latest_github_db()
    if latest_db:
        DB_CACHE = latest_db
        STYLED_NAMES_CACHE.clear()
        return True
    return False

SHAYARIS = [
    "✨ मंज़िल उन्हीं को मिलती है, जिनके सपनों में जान होती है!",
    "🔥 हौसले के तरकश में कोशिश का तीर ज़िंदा रख!",
    "💎 संघर्ष जितना कठिन होगा, जीत उतनी ही शानदार होगी!"
]

def build_topics_keyboard(page: int = 0):
    topics = sorted(list(DB_CACHE.keys()))
    if not topics:
        return InlineKeyboardMarkup([[InlineKeyboardButton("❌ कोई विषय नहीं मिला", callback_data="noop")]])

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

# --- Commands ---
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
    elif update.message.text and ("options" in update.message.text or "question" in update.message.text):
        json_text = update.message.text
    else:
        return

    m = await update.message.reply_text("🛡️ `Safely Adding Data to GitHub...`", parse_mode="Markdown")
    try:
        clean_text = json_text.replace('```json', '').replace('```', '').strip()
        new_data = json.loads(clean_text)

        global DB_CACHE, STYLED_NAMES_CACHE
        latest_db, _ = await get_latest_github_db()
        if not latest_db:
            latest_db = DB_CACHE

        for topic, questions in new_data.items():
            if topic in latest_db:
                latest_db[topic].extend(questions)
            else:
                latest_db[topic] = questions

        saved = await save_to_github_safely(latest_db, "Safe Add JSON")
        if saved:
            DB_CACHE = latest_db
            STYLED_NAMES_CACHE.clear()
            total_topics = len(DB_CACHE.keys())
            await m.edit_text(
                "╔════════════════════╗\n  🚀 **SUCCESSFULLY ADDED!** 🚀  \n╚════════════════════╝\n"
                f"📦 कुल सुरक्षित विषय: **{total_topics}**", parse_mode="Markdown"
            )
            markup = build_topics_keyboard(page=0)
            await update.message.reply_text("🎯 **अपडेटेड विषय सूची:**", reply_markup=markup)
        else:
            await m.edit_text("❌ GitHub सेव करने में दिक्कत आई, कृपया दोबारा भेजें।")

    except Exception as e:
        await m.edit_text(f"❌ `Data Format Error: {e}`", parse_mode="Markdown")

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = " ".join(context.args).strip()
    if not t:
        return await update.message.reply_text("💡 उपयोग: `/delete TopicName`", parse_mode="Markdown")

    m = await update.message.reply_text(f"🛡️ Deleting `{t}` safely...", parse_mode="Markdown")
    global DB_CACHE, STYLED_NAMES_CACHE
    latest_db, _ = await get_latest_github_db()
    if not latest_db:
        latest_db = DB_CACHE

    if t in latest_db:
        del latest_db[t]
        saved = await save_to_github_safely(latest_db, f"Deleted Topic: {t}")
        if saved:
            DB_CACHE = latest_db
            STYLED_NAMES_CACHE.clear()
            await m.edit_text(f"✅ **DELETED:** `{t}`\n\nबाकी सभी विषय सुरक्षित हैं!", parse_mode="Markdown")
            markup = build_topics_keyboard(page=0)
            await update.message.reply_text("🎯 **अपडेटेड विषय सूची:**", reply_markup=markup)
        else:
            await m.edit_text("❌ डिलीट करने में विफल! GitHub कनेक्ट नहीं हुआ।")
    else:
        await m.edit_text(f"❌ विषय `{t}` डेटाबेस में नहीं मिला! कृपया सही नाम लिखें।")

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
    try:
        await query.answer()
    except Exception:
        pass

    data = query.data
    if data == "noop": return

    if data == "super_reset":
        class TU:
            def __init__(self, m): self.message = m
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
        if topic not in DB_CACHE:
            await query.message.reply_text("❌ यह विषय डिलीट हो चुका है! /start करें।")
            return

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
    
    # 📌 1. मूल प्रश्न (Original Question Text)
    q_text = q.get('question', '').strip()

    # 🎲 2. स्मार्ट ऑप्शन शफलिंग (हर बार ऑप्शन्स की जगह बदलना)
    original_options = q['options'].copy()
    correct_option_text = original_options[q['answer']] # सही उत्तर का टेक्स्ट निकाल लिया

    # ऑप्शन्स को रैंडम शफल करना
    shuffled_options = original_options.copy()
    random.shuffle(shuffled_options)

    # नया सही उत्तर किस इंडेक्स पर गया, वो ट्रैक करना
    new_correct_index = shuffled_options.index(correct_option_text)
    
    # ऑप्शन्स के आगे डिज़ाइन जोड़ना
    styled_options = [f"▪️ {opt}" for opt in shuffled_options]

    # यूज़र डेटा में नया सही इंडेक्स सेव करना
    ud['current_correct_index'] = new_correct_index

    try:
        await context.bot.send_poll(
            chat_id=chat_id,
            question=f"✨ ({idx+1}/{len(qs)}) {q_text}\n{bar}",
            options=styled_options,
            type=Poll.QUIZ,
            correct_option_id=new_correct_index,
            is_anonymous=False
        )
        ud['idx'] = idx + 1
    except Exception as e:
        logger.error(f"Poll Send Error: {e}")
        await asyncio.sleep(0.5)
        await send_q(context, chat_id)

async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    uid = ans.user.id
    ud = context.application.user_data.get(uid)
    
    if ud and ud.get('busy'):
        current_idx = ud['idx'] - 1
        if 0 <= current_idx < len(ud['qs']):
            correct_ans = ud.get('current_correct_index')
            if ans.option_ids[0] == correct_ans:
                ud['score'] += 1
            await asyncio.sleep(0.2)
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
