import os
import json
import random
import logging
import asyncio
import html
import re
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Poll
from telegram.constants import ParseMode
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PollAnswerHandler,
    filters,
    ContextTypes
)

# Optional json-repair library check
try:
    from json_repair import repair_json
except ImportError:
    repair_json = None

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
WATCHDOG_TASK = None
HTTP_CLIENT = None

def get_http_client():
    global HTTP_CLIENT
    if HTTP_CLIENT is None or HTTP_CLIENT.is_closed:
        HTTP_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=15.0),
            limits=httpx.Limits(max_keepalive_connections=5, keepalive_expiry=15.0)
        )
    return HTTP_CLIENT

def style_txt(text):
    if text in STYLED_NAMES_CACHE:
        return STYLED_NAMES_CACHE[text]
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    stylish = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    trans = str.maketrans(normal, stylish)
    res = str(text).translate(trans)
    STYLED_NAMES_CACHE[text] = res
    return res

# =====================================================================
# 🛠️ ADVANCED AUTO-REPAIR (डबल ब्रैकेट और सिंटैक्स गलतियाँ ऑटो-ठीक करने वाला)
# =====================================================================

def advanced_auto_repair_json(text: str) -> str:
    t = text.strip()

    # 1. डबल ब्रैकेट ऑटो-फिक्स (जैसे ": [\n  [" को ": [" बनाना)
    t = re.sub(r':\s*\[\s*\[', ': [', t)
    t = re.sub(r'\]\s*\]\s*\}', '] }', t)

    if repair_json:
        try:
            return repair_json(t)
        except Exception:
            pass

    # 2. स्मार्ट कोट्स हटाना
    t = t.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")

    # 3. फालतू कॉमा हटाना
    t = re.sub(r',\s*([\]}])', r'\1', t)

    # 4. छूटे हुए कॉमा जोड़ना
    t = re.sub(r'}\s*{', '}, {', t)
    t = re.sub(r']\s*\[', '], [', t)
    t = re.sub(r'}\s*"', '}, "', t)
    t = re.sub(r'"\s*{', '", {', t)

    # 5. सिंगल कोट्स को डबल कोट्स में बदलना
    t = re.sub(r"([{,]\s*)'([^']+)'\s*:", r'\1"\2":', t)
    t = re.sub(r":\s*'([^']*)'", r': "\1"', t)
    t = re.sub(r"\[\s*'([^']*)'", r'["\1"', t)
    t = re.sub(r",\s*'([^']*)'", r', "\1"', t)

    # 6. छूटे हुए ब्रैकेट्स बंद करना
    open_brackets = t.count('[') - t.count(']')
    open_braces = t.count('{') - t.count('}')
    if open_brackets > 0:
        t += ']' * open_brackets
    if open_braces > 0:
        t += '}' * open_braces

    return t

def auto_heal_quiz_structure(data):
    repaired_data = {}

    if isinstance(data, dict) and "question" in data:
        data = [data]

    if isinstance(data, list):
        data = {"सामान्य ज्ञान (Auto-Import)": data}

    if not isinstance(data, dict):
        return None, "डेटा एक वैध सूची या डिक्शनरी नहीं है।"

    for topic, q_list in data.items():
        # अगर अंदर भी डबल लिस्ट [[ ... ]] हो गई हो तो उसे चपटा (flatten) करें
        if isinstance(q_list, list) and len(q_list) > 0 and isinstance(q_list[0], list):
            q_list = [item for sublist in q_list if isinstance(sublist, list) for item in sublist]

        if not isinstance(q_list, list):
            continue

        clean_questions = []
        for q in q_list:
            if not isinstance(q, dict) or "question" not in q:
                continue

            q_clean = q.copy()
            options = q_clean.get("options", [])

            if isinstance(options, str):
                options = [opt.strip() for opt in options.split(",") if opt.strip()]
                q_clean["options"] = options

            if not isinstance(options, list) or len(options) < 2:
                continue

            ans = q_clean.get("answer", 0)
            if isinstance(ans, str):
                matched_idx = -1
                for idx, opt in enumerate(options):
                    if str(opt).strip().lower() == ans.strip().lower():
                        matched_idx = idx
                        break
                ans = matched_idx if matched_idx != -1 else 0

            if isinstance(ans, int):
                if ans >= len(options):
                    ans = len(options) - 1
                elif ans < 0:
                    ans = 0

            q_clean["answer"] = int(ans)
            clean_questions.append(q_clean)

        if clean_questions:
            repaired_data[str(topic).strip()] = clean_questions

    if not repaired_data:
        return None, "फ़ाइल में कोई भी वैध सवाल नहीं मिल सका।"

    return repaired_data, None

# =====================================================================
# 🎯 EXACT HINT ENGINE (सटीक सुझाव: क्या हटाना है और क्या जोड़ना है)
# =====================================================================

def get_actionable_hint(e: json.JSONDecodeError, lines: list) -> str:
    line_no = e.lineno
    current_line = lines[line_no - 1] if 0 <= line_no - 1 < len(lines) else ""
    prev_line = lines[line_no - 2] if line_no - 2 >= 0 and line_no - 2 < len(lines) else ""
    prev2_line = lines[line_no - 3] if line_no - 3 >= 0 and line_no - 3 < len(lines) else ""
    msg = e.msg.lower()

    # 1. डबल ब्रैकेट एरर (जैसा आपके स्क्रीनशॉट में हुआ)
    if "[" in current_line and "[" in prev_line:
        return f"👉 <b>क्या करना है:</b> लाइन <code>{line_no}</code> पर लगा फालतू ब्रैकेट <code>[</code> <b>हटा दें (Delete करें)</b>।"
    if "{" in current_line and "[" in prev_line and "[" in prev2_line:
        return f"👉 <b>क्या करना है:</b> लाइन <code>{line_no-1}</code> पर लगा फालतू ब्रैकेट <code>[</code> <b>हटा दें (Delete करें)</b>।"

    # 2. कॉमा छूटने की गलती
    if "expecting ',' delimiter" in msg:
        return f"👉 <b>क्या करना है:</b> लाइन <code>{line_no-1}</code> के अंत में कॉमा (<code>,</code>) लगाना भूल गए हैं, वहाँ <b>कॉमा जोड़ें</b>।"

    # 3. कोट्स की गलती
    if "expecting property name" in msg:
        if "'" in current_line:
            return f"👉 <b>क्या करना है:</b> सिंगल कोट्स (<code>'</code>) हटाकर डबल कोट्स (<code>\"</code>) लगाएँ।"
        return f"👉 <b>क्या करना है:</b> लाइन <code>{line_no}</code> पर नाम के आगे-पीछे डबल कोट्स (<code>\"</code>) जोड़ें।"

    # 4. इनवर्टेड कोट्स बंद न होना
    if "unterminated string" in msg:
        return f"👉 <b>क्या करना है:</b> लाइन <code>{line_no}</code> पर इनवर्टेड कोट्स खुला रह गया है, वाक्य के अंत में <code>\"</code> जोड़कर बंद करें।"

    # 5. फालतू कॉमा (Trailing Comma)
    if "expecting value" in msg:
        if prev_line.strip().endswith(","):
            return f"👉 <b>क्या करना है:</b> लाइन <code>{line_no-1}</code> के अंत में लगा फालतू कॉमा (<code>,</code>) <b>हटा दें</b>।"
        return f"👉 <b>क्या करना है:</b> लाइन <code>{line_no}</code> या <code>{line_no-1}</code> पर ब्रैकेट <code>[</code> या <code>{{</code> गलत लगा है, उसे चेक करें।"

    return "👉 <b>क्या करना है:</b> इस लाइन के आसपास कॉमा (,) और कोट्स (\") चेक करें।"

def format_json_syntax_error(e: json.JSONDecodeError, raw_text: str) -> str:
    lines = raw_text.splitlines()
    line_no = e.lineno
    col_no = e.colno
    msg = e.msg

    start_line = max(1, line_no - 2)
    end_line = min(len(lines), line_no + 2)

    snippet = []
    for i in range(start_line, end_line + 1):
        line_content = lines[i - 1] if i - 1 < len(lines) else ""
        if i == line_no:
            snippet.append(f"➡️ L{i}: {line_content}")
            pointer_indent = " " * (len(f"➡️ L{i}: ") + max(0, col_no - 1))
            snippet.append(f"{pointer_indent}🔺 [त्रुटि यहाँ है]")
        else:
            snippet.append(f"   L{i}: {line_content}")

    snippet_str = html.escape("\n".join(snippet))
    hint = get_actionable_hint(e, lines)

    return (
        "╔═════════════════════════╗\n"
        "   ❌ <b>JSON फ़ॉर्मेट त्रुटि</b>\n"
        "╚═════════════════════════╝\n\n"
        f"📍 <b>लाइन नंबर:</b> <code>{line_no}</code>\n"
        f"⚠️ <b>समस्या:</b> <code>{html.escape(msg)}</code>\n\n"
        f"💡 <b>सटीक समाधान:</b>\n{hint}\n\n"
        f"🔍 <b>फ़ाइल का वो हिस्सा:</b>\n"
        f"<pre>{snippet_str}</pre>"
    )

# =====================================================================
# GITHUB & DATABASE FUNCTIONS
# =====================================================================

async def get_latest_github_db():
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    client = get_http_client()
    try:
        ref_res = await client.get(
            f"https://api.github.com/repos/{REPO_NAME}/git/trees/main?recursive=1", 
            headers=headers
        )
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
                blob_res = await client.get(
                    f"https://api.github.com/repos/{REPO_NAME}/git/blobs/{file_blob_sha}", 
                    headers=blob_headers
                )
                if blob_res.status_code == 200:
                    text_data = blob_res.text.strip()
                    if not text_data:
                        return {}
                    return json.loads(text_data)
            else:
                return {}
    except Exception as e:
        logger.error(f"GitHub Direct Fetch Error: {e}")
        return None
    return {}

async def save_to_github_safely(data_to_save, commit_msg):
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    client = get_http_client()
    try:
        content_str = json.dumps(data_to_save, indent=2, ensure_ascii=False)
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
    global DB_CACHE, STYLED_NAMES_CACHE
    latest_db = await get_latest_github_db()
    if latest_db is not None:
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
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ कोई विषय नहीं मिला (डेटाबेस खाली है)", callback_data="noop")],
            [InlineKeyboardButton("⚡ SUPER RESET ⚡", callback_data="super_reset")]
        ])

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

# --- QUIZ ENGINE ---
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
            await context.bot.send_message(chat_id, "⚠️ विषय डेटा लोड नहीं हो सका। पुनः शुरू करें: /start")
            return

        if user_data.get('is_retry'):
            qs = user_data.get('wrong_qs_pool', [])
        else:
            qs = user_data.get('q_indices', [])

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

        message = await context.bot.send_poll(
            chat_id=chat_id,
            question=q_header,
            options=shuffled_options,
            type=Poll.QUIZ,
            correct_option_id=correct_option_id,
            is_anonymous=False,
            read_timeout=30,
            write_timeout=30
        )

        POLL_TRACKER[message.poll.id] = {
            "user_id": user_id,
            "chat_id": chat_id,
            "correct_option_id": correct_option_id,
            "q_data": q
        }

        user_data['idx'] = idx + 1

    except Exception as e:
        logger.error(f"Quiz Sending Error: {e}")
        if user_data:
            user_data['idx'] = user_data.get('idx', 0) + 1
            user_data['sending_lock'] = False
            asyncio.create_task(send_next_quiz(context, chat_id, user_id))
    finally:
        if user_data:
            user_data['sending_lock'] = False

# --- Poll Answer Handler ---
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
            if selected_option == correct_option_id:
                user_data['score'] += 1
            else:
                if 'wrong_qs' not in user_data:
                    user_data['wrong_qs'] = []
                user_data['wrong_qs'].append(tracker["q_data"])

            await send_next_quiz(context, chat_id, user_id)

# --- Commands ---
async def reset_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in context.application.user_data:
        context.application.user_data[user_id].clear()

    m = await update.message.reply_text("🌀 Re-linking Webhook & Syncing...")
    try:
        target_url = f"{RENDER_URL}/{TOKEN}"
        await context.bot.set_webhook(
            url=target_url,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            read_timeout=30,
            write_timeout=30
        )
        await sync_db()
        POLL_TRACKER.clear()
        res = "╔════════════════════╗\n  ⚡ BOT IS ALIVE NOW ⚡ \n╚════════════════════╝\n✅ कनेक्शन और मेमोरी पूरी तरह रीसेट हो गई है!\n\n/start पर क्लिक करें।"
        await m.edit_text(res)
    except Exception as e:
        await m.edit_text(f"❌ Failed: {e}")

async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📡 Syncing Database from GitHub...")
    if await sync_db():
        total_topics = len(DB_CACHE.keys())
        total_qs = sum(len(v) for v in DB_CACHE.values())
        res = (
            "╔════════════════════╗\n 🔄 REFRESH SUCCESS 🔄 \n╚════════════════════╝\n"
            f"\n📂 कुल विषय: {total_topics} | 📊 कुल सवाल: {total_qs}\n\n/start पर क्लिक करें।"
        )
        await msg.edit_text(res)
    else:
        await msg.edit_text("❌ Sync Failed! GitHub कनेक्शन में समस्या है।")

async def clear_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text("🗑️ सभी प्रश्न और विषय हटाए जा रहे हैं...")
    global DB_CACHE, STYLED_NAMES_CACHE
    saved = await save_to_github_safely({}, "Cleared entire database")
    if saved:
        DB_CACHE.clear()
        STYLED_NAMES_CACHE.clear()
        await m.edit_text("✅ सफलता! बॉट और GitHub दोनों से सारा डेटा डिलीट कर दिया गया है।\n\nअब नया JSON भेजें या /start करें।")
    else:
        await m.edit_text("❌ GitHub से डेटा हटाने में समस्या आई।")

# =====================================================================
# स्मार्ट इनपुट हैंडलर (Auto-Repair + Exact Hint)
# =====================================================================

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in context.application.user_data:
        context.application.user_data[user_id]['busy'] = False

    try:
        raw_text = ""
        if update.message.document:
            m_down = await update.message.reply_text("📥 फ़ाइल प्राप्त हो रही है...")
            try:
                f = await context.bot.get_file(update.message.document.file_id, read_timeout=60.0, write_timeout=60.0)
                c = await f.download_as_bytearray(read_timeout=60.0, write_timeout=60.0)
                raw_text = c.decode('utf-8', errors='ignore')
            finally:
                try:
                    await m_down.delete()
                except Exception:
                    pass
        elif update.message.text and ("options" in update.message.text or "question" in update.message.text):
            raw_text = update.message.text
        else:
            return

        if not raw_text.strip():
            return

        clean_text = raw_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        parsed_data = None
        was_repaired = False
        original_syntax_error = None

        # 1. साधारण पार्सिंग
        try:
            parsed_data = json.loads(clean_text)
        except json.JSONDecodeError as je:
            original_syntax_error = je

        # 2. अगर साधारण में फेल हुआ, तो ऑटो-रिपेयर चलाएं
        if parsed_data is None:
            try:
                repaired_text = advanced_auto_repair_json(clean_text)
                parsed_data = json.loads(repaired_text)
                was_repaired = True
            except Exception:
                # यदि ऑटो-रिपेयर भी विफल हो, तो सटीक एक्शन हिंट भेजें
                err_msg = format_json_syntax_error(original_syntax_error, clean_text)
                await update.message.reply_text(err_msg, parse_mode=ParseMode.HTML)
                return

        # 3. स्ट्रक्चर को ऑटो-हीलिंग दें
        final_data, struct_err = auto_heal_quiz_structure(parsed_data)
        if struct_err:
            await update.message.reply_text(f"⚠️ {struct_err}")
            return

        # 4. GitHub पर सेव करें
        m = await update.message.reply_text("🛡️ Safely Adding Data to GitHub...")

        global DB_CACHE, STYLED_NAMES_CACHE
        latest_db = await get_latest_github_db()
        if latest_db is None:
            latest_db = DB_CACHE.copy() if DB_CACHE else {}

        added_qs_count = 0
        for topic, questions in final_data.items():
            if topic in latest_db:
                latest_db[topic].extend(questions)
            else:
                latest_db[topic] = questions
            added_qs_count += len(questions)

        saved = await save_to_github_safely(latest_db, "Safe Add (Auto-Healed)")
        if saved:
            DB_CACHE = latest_db
            STYLED_NAMES_CACHE.clear()
            total_topics = len(DB_CACHE.keys())

            fix_note = "\n🛠️ <i>(JSON में सिंटैक्स त्रुटि थी, लेकिन बॉट ने उसे खुद ठीक करके स्वीकार कर लिया!)</i>" if was_repaired else ""

            await m.edit_text(
                "╔════════════════════╗\n"
                "  🚀 SUCCESSFULLY ADDED! 🚀  \n"
                "╚════════════════════╝\n\n"
                f"✅ जोड़े गए नए प्रश्न: <b>{added_qs_count}</b>\n"
                f"📦 कुल सुरक्षित विषय: <b>{total_topics}</b>"
                f"{fix_note}",
                parse_mode=ParseMode.HTML
            )
            markup = build_topics_keyboard(page=0)
            await update.message.reply_text("🎯 अपडेटेड विषय सूची:", reply_markup=markup)
        else:
            await m.edit_text("❌ GitHub सेव करने में दिक्कत आई, कृपया दोबारा भेजें।")

    except Exception as e:
        logger.error(f"Handle Input Error: {e}")
        await update.message.reply_text(f"❌ अप्रत्याशित त्रुटि: {html.escape(str(e))}")

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = " ".join(context.args).strip()
    if not t:
        return await update.message.reply_text("💡 उपयोग: /delete TopicName")

    m = await update.message.reply_text(f"🛡️ Deleting {t} safely...")
    global DB_CACHE, STYLED_NAMES_CACHE
    latest_db = await get_latest_github_db()
    if latest_db is None:
        latest_db = DB_CACHE.copy()

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

# FORCED AUTO-UNLOCKED START COMMAND
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in context.application.user_data:
        context.application.user_data[user_id].clear()
    
    if update.message:
        try:
            await update.message.reply_chat_action("typing")
        except Exception:
            pass

    await sync_db()

    welcome = (
        "╔════════════════════╗\n"
        f"    👑 {style_txt('PANKAJ QUIZ BOT 2.0')} 👑\n"
        "╚════════════════════╝\n\n"
        f"{random.choice(SHAYARIS)}\n\n"
        "🎯 अपनी पसंद का विषय चुनें: 👇"
    )
    markup = build_topics_keyboard(page=0)
    await update.message.reply_text(welcome, reply_markup=markup)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    if data == "noop":
        return

    if data == "super_reset":
        class TU:
            def __init__(self, m, u): 
                self.message = m
                self.effective_user = u
        await reset_bot(TU(query.message, query.from_user), context)
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
        if not DB_CACHE:
            await sync_db()

        if topic not in DB_CACHE:
            await query.message.reply_text("❌ यह विषय उपलब्ध नहीं है! /start करें।")
            return

        total_questions = len(DB_CACHE[topic])
        if total_questions == 0:
            await query.message.reply_text("❌ इस विषय में कोई सवाल नहीं हैं!")
            return

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
    logger.error(f"Update {update} caused error: {context.error}")

# --- 24/7 AUTO-HEALING & KEEP-ALIVE WATCHDOG ---
async def self_keep_alive_watchdog(application: Application):
    await asyncio.sleep(15)
    logger.info("⚡ Auto-Healing Watchdog Online!")
    target_url = f"{RENDER_URL}/{TOKEN}"

    counter = 0
    while True:
        try:
            client = get_http_client()
            try:
                await client.get(RENDER_URL, follow_redirects=True)
            except Exception:
                pass

            counter += 1
            if counter >= 2:
                counter = 0
                wh_info = await application.bot.get_webhook_info()
                if wh_info.url != target_url:
                    logger.warning(f"⚠️ Webhook Disconnected! Current: '{wh_info.url}'. Auto-relinking now...")
                    await application.bot.set_webhook(
                        url=target_url,
                        allowed_updates=Update.ALL_TYPES,
                        drop_pending_updates=True,
                        read_timeout=30,
                        write_timeout=30
                    )
                    logger.info("✅ Webhook Auto-Healed Successfully!")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Watchdog Loop Error: {e}")

        await asyncio.sleep(60)

async def post_init(application: Application):
    global WATCHDOG_TASK
    asyncio.create_task(sync_db())
    WATCHDOG_TASK = asyncio.create_task(self_keep_alive_watchdog(application))

async def post_shutdown(application: Application):
    global WATCHDOG_TASK, HTTP_CLIENT
    if WATCHDOG_TASK and not WATCHDOG_TASK.done():
        WATCHDOG_TASK.cancel()
    if HTTP_CLIENT and not HTTP_CLIENT.is_closed:
        await HTTP_CLIENT.aclose()

def main():
    request_config = HTTPXRequest(
        connection_pool_size=10,
        connect_timeout=30.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=30.0
    )

    app = (
        Application.builder()
        .token(TOKEN)
        .request(request_config)
        .concurrent_updates(True)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh_cmd))
    app.add_handler(CommandHandler("reset", reset_bot))
    app.add_handler(CommandHandler("clear_all", clear_all_cmd))
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
