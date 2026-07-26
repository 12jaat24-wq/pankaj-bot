import os
import json
import random
import logging
import asyncio
import time
import httpx
from github import Github
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    PollAnswerHandler, MessageHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

# --- कॉन्फ़िगरेशन (Environment Variables) ---
TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = "12jaat24-wq/pankaj-bot" # अपना सही रिपो नाम डालें
DB_FILE = "quiz_database.json"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{REPO_NAME}/main/{DB_FILE}"

# --- लॉगिंग और ग्लोबल डेटा ---
logging.basicConfig(level=logging.ERROR)
DB_CACHE = {}
STYLE_CACHE = {}

# --- शाही स्टाइलिंग इंजन (Cache-Based) ---
def style_txt(text):
    if text in STYLE_CACHE: return STYLE_CACHE[text]
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    bold = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝘅𝗬𝘡𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    res = str(text).translate(str.maketrans(normal, bold))
    STYLE_CACHE[text] = res
    return res

def box(text):
    return f"╔════════════════════╗\n   {text}\n╚════════════════════╝"

# --- मोटिवेशनल शायरियां ---
SHAYARIS = [
    "✨ मंज़िल उन्हीं को मिलती है, जिनके सपनों में जान होती है।",
    "🔥 हौसले के तरकश में कोशिश का वो तीर ज़िंदा रख।",
    "🚀 शुरुआत करने के लिए महान होना ज़रूरी नहीं, शुरुआत करना ज़रूरी है।",
    "💎 मैदान में हारा हुआ इंसान फिर से जीत सकता है, पर मन से हारा नहीं।"
]

# --- सुपर-फास्ट डेटा सिंक (Cache-Buster) ---
async def sync_github():
    global DB_CACHE
    try:
        async with httpx.AsyncClient() as client:
            # Timestamp (t=...) का उपयोग ताकि GitHub हमेशा ताज़ा डेटा दे
            res = await client.get(f"{GITHUB_RAW_URL}?t={int(time.time())}", timeout=10)
            if res.status_code == 200:
                DB_CACHE = res.json()
                return True
    except Exception: pass
    return False

# --- कमांड: /start (Royal UI) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DB_CACHE: await sync_github()
    
    name = style_txt("PANKAJ QUIZ BOT 2.0")
    header = box(f"👑 {name} 👑")
    shayar = f"_{random.choice(SHAYARIS)}_"
    
    icons = ["💠", "🔆", "💎", "🌀", "⚛️", "🔥", "🔱", "⚡"]
    keyboard = []
    topics = sorted(DB_CACHE.keys())
    for i in range(0, len(topics), 2):
        row = [InlineKeyboardButton(f"{random.choice(icons)} {style_txt(topics[i])}", callback_data=topics[i])]
        if i + 1 < len(topics):
            row.append(InlineKeyboardButton(f"{random.choice(icons)} {style_txt(topics[i+1])}", callback_data=topics[i+1]))
        keyboard.append(row)

    await update.message.reply_text(
        f"{header}\n\n{shayar}\n\n🎯 **अपना विषय चुनें और शुरू करें:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

# --- क्विज़ लॉजिक (0.5s Auto-Next & Progress Bar) ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    topic = query.data
    if topic not in DB_CACHE: return
    
    qs = list(DB_CACHE[topic])
    random.shuffle(qs)
    context.user_data.update({'qs': qs, 'idx': 0, 'score': 0, 'topic': topic})
    
    await query.delete_message()
    await send_next_q(context, query.message.chat_id)

async def send_next_q(context, chat_id):
    ud = context.user_data
    idx, qs = ud['idx'], ud['qs']
    total = len(qs)

    if idx >= total:
        # शाही रिपोर्ट कार्ड
        score = ud['score']
        per = int((score/total)*100)
        medal = "🏆" if per >= 80 else ("🥇" if per >= 60 else "🥈")
        
        report = (
            f"╔════════════════════╗\n"
            f"   📊   {style_txt('REPORT CARD')}   {medal}\n"
            f"╚════════════════════╝\n"
            f"📝 विषय: `{ud['topic']}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ सही: `{score}` | ❌ गलत: `{total-score}`\n"
            f"🏆 परिणाम: `{per}%` | {medal}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 /start - फिर से शुरू करें"
        )
        await context.bot.send_message(chat_id, report, parse_mode=ParseMode.MARKDOWN)
        return

    q = qs[idx]
    # प्रोग्रेस बार
    progress = idx + 1
    bar = "🔹" * progress + "▫️" * (total - progress)
    
    await context.bot.send_poll(
        chat_id=chat_id,
        question=f"✨ ({idx+1}/{total}) {q['variations'][0]}\n{bar}",
        options=q['options'],
        type=Poll.QUIZ,
        correct_option_id=q['answer'],
        is_anonymous=False
    )
    ud['idx'] += 1

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    ud = context.application.user_data.get(ans.user.id)
    if ud and 'qs' in ud:
        # स्कोर अपडेट
        if ans.option_ids[0] == ud['qs'][ud['idx']-1]['answer']:
            ud['score'] += 1
        
        # 0.5 सेकंड का इंतज़ार (Unstoppable Speed)
        await asyncio.sleep(0.5)
        
        # डमी क्लास ताकि send_next_q चले
        class TC:
            def __init__(self, u, b): self.user_data, self.bot = u, b
        await send_next_q(TC(ud, context.bot), ans.user.id)

# --- इन्वेंटरी: /refresh (Monospace Table) ---
async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text("🔄 `Syncing Engine...`", parse_mode=ParseMode.MARKDOWN)
    if await sync_github():
        table = "```\n"
        table += "┌──────────────┬──────┐\n"
        table += "│   SUBJECT    │ Qs   │\n"
        table += "├──────────────┼──────┤\n"
        for t, v in DB_CACHE.items():
            table += f"│ {t[:12].ljust(12)} │ {str(len(v)).ljust(4)} │\n"
        table += "└──────────────┴──────┘\n```"
        
        res = f"{box(style_txt('REFRESH SUCCESS'))}\n\n{table}\n/start करें।"
        await m.edit_text(res, parse_mode=ParseMode.MARKDOWN)
    else:
        await m.edit_text("❌ `GitHub Sync Failed!`")

# --- डेटा हैंडलिंग: Upload & Delete ---
async def handle_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # JSON कोड या फाइल रिसीव करना
    text = ""
    if update.message.document:
        f = await context.bot.get_file(update.message.document.file_id)
        b = await f.download_as_bytearray()
        text = b.decode('utf-8')
    else: text = update.message.text

    if "variations" in text:
        try:
            new_data = json.loads(text.replace('```json', '').replace('```', '').strip())
            msg = await update.message.reply_text("⏳ `Vault Updating...`")
            
            # GitHub Push Logic
            g = Github(GITHUB_TOKEN)
            repo = g.get_repo(REPO_NAME)
            file_obj = repo.get_contents(DB_FILE)
            db = json.loads(file_obj.decoded_content.decode())
            db.update(new_data)
            repo.update_file(file_obj.path, "Vault Update", json.dumps(db, indent=4, ensure_ascii=False), file_obj.sha)
            
            await sync_github()
            await msg.edit_text(f"{box(style_txt('DATABASE UPDATED'))}\n\n✅ नया खजाना सुरक्षित है!\n/refresh करें।", parse_mode=ParseMode.MARKDOWN)
        except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

async def delete_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic: return await update.message.reply_text("💡 `/delete TopicName` लिखें।")
    
    try:
        g = Github(GITHUB_TOKEN); repo = g.get_repo(REPO_NAME)
        file_obj = repo.get_contents(DB_FILE)
        db = json.loads(file_obj.decoded_content.decode())
        if topic in db:
            del db[topic]
            repo.update_file(file_obj.path, f"Deleted {topic}", json.dumps(db, indent=4, ensure_ascii=False), file_obj.sha)
            await sync_github()
            await update.message.reply_text(f"{box(style_txt('TOPIC DELETED'))}\n\n🔥 `{topic}` जड़ से मिटा दिया गया।", parse_mode=ParseMode.MARKDOWN)
    except Exception as e: await update.message.reply_text(f"❌ Error: {e}")

# --- सुपर रिसेट (Flush Webhook) ---
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.application.drop_pending_updates()
    await update.message.reply_text(f"{box(style_txt('SYSTEM RESET'))}\n\n✅ पाइप साफ़ हो गया! अब डबल टिक आएगा।", parse_mode=ParseMode.MARKDOWN)

# --- मुख्य इंजन ---
def main():
    # concurrent_updates और drop_pending_updates जाम होने से बचाएंगे
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("delete", delete_topic))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(PollAnswerHandler(handle_answer))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_data))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_data))

    # Render Webhook Setup
    PORT = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0", port=PORT, url_path=TOKEN,
        webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}",
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
