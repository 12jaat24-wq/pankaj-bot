import os
import json
import random
import logging
import asyncio
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
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

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CACHE = {}
STYLED_NAMES_CACHE = {}
TOPICS_PER_PAGE = 10 
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

# --- 🎮 ARCADE GAMING HUD RENDERER (0.00 SEC FLICKER-FREE) ---
def render_arcade_screen(user_data, view_idx):
    topic = user_data.get('topic')
    qs = user_data.get('wrong_qs_pool') if user_data.get('is_retry') else user_data.get('q_indices')
    total_qs = len(qs)
    history = user_data.get('history', [])
    lives = user_data.get('lives', 5)
    score = user_data.get('score', 0)
    streak = user_data.get('streak', 0)
    xp = user_data.get('xp', 0)

    # अगर गेम समाप्त हो गया (सवाल खत्म या 0 लाइफ)
    if view_idx >= total_qs or lives <= 0:
        wrong_count = len([h for h in history if not h['is_correct'] and h['user_selected'] is not None])
        skipped = total_qs - score - wrong_count
        per = int((score / total_qs) * 100) if total_qs > 0 else 0

        title = "💀 GAME OVER" if lives <= 0 else "🏆 VICTORY CHAMPION"
        rank = "👑 GODLIKE" if per >= 90 else "⚡ PRO GAMER" if per >= 70 else "🎯 SURVIVOR"

        text = (
            f"┏━━━━━━━━━━━━━━━━━━━━━┓\n"
            f"   {title}   \n"
            f"┗━━━━━━━━━━━━━━━━━━━━━┛\n\n"
            f"🎮 विषय: ❴ {topic} ❵\n"
            f"🎖️ रैंक: {rank}\n"
            f"⭐ कुल XP अर्जित: {xp} PTS\n"
            f"─────────────────────\n"
            f"🟢 सही उत्तर   : {score}\n"
            f"🔴 गलत उत्तर   : {wrong_count}\n"
            f"⚪ छोड़े गए     : {skipped}\n"
            f"📊 एक्यूरेसी    : {per}%\n"
            f"─────────────────────\n"
            f"💡 नीचे दिए बटनों से पिछला गेम रीव्यू करें या गलत सवाल फिर से खेलें!"
        )

        kb = []
        if total_qs > 0:
            kb.append([InlineKeyboardButton("🔍 सवालों का पूरा रीव्यू (Review)", callback_data=f"qnav_view_{min(view_idx, total_qs-1)}")])
        if wrong_count > 0:
            kb.append([InlineKeyboardButton(f"🔄 गलत सवाल फिर से खेलें ({wrong_count})", callback_data="retry_wrong")])
        kb.append([InlineKeyboardButton("🏠 मुख्य मेनू (/start)", callback_data="go_start")])
        return text, InlineKeyboardMarkup(kb)

    # वर्तमान सवाल डेटा
    if user_data.get('is_retry'):
        q = qs[view_idx]
    else:
        q = DB_CACHE[topic][qs[view_idx]]

    current_q_num = view_idx + 1

    # रंगीन लाइफ बार ❤️
    lives_str = "❤️" * lives + "🖤" * (5 - lives)
    streak_banner = f"🔥 COMBO x{streak}" if streak >= 2 else "⚡ ACTIVE"

    completed_blocks = int((current_q_num / total_qs) * 8)
    progress_bar = "🟩" * completed_blocks + "⬜" * (8 - completed_blocks)

    is_answered = view_idx < len(history)
    letters = ["🅐", "🅑", "🅒", "🅓", "🅔", "🅕"]

    if not is_answered:
        # अगर सवाल अभी हल करना है
        if 'pending_q_meta' not in user_data or user_data['pending_q_meta']['idx'] != view_idx:
            original_options = list(q.get('options', []))
            correct_text = original_options[q['answer']]
            shuffled = original_options.copy()
            random.shuffle(shuffled)
            correct_id = shuffled.index(correct_text)

            user_data['pending_q_meta'] = {
                'idx': view_idx,
                'shuffled': shuffled,
                'correct_id': correct_id,
                'q': q,
                'hidden': []
            }

        meta = user_data['pending_q_meta']
        shuffled = meta['shuffled']
        hidden = meta.get('hidden', [])

        text = (
            f"╭─────────────────────╮\n"
            f"  🕹️ {style_txt('PANKAJ ARCADE')} • Q{current_q_num}/{total_qs}\n"
            f"╰─────────────────────╯\n"
            f"💓 {lives_str} │ {streak_banner}\n"
            f"⭐ XP: {xp} PTS    │ ⏳ शेष: {total_qs - current_q_num}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"❓ {str(q.get('question','')).strip()}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"{progress_bar}\n"
            f"👇 सही विकल्प चुनें:"
        )

        kb = []
        for i, opt in enumerate(shuffled):
            if i in hidden:
                kb.append([InlineKeyboardButton("🚫 [ 50:50 से हटाया गया ]", callback_data="noop")])
            else:
                l = letters[i] if i < len(letters) else f"{i+1}."
                kb.append([InlineKeyboardButton(f"{l} {str(opt)[:50]}", callback_data=f"qans_{i}")])

        # गेमिंग कंट्रोल बार
        nav_row = []
        if view_idx > 0:
            nav_row.append(InlineKeyboardButton("⬅️ पिछला", callback_data=f"qnav_view_{view_idx-1}"))

        # 50:50 लाइफलाइन बटन
        if not user_data.get('used_5050', False):
            nav_row.append(InlineKeyboardButton("💡 50:50", callback_data="use_5050"))

        nav_row.append(InlineKeyboardButton("⏩ छोड़ें", callback_data="qnav_skip"))
        nav_row.append(InlineKeyboardButton("🛑 बंद", callback_data="qnav_quit"))
        kb.append(nav_row)

    else:
        # रीव्यू मोड (पहले से हल किया गया सवाल)
        h = history[view_idx]
        shuffled = h['shuffled']
        user_choice = h['user_selected']
        correct_id = h['correct_id']

        status_text = "✅ आपका उत्तर सही था!" if h['is_correct'] else "❌ आपका उत्तर गलत था!" if user_choice is not None else "⚪ आपने छोड़ दिया था!"

        text = (
            f"╭─────────────────────╮\n"
            f"  🔍 {style_txt('TIME MACHINE')} • Q{current_q_num}/{total_qs}\n"
            f"╰─────────────────────╯\n"
            f"📊 स्टेटस: {status_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"❓ {str(q.get('question','')).strip()}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👉 आपका चुनाव: {shuffled[user_choice] if user_choice is not None else 'छोड़ा था'}\n"
            f"🎯 सही उत्तर  : ✅ {shuffled[correct_id]}"
        )

        kb = []
        for i, opt in enumerate(shuffled):
            prefix = "✅ " if i == correct_id else "❌ " if i == user_choice else f"{letters[i]} "
            kb.append([InlineKeyboardButton(f"{prefix}{str(opt)[:50]}", callback_data="noop")])

        nav_row = []
        if view_idx > 0:
            nav_row.append(InlineKeyboardButton("⬅️ पिछला", callback_data=f"qnav_view_{view_idx-1}"))
        
        if view_idx < len(history) - 1:
            nav_row.append(InlineKeyboardButton("अगला ➡️", callback_data=f"qnav_view_{view_idx+1}"))
        else:
            nav_row.append(InlineKeyboardButton("⚡ ताज़ा सवाल ➡️", callback_data=f"qnav_view_{len(history)}"))

        kb.append(nav_row)

    return text, InlineKeyboardMarkup(kb)

# --- ⚡ 0.00 SEC INSTANT CALLBACK HANDLER ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_data = context.user_data

    if data == "noop":
        await query.answer()
        return

    if data == "go_start":
        await query.answer()
        await start(update, context)
        return

    if data == "super_reset":
        await query.answer()
        class TU:
            def __init__(self, m): self.message = m
        await reset_bot(TU(query.message), context)
        return

    if data.startswith("page_"):
        await query.answer()
        page = int(data.split("_")[1])
        markup = build_topics_keyboard(page=page)
        try:
            await query.edit_message_reply_markup(reply_markup=markup)
        except Exception:
            pass
        return

    # विषय चुनना (बिना किसी फालतू मैसेज के डायरेक्ट उसी मैसेज में गेम शुरू)
    if data.startswith("tp_"):
        await query.answer()
        topic = data[3:]
        if topic not in DB_CACHE or not DB_CACHE[topic]:
            await query.answer("❌ इस विषय में सवाल नहीं हैं!", show_alert=True)
            return

        indices = list(range(len(DB_CACHE[topic])))
        random.shuffle(indices)

        user_data.clear()
        user_data.update({
            'topic': topic,
            'q_indices': indices,
            'history': [],
            'score': 0,
            'streak': 0,
            'xp': 0,
            'lives': 5,
            'used_5050': False,
            'busy': True,
            'is_retry': False,
            'view_idx': 0
        })

        text, kb = render_arcade_screen(user_data, 0)
        await query.edit_message_text(text, reply_markup=kb)
        return

    # 50:50 लाइफलाइन का इस्तेमाल
    if data == "use_5050":
        meta = user_data.get('pending_q_meta')
        if meta and not user_data.get('used_5050'):
            user_data['used_5050'] = True
            corr = meta['correct_id']
            wrong_indices = [i for i in range(len(meta['shuffled'])) if i != corr]
            to_hide = random.sample(wrong_indices, min(2, len(wrong_indices)))
            meta['hidden'] = to_hide
            
            await query.answer("💡 50:50 एक्टिव! 2 गलत विकल्प उड़ा दिए गए!", show_alert=False)
            text, kb = render_arcade_screen(user_data, user_data.get('view_idx', 0))
            await query.edit_message_text(text, reply_markup=kb)
        else:
            await query.answer("⚠️ 50:50 लाइफलाइन पहले ही उपयोग हो चुकी है!", show_alert=False)
        return

    # उत्तर विकल्प पर क्लिक (0-माइक्रोसेकंड रिस्पॉन्स + फ़्लोटिंग टोस्ट)
    if data.startswith("qans_"):
        selected_id = int(data.split("_")[1])
        meta = user_data.get('pending_q_meta')
        if not meta:
            await query.answer()
            return

        corr_id = meta['correct_id']
        is_correct = (selected_id == corr_id)

        if is_correct:
            user_data['score'] = user_data.get('score', 0) + 1
            user_data['streak'] = user_data.get('streak', 0) + 1
            earned_xp = 10 + (user_data['streak'] * 5)
            user_data['xp'] = user_data.get('xp', 0) + earned_xp
            # फ़ोन में हल्का वाइब्रेशन + ऊपर नियॉन टोस्ट (बिना किसी लैग के)
            await query.answer(f"🎉 सही उत्तर! +{earned_xp} XP 🔥 COMBO x{user_data['streak']}", show_alert=False)
        else:
            user_data['streak'] = 0
            user_data['lives'] = max(0, user_data.get('lives', 5) - 1)
            corr_text = meta['shuffled'][corr_id]
            # गलत होने पर झटका + सही उत्तर तुरंत टोस्ट में
            await query.answer(f"❌ गलत! सही उत्तर: {corr_text[:35]} (💔 1 Life Lost)", show_alert=False)

        user_data.setdefault('history', []).append({
            'q': meta['q'],
            'shuffled': meta['shuffled'],
            'correct_id': corr_id,
            'user_selected': selected_id,
            'is_correct': is_correct
        })

        next_idx = len(user_data['history'])
        user_data['view_idx'] = next_idx
        text, kb = render_arcade_screen(user_data, next_idx)
        try:
            await query.edit_message_text(text, reply_markup=kb)
        except Exception:
            pass
        return

    # सवाल छोड़ना (Skip)
    if data == "qnav_skip":
        meta = user_data.get('pending_q_meta')
        if meta:
            user_data['streak'] = 0
            user_data.setdefault('history', []).append({
                'q': meta['q'],
                'shuffled': meta['shuffled'],
                'correct_id': meta['correct_id'],
                'user_selected': None,
                'is_correct': False
            })
        await query.answer("⏩ सवाल छोड़ दिया गया!", show_alert=False)
        next_idx = len(user_data.get('history', []))
        user_data['view_idx'] = next_idx
        text, kb = render_arcade_screen(user_data, next_idx)
        try:
            await query.edit_message_text(text, reply_markup=kb)
        except Exception:
            pass
        return

    # पिछला / अगला सवाल देखना (Time Machine Review)
    if data.startswith("qnav_view_"):
        await query.answer()
        target_idx = int(data.split("_")[2])
        user_data['view_idx'] = target_idx
        text, kb = render_arcade_screen(user_data, target_idx)
        try:
            await query.edit_message_text(text, reply_markup=kb)
        except Exception:
            pass
        return

    # क्विज़ बीच में समाप्त करना
    if data == "qnav_quit":
        await query.answer("🛑 गेम समाप्त!")
        user_data['view_idx'] = 999999
        text, kb = render_arcade_screen(user_data, 999999)
        try:
            await query.edit_message_text(text, reply_markup=kb)
        except Exception:
            pass
        return

    # गलत सवाल दोबारा हल करना
    if data == "retry_wrong":
        await query.answer()
        history = user_data.get('history', [])
        wrong_qs = [h['q'] for h in history if not h['is_correct']]
        if not wrong_qs:
            await query.answer("❌ कोई गलत सवाल बाकी नहीं है!", show_alert=True)
            return

        random.shuffle(wrong_qs)
        topic = user_data.get('topic', 'रिवीजन')
        user_data.clear()
        user_data.update({
            'topic': f"{topic} (रिवीजन)",
            'wrong_qs_pool': wrong_qs,
            'history': [],
            'score': 0,
            'streak': 0,
            'xp': 0,
            'lives': 5,
            'used_5050': False,
            'busy': True,
            'is_retry': True,
            'view_idx': 0
        })
        text, kb = render_arcade_screen(user_data, 0)
        try:
            await query.edit_message_text(text, reply_markup=kb)
        except Exception:
            pass
        return

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if not DB_CACHE:
        await sync_db()
    if not DB_CACHE:
        msg = update.message or update.callback_query.message
        return await msg.reply_text("❌ डेटाबेस खाली है!")

    welcome = (
        "┏━━━━━━━━━━━━━━━━━━━━━┓\n"
        f"  🕹️ {style_txt('PANKAJ CYBER ARCADE')} 🕹️\n"
        "┗━━━━━━━━━━━━━━━━━━━━━┛\n\n"
        f"{random.choice(SHAYARIS)}\n\n"
        "⚡ 0.00 सेकंड स्पीड • नो स्क्रीन फ्लिकर!\n"
        "💓 5 लाइफलाइन सिस्टम • 💡 50:50 KBC मोड\n\n"
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
