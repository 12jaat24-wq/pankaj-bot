import os
import json
import random
import logging
import asyncio
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Poll
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PollAnswerHandler,
    filters,
    ContextTypes
)

# --- कॉन्फ़िगरेशन ---
TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = "12jaat24-wq/pankaj-bot"
DB_FILE = "quiz_database.json"
RENDER_URL = "https://pankaj-bot.onrender.com"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CACHE = {}
STYLED_NAMES_CACHE = {}
POLL_TRACKER = {}  
TOPICS_PER_PAGE = 10 
USER_LOCKS = {}
PING_TASK = None

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
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        async with httpx.AsyncClient() as client:
            ref_res = await client.get(f"https://api.github.com/repos/{REPO_NAME}/git/trees/main?recursive=1", headers=headers, timeout=10.0)
            if ref_res.status_code == 200:
                tree = ref_res.json().get("tree", [])
                file_blob_sha = None
                for item in tree:
                    if item.get("path") == DB_FILE:
                        file_blob_sha = item.get("sha")
                        break
                
                if file_blob_sha:
                    blob_headers = headers.copy()
                    blob_headers["Accept"] = "application/vnd.github.v3.raw"
                    blob_res = await client.get(f"https://api.github.com/repos/{REPO_NAME}/git/blobs/{file_blob_sha}", headers=blob_headers, timeout=15.0)
                    if blob_res.status_code == 200:
                        return json.loads(blob_res.text)
    except Exception as e:
        logger.error(f"GitHub Direct Fetch Error: {e}")
    return {}

async def save_to_github_safely(data_to_save, commit_msg):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        content_str = json.dumps(data_to_save, indent=2, ensure_ascii=False)
        async with httpx.AsyncClient() as client:
            ref_res = await client.get(f"https://api.github.com/repos/{REPO_NAME}/git/ref/heads/main", headers=headers, timeout=10.0)
            if ref_res.status_code != 200: return False
            latest_commit_sha = ref_res.json()["object"]["sha"]

            blob_res = await client.post(
                f"https://api.github.com/repos/{REPO_NAME}/git/blobs",
                headers=headers,
                json={"content": content_str, "encoding": "utf-8"},
                timeout=20.0
            )
            if blob_res.status_code != 201: return False
            blob_sha = blob_res.json()["sha"]

            tree_res = await client.post(
                f"https://api.github.com/repos/{REPO_NAME}/git/trees",
                headers=headers,
                json={
                    "base_tree": latest_commit_sha,
                    "tree": [{"path": DB_FILE, "mode": "100644", "type": "blob", "sha": blob_sha}]
                },
                timeout=10.0
            )
            if tree_res.status_code != 201: return False
            new_tree_sha = tree_res.json()["sha"]

            commit_res = await client.post(
                f"https://api.github.com/repos/{REPO_NAME}/git/commits",
                headers=headers,
                json={"message": commit_msg, "tree": new_tree_sha, "parents": [latest_commit_sha]},
                timeout=10.0
            )
            if commit_res.status_code != 201: return False
            new_commit_sha = commit_res.json()["sha"]

            update_ref = await client.patch(
                f"https://api.github.com/repos/{REPO_NAME}/git/refs/heads/main",
                headers=headers,
                json={"sha": new_commit_sha},
                timeout=10.0
            )
            return update_ref.status_code == 200
    except Exception as e:
        logger.error(f"GitHub Save Failed: {e}")
        return False

async def sync_db():
    global DB_CACHE, STYLED_NAMES_CACHE
    latest_db = await get_latest_github_db()
    if latest_db or latest_db == {}:
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

# --- ऑफिशियल टेलीग्राम QUIZ POLL इंजन (फूल और बिखरने वाला जादू) ---
async def send_next_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    user_data = context.application.user_data.get(user_id)
    if not user_data or not user_data.get('busy'):
        return

    if user_data.get('sending_lock', False):
        return
        
    user_data['sending_lock'] = True

    try:
        idx = user_data.get('idx', 0)
        topic = user_data.get('topic')
        
        if not user_data.get('is_retry') and (topic not in DB_CACHE or not DB_CACHE[topic]):
            user_data['busy'] = False
            await context.bot.send_message(chat_id, "⚠️ डेटाबेस अपडेट हुआ है। /start दबाएं।")
            return

        if user_data.get('is_retry'):
            qs = user_data.get('wrong_qs_pool', [])
        else:
            qs = user_data.get('q_indices', [])

        total_qs = len(qs)

        # क्विज़ समाप्त होने पर रिपोर्ट
        if idx >= total_qs:
            # आखिरी सवाल को भी बिखरने वाले एनिमेशन से डिलीट करें
            old_msg_id = user_data.get('last_msg_id')
            if old_msg_id:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
                except Exception:
                    pass

            score = user_data.get('score', 0)
            wrong_count = total_qs - score
            per = int((score / total_qs) * 100) if total_qs > 0 else 0

            res = (
                f"┏━━━━━━━━━━━━━━━━━━━━━┓\n"
                f"  🏆 {style_txt('QUIZ SCORECARD')} 🏆\n"
                f"┗━━━━━━━━━━━━━━━━━━━━━┛\n\n"
                f"📚 विषय: ❴ {topic} ❵\n"
                f"─────────────────────\n"
                f"🟢 सही उत्तर  : {score}\n"
                f"🔴 गलत उत्तर  : {wrong_count}\n"
                f"📊 कुल स्कोर  : {per}%\n"
                f"─────────────────────\n"
                f"✨ नीचे बटन दबाकर देखें आपने क्या टिक किया था!"
            )

            keyboard = []
            keyboard.append([InlineKeyboardButton("🔍 सवालों का पूरा रीव्यू (Back View)", callback_data="show_review")])
            if wrong_count > 0 and user_data.get('wrong_qs'):
                keyboard.append([InlineKeyboardButton(f"🔄 गलत सवाल हल करें ({wrong_count})", callback_data="retry_wrong")])
            keyboard.append([InlineKeyboardButton("🏠 मुख्य मेनू (/start)", callback_data="go_start")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id, res, reply_markup=reply_markup)
            user_data['busy'] = False
            return

        try:
            if user_data.get('is_retry'):
                q = qs[idx]
            else:
                q_idx = qs[idx]
                q = DB_CACHE[topic][q_idx]
        except Exception:
            user_data['idx'] = idx + 1
            asyncio.create_task(send_next_quiz(context, chat_id, user_id))
            return

        current_q_num = idx + 1
        remaining_qs = total_qs - current_q_num

        completed_blocks = int((current_q_num / total_qs) * 8)
        progress_bar = "🟢" * completed_blocks + "⚪" * (8 - completed_blocks)

        streak = user_data.get('streak', 0)
        streak_tag = f"🔥 x{streak}" if streak >= 2 else "⚡"

        q_question = str(q.get('question', '')).strip()
        
        # Telegram Poll Header (240 अक्षरों तक सेफ)
        q_header = (
            f"Q{current_q_num}/{total_qs} {streak_tag}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{q_question[:210]}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{progress_bar} (बाकी: {remaining_qs})"
        )

        original_options = list(q.get('options', []))
        correct_option_text = original_options[q['answer']]

        shuffled_options = original_options.copy()
        random.shuffle(shuffled_options)
        correct_option_id = shuffled_options.index(correct_option_text)

        # Telegram ऑप्शन लिमिट सेफ (अधिकतम 95 अक्षर)
        safe_options = [str(opt)[:95] for opt in shuffled_options]

        # 💥 जादू: पुराने सवाल को बिखरने (Shatter) वाले प्रभाव के साथ डिलीट करना!
        old_msg_id = user_data.get('last_msg_id')
        if old_msg_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
            except Exception:
                pass

        # 🌸 ऑफिशियल Telegram Quiz Poll (फूल/कंफ़ेटी वाला) भेजना
        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=q_header,
            options=safe_options,
            type=Poll.QUIZ,
            correct_option_id=correct_option_id,
            is_anonymous=False,
            explanation=f"✅ सही उत्तर: {correct_option_text}",
            read_timeout=15,
            write_timeout=15
        )

        # नया मैसेज आईडी स्टोर करें ताकि अगले सवाल पर यह बिखर कर मिट सके
        user_data['last_msg_id'] = message.message_id

        POLL_TRACKER[message.poll.id] = {
            "user_id": user_id,
            "chat_id": chat_id,
            "correct_option_id": correct_option_id,
            "q_data": q,
            "shuffled": safe_options
        }

        user_data['idx'] = idx + 1

    except Exception as e:
        logger.error(f"Quiz Sending Error: {e}")
        if user_data:
            user_data['idx'] = user_data.get('idx', 0) + 1
            asyncio.create_task(send_next_quiz(context, chat_id, user_id))
    finally:
        if user_data:
            user_data['sending_lock'] = False

# --- Poll Answer Handler (फूल + सुपरफ़ास्ट बिखरना) ---
async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id

    if poll_id not in POLL_TRACKER:
        return

    tracker = POLL_TRACKER.pop(poll_id)
    user_id = tracker["user_id"]
    chat_id = tracker["chat_id"]
    correct_option_id = tracker["correct_option_id"]
    selected_option = poll_answer.option_ids[0]

    if user_id not in USER_LOCKS:
        USER_LOCKS[user_id] = asyncio.Lock()

    async with USER_LOCKS[user_id]:
        user_data = context.application.user_data.get(user_id)
        if user_data and user_data.get('busy'):
            is_correct = (selected_option == correct_option_id)
            if is_correct:
                user_data['score'] += 1
                user_data['streak'] = user_data.get('streak', 0) + 1
            else:
                user_data['streak'] = 0
                if 'wrong_qs' not in user_data:
                    user_data['wrong_qs'] = []
                user_data['wrong_qs'].append(tracker["q_data"])

            # हिस्ट्री में सेव करें (ताकि बाद में रीव्यू देख सकें)
            user_data.setdefault('history', []).append({
                'q': tracker["q_data"],
                'shuffled': tracker["shuffled"],
                'correct_id': correct_option_id,
                'user_selected': selected_option,
                'is_correct': is_correct
            })

            # 🌸 ठीक 0.7 सेकंड का वेट: फूल और पटाखे फूटने का पूरा मज़ा मिलेगा!
            await asyncio.sleep(0.7)
            # तुरंत अगला सवाल (जिसमें पुराना सवाल बिखर कर गायब हो जाएगा)
            await send_next_quiz(context, chat_id, user_id)

# --- Commands & Callbacks ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    user_data = context.user_data

    if data == "noop":
        return

    if data == "go_start":
        await start(update, context)
        return

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

    # विषय शुरू करना
    if data.startswith("tp_"):
        topic = data[3:]
        if topic not in DB_CACHE or not DB_CACHE[topic]:
            await query.message.reply_text("❌ विषय में कोई सवाल नहीं हैं!")
            return

        indices = list(range(len(DB_CACHE[topic])))
        random.shuffle(indices)

        user_data.clear()
        user_data.update({
            'topic': topic,
            'q_indices': indices,
            'idx': 0,
            'score': 0,
            'streak': 0,
            'busy': True,
            'is_retry': False,
            'sending_lock': False,
            'last_msg_id': None,
            'history': []
        })

        await query.message.reply_text(f"🚀 **{topic}** शुरू हो रहा है! तैयार हो जाइए...")
        asyncio.create_task(send_next_quiz(context, chat_id, user_id))
        return

    # 🔍 रीव्यू देखने का बटन (आपने क्या टिक किया था)
    if data == "show_review":
        history = user_data.get('history', [])
        if not history:
            await query.message.reply_text("❌ कोई रीव्यू डेटा नहीं मिला!")
            return

        review_chunks = []
        current_chunk = "📋 <b>सवालों का पूरा रीव्यू (Review):</b>\n━━━━━━━━━━━━━━━━━━━━━\n"

        for i, h in enumerate(history, 1):
            q_text = h['q'].get('question', '')[:65]
            user_pick = h['shuffled'][h['user_selected']]
            correct_pick = h['shuffled'][h['correct_id']]
            icon = "✅" if h['is_correct'] else "❌"

            entry = (
                f"<b>Q{i}. {q_text}...</b>\n"
                f"👉 आपका चुनाव: {icon} {user_pick}\n"
                f"🎯 सही उत्तर  : ✅ {correct_pick}\n"
                f"─────────────────────\n"
            )

            if len(current_chunk) + len(entry) > 3800:
                review_chunks.append(current_chunk)
                current_chunk = entry
            else:
                current_chunk += entry

        review_chunks.append(current_chunk)

        for chunk in review_chunks:
            await query.message.reply_text(chunk, parse_mode="HTML")
        return

    # गलत सवाल दोबारा हल करना
    if data == "retry_wrong":
        wrong_qs = user_data.get('wrong_qs', [])
        topic = user_data.get('topic', 'रिवीजन')
        if not wrong_qs:
            await query.message.reply_text("❌ कोई गलत सवाल बाकी नहीं है!")
            return

        qs = list(wrong_qs)
        random.shuffle(qs)
        user_data.clear()
        user_data.update({
            'topic': f"{topic} (रिवीजन)",
            'wrong_qs_pool': qs,
            'idx': 0,
            'score': 0,
            'streak': 0,
            'busy': True,
            'is_retry': True,
            'sending_lock': False,
            'last_msg_id': None,
            'history': []
        })
        asyncio.create_task(send_next_quiz(context, chat_id, user_id))
        return

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if not DB_CACHE:
        await sync_db()
    if not DB_CACHE:
        msg = update.message or update.callback_query.message
        return await msg.reply_text("❌ डेटाबेस खाली है!")

    welcome = (
        "┏━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"   👑 {style_txt('PANKAJ QUIZ BOT')} 👑\n"
        "┗━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"{random.choice(SHAYARIS)}\n\n"
        "🌸 सही होने पर फूल और पटाखे फूटेंगे!\n"
        "💥 पुराना सवाल बिखर कर गायब हो जाएगा!\n\n"
        "🎯 अपनी पसंद का विषय चुनें: 👇"
    )
    markup = build_topics_keyboard(page=0)
    if update.message:
        await update.message.reply_text(welcome, reply_markup=markup)
    else:
        await update.callback_query.message.reply_text(welcome, reply_markup=markup)

async def reset_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text("🌀 Rebooting & Flushing Webhook...")
    try:
        await context.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(1.0)
        await context.bot.set_webhook(
            url=f"{RENDER_URL}/{TOKEN}",
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        await sync_db()
        context.user_data.clear()
        POLL_TRACKER.clear()
        res = "╔════════════════════╗\n  ⚡ BOT IS ALIVE NOW ⚡ \n╚════════════════════╝\n✅ सारे बटन और जाम साफ़ हो गए हैं!"
        await m.edit_text(res)
    except Exception as e:
        await m.edit_text(f"❌ Failed: {e}")

async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📡 Syncing Database...")
    if await sync_db():
        total_topics = len(DB_CACHE.keys())
        total_qs = sum(len(v) for v in DB_CACHE.values())
        res = (
            "╔════════════════════╗\n 🔄 REFRESH SUCCESS 🔄 \n╚════════════════════╝\n"
            f"\n📂 कुल विषय: {total_topics} | 📊 कुल सवाल: {total_qs}\n\n/start पर क्लिक करें।"
        )
        await msg.edit_text(res)
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

    m = await update.message.reply_text("🛡️ Safely Adding Data to GitHub...")
    try:
        clean_text = json_text.replace('```json', '').replace('```', '').strip()
        new_data = json.loads(clean_text)

        global DB_CACHE, STYLED_NAMES_CACHE
        latest_db = await get_latest_github_db()
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
                "╔════════════════════╗\n  🚀 SUCCESSFULLY ADDED! 🚀  \n╚════════════════════╝\n"
                f"📦 कुल सुरक्षित विषय: {total_topics}"
            )
            markup = build_topics_keyboard(page=0)
            await update.message.reply_text("🎯 अपडेटेड विषय सूची:", reply_markup=markup)
        else:
            await m.edit_text("❌ GitHub सेव करने में दिक्कत आई, कृपया दोबारा भेजें।")

    except Exception as e:
        await m.edit_text(f"❌ Data Format Error: {e}")

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = " ".join(context.args).strip()
    if not t:
        return await update.message.reply_text("💡 उपयोग: /delete TopicName")

    m = await update.message.reply_text(f"🛡️ Deleting {t} safely...")
    global DB_CACHE, STYLED_NAMES_CACHE
    latest_db = await get_latest_github_db()
    if not latest_db:
        latest_db = DB_CACHE

    if t in latest_db:
        del latest_db[t]
        saved = await save_to_github_safely(latest_db, f"Deleted Topic: {t}")
        if saved:
            DB_CACHE = latest_db
            STYLED_NAMES_CACHE.clear()
            await m.edit_text(f"✅ DELETED: {t}\n\nबाकी सभी विषय सुरक्षित हैं!")
            markup = build_topics_keyboard(page=0)
            await update.message.reply_text("🎯 अपडेटेड विषय सूची:", reply_markup=markup)
        else:
            await m.edit_text("❌ डिलीट करने में विफल! GitHub कनेक्ट नहीं हुआ।")
    else:
        await m.edit_text(f"❌ विषय '{t}' डेटाबेस में नहीं मिला! कृपया सही नाम लिखें।")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# --- SELF-PING LOOP ---
async def self_ping():
    try:
        await asyncio.sleep(15)
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    await client.get(RENDER_URL, timeout=10.0)
                    logger.info("⚡ Heartbeat Sent: Server Kept Awake!")
                except Exception as e:
                    logger.error(f"Heartbeat Error: {e}")
                await asyncio.sleep(240)
    except asyncio.CancelledError:
        logger.info("Self-ping task cancelled cleanly.")

# --- STARTUP INITIALIZATION ---
async def post_init(application: Application):
    global PING_TASK
    await sync_db()
    PING_TASK = asyncio.create_task(self_ping())

# --- CLEAN SHUTDOWN ---
async def post_shutdown(application: Application):
    global PING_TASK
    if PING_TASK and not PING_TASK.done():
        PING_TASK.cancel()

def main():
    app = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(True)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh_cmd))
    app.add_handler(CommandHandler("reset", reset_bot))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(PollAnswerHandler(handle_poll_answer))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_input))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_input))
    
    app.add_error_handler(error_handler)

    p = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0",
        port=p,
        url_path=TOKEN,
        webhook_url=f"{RENDER_URL}/{TOKEN}",
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
