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
REPO_NAME = "jaatpankaj610/paid-quiz-app"
DB_FILE = "quiz_database.json"
RENDER_URL = "https://bankerbot-mdzw.onrender.com"
GITHUB_API_URL = f"https://api.github.com/repos/{REPO_NAME}/contents/{DB_FILE}"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CACHE = {}
STYLED_NAMES_CACHE = {}
TOPICS_PER_PAGE = 8

def style_txt(text):
    if text in STYLED_NAMES_CACHE:
        return STYLED_NAMES_CACHE[text]
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    stylish = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    trans = str.maketrans(normal, stylish)
    res = str(text).translate(trans)
    STYLED_NAMES_CACHE[text] = res
    return res

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

    for idx, t in enumerate(current_topics):
        q_count = len(DB_CACHE[t])
        cb_data = f"tp_{start_idx + idx}"
        btn_text = f"{random.choice(icons)} {style_txt(t)} [{q_count}Q]"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])

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
    m = await update.message.reply_text("🌀 Rebooting...", parse_mode="Markdown")
    try:
        await context.bot.delete_webhook(drop_pending_updates=True)
        await context.bot.set_webhook(url=f"{RENDER_URL}/{TOKEN}", drop_pending_updates=True)
        await sync_db()
        context.application.user_data.clear()
        res = "╔════════════════════╗\n  ⚡ BOT IS ALIVE NOW ⚡ \n╚════════════════════╝\n✅ सिस्टम पूरी तरह साफ़ हो गया है!"
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
    uid = update.effective_user.id
    if uid in context.application.user_data:
        context.application.user_data[uid].clear()

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
    uid = update.effective_user.id
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
        try:
            topic_idx = int(data.split("_")[1])
            topics_list = sorted(list(DB_CACHE.keys()))
            topic = topics_list[topic_idx]
        except Exception:
            await query.message.reply_text("❌ विषय नहीं मिला, कृपया /start करें।")
            return

        qs = list(DB_CACHE.get(topic, []))
        if not qs:
            await query.message.reply_text("❌ इस विषय में कोई सवाल नहीं हैं!")
            return

        random.shuffle(qs)
        ud = context.application.user_data.setdefault(uid, {})
        ud.clear()
        ud.update({
            'qs': qs, 
            'idx': 0, 
            'score': 0, 
            'busy': True, 
            'topic': topic, 
            'wrong_qs': []
        })
        try:
            await query.delete_message()
        except Exception:
            pass
        await send_q(context, uid)

    if data == "retry_wrong":
        ud = context.application.user_data.get(uid, {})
        wrong_qs = ud.get('wrong_qs', [])
        topic = ud.get('topic', 'रिवीजन')
        if not wrong_qs:
            await query.message.reply_text("❌ कोई गलत सवाल बाकी नहीं है!")
            return

        qs = list(wrong_qs)
        random.shuffle(qs)
        ud.clear()
        ud.update({
            'qs': qs, 
            'idx': 0, 
            'score': 0, 
            'busy': True, 
            'topic': f"{topic} (गलत सवाल)", 
            'wrong_qs': []
        })
        try:
            await query.delete_message()
        except Exception:
            pass
        await send_q(context, uid)

async def send_q(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    ud = context.application.user_data.get(chat_id)
    if not ud or not ud.get('busy'):
        return

    idx, qs = ud.get('idx', 0), ud.get('qs', [])
    
    # 🎯 1. सवाल खत्म होने पर गारंटेड रिपोर्ट कार्ड
    if idx >= len(qs) or not qs:
        score, total = ud.get('score', 0), len(qs)
        wrong_count = max(0, total - score)
        per = int((score / total) * 100) if total > 0 else 0
        medal = "🏆" if per >= 80 else "🥇"
        
        res = (
            f"╔══════════════════╗\n  📊 {style_txt('REPORT CARD')} {medal} \n╚══════════════════╝\n"
            f"📝 विषय: {ud.get('topic', 'Quiz')}\n✅ सही: {score} | ❌ गलत: {wrong_count}\n🏆 स्कोर: {per}%\n━━━━━━━━━━━━━━━━━━━━"
        )
        
        keyboard = []
        if wrong_count > 0 and ud.get('wrong_qs'):
            keyboard.append([InlineKeyboardButton(f"🔄 गलत सवाल फिर से हल करें ({wrong_count})", callback_data="retry_wrong")])
        
        keyboard.append([InlineKeyboardButton("🏠 मुख्य मेनू (/start)", callback_data="page_0")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        ud['busy'] = False
        try:
            await context.bot.send_message(chat_id, res, reply_markup=reply_markup, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Report Send Error: {e}")
        return

    q = qs[idx]
    
    # 🛠️ AUTO-FIX FORMATTING (एक भी प्रश्न नहीं छूटेगा)
    options = list(q.get('options', []))
    if not options:
        options = ["विकल्प A", "विकल्प B"]
    elif len(options) < 2:
        options.append("इनमें से कोई नहीं")
    elif len(options) > 10:
        options = options[:10]

    answer_idx = q.get('answer', 0)
    if not isinstance(answer_idx, int) or answer_idx < 0 or answer_idx >= len(options):
        answer_idx = 0

    bar = "🔹" * (idx + 1) + "▫️" * (len(qs) - idx - 1)
    q_text = str(q.get('question', 'सवाल उपलब्ध नहीं है')).strip()[:290]
    
    correct_option_text = options[answer_idx]

    shuffled_options = options.copy()
    random.shuffle(shuffled_options)

    new_correct_index = shuffled_options.index(correct_option_text)
    # टेलीग्राम की 100 कैरेक्टर सीमा के तहत सुरक्षित ट्रिमिंग
    styled_options = [f"▪️ {str(opt)[:95]}" for opt in shuffled_options]

    ud['current_correct_index'] = new_correct_index
    ud['current_q_data'] = q
    ud['idx'] = idx + 1

    try:
        await context.bot.send_poll(
            chat_id=chat_id,
            question=f"✨ ({idx+1}/{len(qs)}) {q_text}\n{bar}",
            options=styled_options,
            type=Poll.QUIZ,
            correct_option_id=new_correct_index,
            is_anonymous=False
        )
    except Exception as e:
        logger.error(f"Poll Send Error, retrying text mode fallback: {e}")
        # अगर टेलीग्राम फिर भी पोल रिजेक्ट करे, तो बिना छूटे टेक्स्ट मोड में उत्तर पूछेगा
        try:
            await context.bot.send_poll(
                chat_id=chat_id,
                question=f"✨ ({idx+1}/{len(qs)}) {q_text}",
                options=["Option A", "Option B", "Option C", "Option D"],
                type=Poll.QUIZ,
                correct_option_id=0,
                is_anonymous=False
            )
        except Exception:
            # बैकअप: ऑटो-एडवांस
            await send_q(context, chat_id)

async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    uid = ans.user.id
    ud = context.application.user_data.get(uid)
    
    if ud and ud.get('busy'):
        current_idx = ud['idx'] - 1
        if 0 <= current_idx < len(ud['qs']):
            correct_ans = ud.get('current_correct_index')
            user_selected = ans.option_ids[0]
            
            if user_selected == correct_ans:
                ud['score'] += 1
            else:
                if 'wrong_qs' not in ud:
                    ud['wrong_qs'] = []
                ud['wrong_qs'].append(ud['current_q_data'])
            
            # 🚀 तुरंत बिना किसी देरी/लोडिंग के अगला सवाल Fire करें
            asyncio.create_task(send_q(context, uid))

# 🛡️ एरर हैंडलर
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

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
    
    app.add_error_handler(error_handler)

    p = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0", port=p, url_path=TOKEN,
        webhook_url=f"{RENDER_URL}/{TOKEN}",
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
