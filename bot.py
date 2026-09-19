from aiohttp import web
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
from telegram.error import RetryAfter, TimedOut, NetworkError

# --- कॉन्फ़िगरेशन ---
TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = os.environ.get("REPO_NAME", "12jaat24-wq/pankaj-bot")  # Env से उठाने का विकल्प
DB_FILE = "quiz_database.json"

# Render URL को पर्यावरण (Environment) से डायनामिक रूप से प्राप्त करें
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://pankaj-bot.onrender.com").rstrip("/")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CACHE = {}
STYLED_NAMES_CACHE = {}
KEYBOARD_CACHE = {}
POLL_TRACKER = {}  
TOPICS_PER_PAGE = 10 

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
        async with httpx.AsyncClient(timeout=10.0) as client:
            ref_res = await client.get(f"https://api.github.com/repos/{REPO_NAME}/git/trees/main?recursive=1", headers=headers)
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
                    blob_res = await client.get(f"https://api.github.com/repos/{REPO_NAME}/git/blobs/{file_blob_sha}", headers=blob_headers)
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
        async with httpx.AsyncClient(timeout=10.0) as client:
            ref_res = await client.get(f"https://api.github.com/repos/{REPO_NAME}/git/ref/heads/main", headers=headers)
            if ref_res.status_code != 200: return False
            latest_commit_sha = ref_res.json()["object"]["sha"]

            blob_res = await client.post(
                f"https://api.github.com/repos/{REPO_NAME}/git/blobs",
                headers=headers,
                json={"content": content_str, "encoding": "utf-8"}
            )
            if blob_res.status_code != 201: return False
            blob_sha = blob_res.json()["sha"]

            tree_res = await client.post(
                f"https://api.github.com/repos/{REPO_NAME}/git/trees",
                headers=headers,
                json={
                    "base_tree": latest_commit_sha,
                    "tree": [{"path": DB_FILE, "mode": "100644", "type": "blob", "sha": blob_sha}]
                }
            )
            if tree_res.status_code != 201: return False
            new_tree_sha = tree_res.json()["sha"]

            commit_res = await client.post(
                f"https://api.github.com/repos/{REPO_NAME}/git/commits",
                headers=headers,
                json={"message": commit_msg, "tree": new_tree_sha, "parents": [latest_commit_sha]}
            )
            if commit_res.status_code != 201: return False
            new_commit_sha = commit_res.json()["sha"]

            update_ref = await client.patch(
                f"https://api.github.com/repos/{REPO_NAME}/git/refs/heads/main",
                headers=headers,
                json={"sha": new_commit_sha}
            )
            return update_ref.status_code == 200
    except Exception as e:
        logger.error(f"GitHub Save Failed: {e}")
        return False

async def sync_db():
    global DB_CACHE, STYLED_NAMES_CACHE, KEYBOARD_CACHE
    latest_db = await get_latest_github_db()
    if latest_db or latest_db == {}:
        DB_CACHE = latest_db
        STYLED_NAMES_CACHE.clear()
        KEYBOARD_CACHE.clear()
        return True
    return False

SHAYARIS = [
    "✨ मंज़िल उन्हीं को मिलती है, जिनके सपनों में जान होती है!",
    "🔥 हौसले के तरकश में कोशिश का तीर ज़िंदा रख!",
    "💎 संघर्ष जितना कठिन होगा, जीत उतनी ही शानदार होगी!"
]

def build_topics_keyboard(page: int = 0):
    if page in KEYBOARD_CACHE:
        return KEYBOARD_CACHE[page]

    topics = sorted([t for t in DB_CACHE.keys() if not t.endswith(" (कमजोर सवाल)")])

    if not topics:
        res = InlineKeyboardMarkup([[InlineKeyboardButton("❌ कोई विषय नहीं मिला", callback_data="noop")]])
        KEYBOARD_CACHE[page] = res
        return res

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
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"opt_{t}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"page_{page+1}"))

    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("⚡ SUPER RESET ⚡", callback_data="super_reset")])
    res = InlineKeyboardMarkup(keyboard)
    KEYBOARD_CACHE[page] = res
    return res

# --- QUIZ ENGINE ---
async def send_next_quiz(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    user_data = context.application.user_data.get(user_id)
    if not user_data or not user_data.get('busy'):
        return

    if user_data.get('sending_lock', False):
        user_data['sending_lock'] = False

    user_data['sending_lock'] = True

    try:
        idx = user_data.get('idx', 0)
        topic = user_data.get('topic')
        
        if not user_data.get('is_retry') and (topic not in DB_CACHE or not DB_CACHE[topic]):
            user_data['busy'] = False
            await context.bot.send_message(chat_id, "⚠️ डेटाबेस में बदलाव हुआ है। कृपया नए सिरे से विषय चुनें: /start")
            return

        qs = user_data.get('wrong_qs_pool', []) if user_data.get('is_retry') else user_data.get('q_indices', [])
        total_qs = len(qs)

        if idx >= total_qs:
            score = user_data.get('score', 0)
            wrong_count = total_qs - score
            per = int((score / total_qs) * 100) if total_qs > 0 else 0
            medal = "🏆" if per >= 80 else "🥇"

            res = (
                f"╔═════════════════════════╗\n"
                f"  📊 {style_txt('QUIZ REPORT CARD')} {medal}\n"
                f"╚═════════════════════════╝\n\n"
                f"📝 विषय: {topic}\n"
                f"✅ सही: {score} | ❌ गलत: {wrong_count}\n"
                f"🏆 कुल स्कोर: {per}%\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

            keyboard = []
            if wrong_count > 0 and user_data.get('wrong_qs'):
                keyboard.append([InlineKeyboardButton(f"🔄 गलत सवाल फिर से हल करें ({wrong_count})", callback_data="retry_wrong")])

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
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
            user_data['sending_lock'] = False
            asyncio.create_task(send_next_quiz(context, chat_id, user_id))
            return

        user_data['current_question'] = q

        current_q_num = idx + 1
        remaining_qs = total_qs - current_q_num

        completed_blocks = int((current_q_num / total_qs) * 8)
        progress_bar = "🟢" * completed_blocks + "⚪" * (8 - completed_blocks)

        q_question = str(q.get('question', '')).strip()
        
        q_header = (
            f"Q{current_q_num}. {q_question}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🌀 {progress_bar} | ⏳ शेष: {remaining_qs}"
        )

        original_options = list(q.get('options', []))
        correct_option_text = original_options[q['answer']]

        shuffled_options = original_options.copy()
        random.shuffle(shuffled_options)
        correct_option_id = shuffled_options.index(correct_option_text)

        circle_icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "🟠", "⚪", "🟤"]
        formatted_options = [
            f"{circle_icons[i % len(circle_icons)]} {opt}" 
            for i, opt in enumerate(shuffled_options)
        ]

        bookmark_btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔖 मार्क करें (कमजोर सवाल लिस्ट में जोड़ें)", callback_data="mark_weak_perm")]
        ])

        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=q_header,
            options=formatted_options,
            type=Poll.QUIZ,
            correct_option_id=correct_option_id,
            is_anonymous=False,
            reply_markup=bookmark_btn,
            read_timeout=15,
            write_timeout=15
        )

        user_data['idx'] = idx + 1

        POLL_TRACKER[message.poll.id] = {
            "user_id": user_id,
            "chat_id": chat_id,
            "correct_option_id": correct_option_id,
            "q_data": q,
            "topic": topic
        }

    except Exception as e:
        logger.error(f"Quiz Sending Error: {e}")
        if user_data:
            user_data['sending_lock'] = False
            user_data['idx'] = user_data.get('idx', 0) + 1
            asyncio.create_task(send_next_quiz(context, chat_id, user_id))
    finally:
        if user_data:
            user_data['sending_lock'] = False

# --- Poll Answer Handler ---
USER_LOCKS = {}

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    poll_answer = update.poll_answer
    poll_id = poll_answer.poll_id

    if poll_id not in POLL_TRACKER:
        user_id = poll_answer.user.id
        user_data = context.application.user_data.get(user_id)
        if user_data and user_data.get('busy'):
            user_data['sending_lock'] = False
            asyncio.create_task(send_next_quiz(context, poll_answer.user.id, user_id))
        return

    tracker = POLL_TRACKER.pop(poll_id)
    user_id = tracker["user_id"]
    chat_id = tracker["chat_id"]
    correct_option_id = tracker["correct_option_id"]
    
    if not poll_answer.option_ids:
        return
        
    selected_option = poll_answer.option_ids[0]

    if user_id not in USER_LOCKS:
        USER_LOCKS[user_id] = asyncio.Lock()

    async with USER_LOCKS[user_id]:
        user_data = context.application.user_data.get(user_id)
        if user_data and user_data.get('busy'):
            if selected_option == correct_option_id:
                user_data['score'] += 1
            else:
                if 'wrong_qs' not in user_data:
                    user_data['wrong_qs'] = []
                user_data['wrong_qs'].append(tracker["q_data"])

            user_data['sending_lock'] = False
            await send_next_quiz(context, chat_id, user_id)

# --- Commands ---
async def reset_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text("🌀 Rebooting Bot...")
    try:
        await context.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(0.5)
        webhook_url = f"{RENDER_URL}/{TOKEN}"
        await context.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
        await sync_db()
        context.user_data.clear()
        POLL_TRACKER.clear()
        res = "╔════════════════════╗\n  ⚡ BOT IS ALIVE NOW ⚡ \n╚════════════════════╝\n✅ सारे जाम साफ़ हो गए हैं!"
        await m.edit_text(res)
    except Exception as e:
        await m.edit_text(f"❌ Failed: {e}")

async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📡 Syncing Database...")
    if await sync_db():
        total_topics = len([t for t in DB_CACHE.keys() if not t.endswith(" (कमजोर सवाल)")])
        total_qs = sum(len(v) for v in DB_CACHE.values())
        res = (
            "╔════════════════════╗\n 🔄 REFRESH SUCCESS 🔄 \n╚════════════════════╝\n"
            f"\n📂 कुल मुख्य विषय: {total_topics} | 📊 कुल सवाल: {total_qs}\n\n/start पर क्लिक करें।"
        )
        await msg.edit_text(res)
    else:
        await msg.edit_text("❌ Sync Failed!")

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global DB_CACHE, STYLED_NAMES_CACHE, KEYBOARD_CACHE
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
            KEYBOARD_CACHE.clear()
            total_topics = len([t for t in DB_CACHE.keys() if not t.endswith(" (कमजोर सवाल)")])
            await m.edit_text(
                "╔════════════════════╗\n  🚀 SUCCESSFULLY ADDED! 🚀  \n╚════════════════════╝\n"
                f"📦 कुल सुरक्षित मुख्य विषय: {total_topics}"
            )
            markup = build_topics_keyboard(page=0)
            await update.message.reply_text("🎯 अपडेटेड विषय सूची:", reply_markup=markup)
        else:
            await m.edit_text("❌ GitHub सेव करने में दिक्कत आई, कृपया दोबारा भेजें।")

    except Exception as e:
        await m.edit_text(f"❌ Data Format Error: {e}")

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global DB_CACHE, STYLED_NAMES_CACHE, KEYBOARD_CACHE
    t = " ".join(context.args).strip()
    if not t:
        return await update.message.reply_text("💡 उपयोग: /delete TopicName")

    m = await update.message.reply_text(f"🛡️ Deleting {t} safely...")
    latest_db = await get_latest_github_db()
    if not latest_db:
        latest_db = DB_CACHE

    if t in latest_db:
        del latest_db[t]
        weak_key = f"{t} (कमजोर सवाल)"
        if weak_key in latest_db:
            del latest_db[weak_key]

        saved = await save_to_github_safely(latest_db, f"Deleted Topic: {t}")
        if saved:
            DB_CACHE = latest_db
            STYLED_NAMES_CACHE.clear()
            KEYBOARD_CACHE.clear()
            await m.edit_text(f"✅ DELETED: {t}\n\nमूल विषय और कमजोर सवाल दोनों डिलीट हो गए!")
            markup = build_topics_keyboard(page=0)
            await update.message.reply_text("🎯 अपडेटेड विषय सूची:", reply_markup=markup)
        else:
            await m.edit_text("❌ डिलीट करने में विफल! GitHub कनेक्ट नहीं हुआ।")
    else:
        await m.edit_text(f"❌ विषय '{t}' डेटाबेस में नहीं मिला! कृपया सही नाम लिखें।")

async def delete_weak_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global DB_CACHE, STYLED_NAMES_CACHE, KEYBOARD_CACHE
    t = " ".join(context.args).strip()
    if not t:
        return await update.message.reply_text("💡 उपयोग: /delete_weak TopicName")

    weak_key = f"{t} (कमजोर सवाल)"
    m = await update.message.reply_text(f"🗑️ Deleting Weak Questions for '{t}'...")
    
    latest_db = await get_latest_github_db()
    if not latest_db:
        latest_db = DB_CACHE

    if weak_key in latest_db:
        del latest_db[weak_key]
        saved = await save_to_github_safely(latest_db, f"Deleted Weak List for: {t}")
        if saved:
            DB_CACHE = latest_db
            STYLED_NAMES_CACHE.clear()
            KEYBOARD_CACHE.clear()
            await m.edit_text(f"✅ **'{t}' के सभी कमजोर सवाल डिलीट कर दिए गए हैं!**", parse_mode="Markdown")
        else:
            await m.edit_text("❌ GitHub अपडेट करने में समस्या आई।")
    else:
        await m.edit_text(f"⚠️ '{t}' के लिए कोई कमजोर सवाल की लिस्ट नहीं मिली।")

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
        f"   👑 {style_txt('PANKAJ QUIZ BOT 2.0')} 👑\n"
        "╚════════════════════╝\n\n"
        f"{random.choice(SHAYARIS)}\n\n"
        "🎯 अपनी पसंद का विषय चुनें: 👇"
    )
    markup = build_topics_keyboard(page=0)
    await update.message.reply_text(welcome, reply_markup=markup)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global DB_CACHE
    query = update.callback_query
    
    asyncio.create_task(query.answer())

    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    if data == "noop":
        return

    if data.startswith("page_"):
        page = int(data.split("_")[1])
        markup = build_topics_keyboard(page=page)
        asyncio.create_task(query.edit_message_reply_markup(reply_markup=markup))
        return

    if data.startswith("opt_"):
        main_topic = data[4:]
        weak_topic_key = f"{main_topic} (कमजोर सवाल)"
        
        main_q_count = len(DB_CACHE.get(main_topic, []))
        weak_q_count = len(DB_CACHE.get(weak_topic_key, []))

        keyboard = []

        if weak_q_count > 0:
            keyboard.append([InlineKeyboardButton(f"⭐ 🔖 {main_topic} (कमजोर सवाल) [{weak_q_count}Q]", callback_data=f"tp_{weak_topic_key}")])

        keyboard.append([InlineKeyboardButton(f"▶️ {main_topic} के सभी सवाल [{main_q_count}Q]", callback_data=f"tp_{main_topic}")])
        keyboard.append([InlineKeyboardButton("⬅️ मुख्य मेन्यू में वापस जाएं", callback_data="back_to_main")])

        markup = InlineKeyboardMarkup(keyboard)
        asyncio.create_task(query.edit_message_text(f"📌 विषय: **{main_topic}**\n\nनीचे दिए गए विकल्पों में से चुनें: 👇", reply_markup=markup, parse_mode="Markdown"))
        return

    if data == "back_to_main":
        markup = build_topics_keyboard(page=0)
        welcome = "🎯 अपनी पसंद का विषय चुनें: 👇"
        asyncio.create_task(query.edit_message_text(welcome, reply_markup=markup))
        return

    if data == "mark_weak_perm":
        current_q = context.user_data.get('current_question')
        main_topic = context.user_data.get('topic')
        
        if not main_topic:
            for p_info in POLL_TRACKER.values():
                if p_info.get("user_id") == user_id:
                    main_topic = p_info.get("topic")
                    current_q = p_info.get("q_data")
                    break

        if main_topic and main_topic.endswith(" (कमजोर सवाल)"):
            main_topic = main_topic.replace(" (कमजोर सवाल)", "")

        if current_q and main_topic:
            weak_topic_key = f"{main_topic} (कमजोर सवाल)"
            
            if weak_topic_key not in DB_CACHE:
                DB_CACHE[weak_topic_key] = []

            if current_q not in DB_CACHE[weak_topic_key]:
                DB_CACHE[weak_topic_key].append(current_q)
                KEYBOARD_CACHE.clear()
                
                asyncio.create_task(context.bot.send_message(chat_id, f"✅ **सवाल '{main_topic}' के कमजोर बटन में जुड़ गया!**", parse_mode="Markdown"))

                async def async_bg_save():
                    try:
                        latest_db = await get_latest_github_db()
                        if not latest_db:
                            latest_db = DB_CACHE
                        if weak_topic_key not in latest_db:
                            latest_db[weak_topic_key] = []
                        if current_q not in latest_db[weak_topic_key]:
                            latest_db[weak_topic_key].append(current_q)
                        await save_to_github_safely(latest_db, f"Added Weak Question to {weak_topic_key}")
                    except Exception as err:
                        logger.error(f"Background Save Exception: {err}")

                asyncio.create_task(async_bg_save())
            else:
                asyncio.create_task(context.bot.send_message(chat_id, "⚠️ **यह सवाल पहले से ही कमजोर लिस्ट में मौजूद है!**", parse_mode="Markdown"))
        else:
            asyncio.create_task(context.bot.send_message(chat_id, "⚠️ **मार्क हो गया! (अगला सवाल हल करें)**", parse_mode="Markdown"))
        return

    if data == "super_reset":
        class TU:
            def __init__(self, m): self.message = m
        await reset_bot(TU(query.message), context)
        return

    if data.startswith("tp_"):
        topic = data[3:]
        if topic not in DB_CACHE or len(DB_CACHE[topic]) == 0:
            await query.message.reply_text("❌ इस विषय में कोई सवाल नहीं हैं!")
            return

        total_questions = len(DB_CACHE[topic])
        indices = list(range(total_questions))
        random.shuffle(indices)

        context.user_data.clear()
        context.user_data.update({
            'q_indices': indices, 
            'idx': 0, 
            'score': 0, 
            'busy': True, 
            'topic': topic, 
            'wrong_qs': [],
            'is_retry': False,
            'sending_lock': False
        })
        asyncio.create_task(send_next_quiz(context, chat_id, user_id))
        return

    if data == "retry_wrong":
        wrong_qs = context.user_data.get('wrong_qs', [])
        topic = context.user_data.get('topic', 'रिवीजन')
        if not wrong_qs:
            await query.message.reply_text("❌ कोई गलत सवाल बाकी नहीं है!")
            return

        qs = list(wrong_qs)
        random.shuffle(qs)
        context.user_data.clear()
        context.user_data.update({
            'wrong_qs_pool': qs, 
            'idx': 0, 
            'score': 0, 
            'busy': True, 
            'topic': f"{topic} (गलत सवाल)", 
            'wrong_qs': [],
            'is_retry': True,
            'sending_lock': False
        })
        asyncio.create_task(send_next_quiz(context, chat_id, user_id))
        return

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# --- SELF-PING LOOP ---
async def self_ping():
    await asyncio.sleep(10)
    async with httpx.AsyncClient() as client:
        while True:
            try:
                await client.get(f"{RENDER_URL}/{TOKEN}", timeout=5.0)
                logger.info("⚡ Heartbeat Sent: Server Kept Awake!")
            except Exception as e:
                logger.error(f"Heartbeat Error: {e}")
            await asyncio.sleep(180)

async def post_init(application: Application):
    asyncio.create_task(self_ping())

def main():
    app = Application.builder().token(TOKEN).concurrent_updates(True).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh_cmd))
    app.add_handler(CommandHandler("reset", reset_bot))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CommandHandler("delete_weak", delete_weak_cmd))
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
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
