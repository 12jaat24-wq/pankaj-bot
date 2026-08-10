import os
import json
import random
import logging
import asyncio
import httpx
import time
import base64
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
            ref_res = await client.get(f"https://api.github.com/repos/{REPO_NAME}/git/trees/main?recursive=1", headers=headers, timeout=15.0)
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
                    blob_res = await client.get(f"https://api.github.com/repos/{REPO_NAME}/git/blobs/{file_blob_sha}", headers=blob_headers, timeout=20.0)
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
                timeout=30.0
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
                timeout=15.0
            )
            if tree_res.status_code != 201: return False
            new_tree_sha = tree_res.json()["sha"]

            commit_res = await client.post(
                f"https://api.github.com/repos/{REPO_NAME}/git/commits",
                headers=headers,
                json={"message": commit_msg, "tree": new_tree_sha, "parents": [latest_commit_sha]},
                timeout=15.0
            )
            if commit_res.status_code != 201: return False
            new_commit_sha = commit_res.json()["sha"]

            update_ref = await client.patch(
                f"https://api.github.com/repos/{REPO_NAME}/git/refs/heads/main",
                headers=headers,
                json={"sha": new_commit_sha},
                timeout=15.0
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

# --- Commands ---
async def reset_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text("🌀 Hard Rebooting...")
    try:
        await context.bot.delete_webhook(drop_pending_updates=True)
        await asyncio.sleep(0.3)
        await context.bot.set_webhook(url=f"{RENDER_URL}/{TOKEN}", drop_pending_updates=True)
        await sync_db()
        context.user_data.clear()
        res = "╔════════════════════╗\n  ⚡ BOT IS ALIVE NOW ⚡ \n╚════════════════════╝\n✅ सारे जाम साफ़ हो गए हैं!"
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

async def send_fast_q(context: ContextTypes.DEFAULT_TYPE, chat_id: int, query=None, is_edit=False):
    ud = context.user_data
    if not ud or not ud.get('busy'):
        return

    idx, qs = ud.get('idx', 0), ud['qs']
    if idx >= len(qs):
        score, total = ud['score'], len(qs)
        wrong_count = total - score
        per = int((score / total) * 100) if total > 0 else 0
        medal = "🏆" if per >= 80 else "🥇"
        
        res = (
            f"╔══════════════════╗\n  📊 {style_txt('REPORT CARD')} {medal} \n╚══════════════════╝\n"
            f"📝 विषय: {ud['topic']}\n✅ सही: {score} | ❌ गलत: {wrong_count}\n🏆 स्कोर: {per}%\n━━━━━━━━━━━━━━━━━━━━"
        )
        
        keyboard = []
        if wrong_count > 0 and ud.get('wrong_qs'):
            keyboard.append([InlineKeyboardButton(f"🔄 गलत सवाल फिर से हल करें ({wrong_count})", callback_data="retry_wrong")])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        try:
            if query and is_edit:
                await query.edit_message_text(res, reply_markup=reply_markup)
            else:
                await context.bot.send_message(chat_id, res, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Report card send error: {e}")
            await context.bot.send_message(chat_id, res, reply_markup=reply_markup)
            
        ud['busy'] = False
        return

    q = qs[idx]
    bar = "🔹" * (idx + 1) + "▫️" * (len(qs) - idx - 1)
    q_text = str(q.get('question', '')).strip()
    original_options = list(q.get('options', []))
    correct_option_text = original_options[q['answer']]

    shuffled_options = original_options.copy()
    random.shuffle(shuffled_options)

    new_correct_index = shuffled_options.index(correct_option_text)
    
    # 🟢🔘 आकर्षक विजुअल बटन्स
    keyboard = []
    for opt_idx, opt_text in enumerate(shuffled_options):
        keyboard.append([InlineKeyboardButton(f"⚪️  {opt_text}", callback_data=f"ans_{opt_idx}_{new_correct_index}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    msg_text = f"✨ ({idx+1}/{len(qs)}) {q_text}\n\n{bar}"

    ud['current_q_data'] = q
    ud['idx'] = idx + 1

    try:
        if query and is_edit:
            await query.edit_message_text(msg_text, reply_markup=reply_markup)
        else:
            await context.bot.send_message(chat_id, msg_text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Message Edit/Send failed, falling back to fresh message: {e}")
        await context.bot.send_message(chat_id, msg_text, reply_markup=reply_markup)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "noop":
        await query.answer()
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

    if data.startswith("tp_"):
        await query.answer()
        topic = data[3:]
        if topic not in DB_CACHE:
            await query.message.reply_text("❌ यह विषय डिलीट हो चुका है! /start करें।")
            return

        qs = list(DB_CACHE.get(topic, []))
        if not qs:
            await query.message.reply_text("❌ इस विषय में कोई सवाल नहीं हैं!")
            return

        random.shuffle(qs)
        context.user_data.clear()
        context.user_data.update({
            'qs': qs, 
            'idx': 0, 
            'score': 0, 
            'busy': True, 
            'topic': topic, 
            'wrong_qs': []
        })
        await send_fast_q(context, query.message.chat_id, query=query, is_edit=True)
        return

    if data == "retry_wrong":
        await query.answer()
        wrong_qs = context.user_data.get('wrong_qs', [])
        topic = context.user_data.get('topic', 'रिवीजन')
        if not wrong_qs:
            await query.message.reply_text("❌ कोई गलत सवाल बाकी नहीं है!")
            return

        qs = list(wrong_qs)
        random.shuffle(qs)
        context.user_data.clear()
        context.user_data.update({
            'qs': qs, 
            'idx': 0, 
            'score': 0, 
            'busy': True, 
            'topic': f"{topic} (गलत सवाल)", 
            'wrong_qs': []
        })
        await send_fast_q(context, query.message.chat_id, query=query, is_edit=True)
        return

    if data.startswith("ans_"):
        parts = data.split("_")
        selected_idx = int(parts[1])
        correct_idx = int(parts[2])

        ud = context.user_data
        if ud and ud.get('busy'):
            if selected_idx == correct_idx:
                ud['score'] += 1
                # show_alert=False: स्क्रीन पर ऊपर ग्रीन मैसेज पट्टी + फ़ोन में वाइब्रेशन देगा
                await query.answer("🎉 बिलकुल सही जवाब! 🔥", show_alert=False)
            else:
                if 'wrong_qs' not in ud:
                    ud['wrong_qs'] = []
                ud['wrong_qs'].append(ud.get('current_q_data'))
                await query.answer("❌ ओहो, गलत जवाब! 💔", show_alert=False)

            await send_fast_q(context, query.message.chat_id, query=query, is_edit=True)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()

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
        listen="0.0.0.0", port=p, url_path=TOKEN,
        webhook_url=f"{RENDER_URL}/{TOKEN}",
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
