import os
import json
import random
import logging
import asyncio
import httpx
import time
from datetime import datetime
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# --- कॉन्फ़िगरेशन (Environment Variables) ---
TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = os.environ.get("REPO_NAME") # Example: "12jaat24-wq/pankaj-bot"
DB_FILE = os.environ.get("DB_FILE", "quiz_database.json")
GITHUB_URL = f"https://api.github.com/repos/{REPO_NAME}/contents/{DB_FILE}"

# --- लॉगिंग और कैचिंग ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

QUIZ_CACHE = {}
STYLISH_NAME = "𝗣𝗔𝗡𝗞𝗔𝗝 𝗤𝗨𝗜𝗭 𝗕𝗢𝗧 𝟮.𝟬"

# --- स्टाइलिश फॉन्ट जनरेटर (Cache Optimized) ---
def style_txt(text):
    normal =  "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    stylish = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝘅𝗬𝘡𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    trans = str.maketrans(normal, stylish)
    return str(text).translate(trans)

# --- शाही बॉक्स डिज़ाइन ---
def make_box(content, title="INFO"):
    box =  f"╔════════════════════╗\n"
    box += f"   {title}   \n"
    box += f"╚════════════════════╝\n\n"
    box += f"{content}"
    return box

# --- मोटिवेशनल शायरियां ---
SHAYARIS = [
    "✨ *मंज़िल उन्हीं को मिलती है, जिनके सपनों में जान होती है,*\n*पंखों से कुछ नहीं होता, हौसलों से उड़ान होती है।*",
    "🔥 *हौसले के तरकश में कोशिश का वो तीर ज़िंदा रख,*\n*हार जा चाहे ज़िंदगी में सब कुछ, मगर फिर से जीतने की उम्मीद ज़िंदा रख।*",
    "🚀 *शुरुआत करने के लिए महान होना ज़रूरी नहीं,*\n*लेकिन महान होने के लिए शुरुआत करना ज़रूरी है।*",
    "💎 *मैदान में हारा हुआ इंसान फिर से जीत सकता है,*\n*लेकिन मन से हारा हुआ इंसान कभी नहीं जीत सकता।*"
]

# --- गिटहब नॉन-ब्लॉकिंग सिंक (Async) ---
async def sync_github():
    global QUIZ_CACHE
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3.raw"}
    async with httpx.AsyncClient() as client:
        try:
            # कैश-बस्टर के लिए टाइमस्टैम्प का उपयोग
            r = await client.get(f"https://raw.githubusercontent.com/{REPO_NAME}/main/{DB_FILE}?t={int(time.time())}", timeout=15.0)
            if r.status_code == 200:
                QUIZ_CACHE = r.json()
                return True
        except Exception as e:
            logger.error(f"Sync Error: {e}")
    return False

# --- कमांड: /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not QUIZ_CACHE: await sync_github()
    
    # यूजर डेटा रिसेट
    context.user_data.clear()
    
    welcome_msg = make_box(f"{random.choice(SHAYARIS)}\n\n🎯 **तैयारी के लिए विषय चुनें:**", style_txt(STYLISH_NAME))
    
    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "💎", "⚡", "🔥"]
    keyboard = []
    topics = sorted(QUIZ_CACHE.keys())
    
    for i in range(0, len(topics), 2):
        row = [InlineKeyboardButton(f"{random.choice(icons)} {style_txt(topics[i])}", callback_data=f"t_{topics[i]}")]
        if i + 1 < len(topics):
            row.append(InlineKeyboardButton(f"{random.choice(icons)} {style_txt(topics[i+1])}", callback_data=f"t_{topics[i+1]}"))
        keyboard.append(row)

    await update.message.reply_text(welcome_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

# --- कमांड: /refresh (Inventory Table) ---
async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text("🌀 `Neural Link Syncing...`", parse_mode=ParseMode.MARKDOWN)
    if await sync_github():
        table = "┌──────────────────┐\n"
        table += "   📋 SUBJECT | MCQS   \n"
        table += "├──────────────────┤\n"
        for t, q in QUIZ_CACHE.items():
            name = (t[:10] + '..') if len(t) > 10 else t.ljust(12)
            table += f" 🔹 {name} | {len(q)} Q\n"
        table += "└──────────────────┘"
        
        res = make_box(f"```\n{table}\n```\n✅ **Data Reloaded!**", style_txt("DATABASE REFRESHED"))
        await m.edit_text(res, parse_mode=ParseMode.MARKDOWN)
    else:
        await m.edit_text("❌ `GitHub Sync Failed!`")

# --- क्विज़ इंजन (Auto-Next 0.5s) ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("t_"):
        topic = query.data[2:]
        questions = list(QUIZ_CACHE.get(topic, []))
        random.shuffle(questions)
        
        context.user_data.update({
            'qs': questions, 'idx': 0, 'score': 0, 'topic': topic, 'total': len(questions)
        })
        await query.delete_message()
        await send_poll(context, query.message.chat_id)

async def send_poll(context, chat_id):
    ud = context.user_data
    idx = ud['idx']
    qs = ud['qs']
    
    if idx >= ud['total']:
        # शाही रिपोर्ट कार्ड
        score = ud['score']
        total = ud['total']
        per = int((score/total)*100)
        medal = "🏆" if per >= 80 else ("🥇" if per >= 60 else "🥈")
        
        report = (
            f"📊 **{style_txt('QUIZ RESULTS')}**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 विषय: `{ud['topic']}`\n"
            f"✅ सही: `{score}` | ❌ गलत: `{total-score}`\n"
            f"🏅 स्कोर: `{per}%` {medal}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔥 /start - फिर से शुरू करें"
        )
        await context.bot.send_message(chat_id, make_box(report, style_txt("REPORT CARD")), parse_mode=ParseMode.MARKDOWN)
        return

    q = qs[idx]
    # रंगीन प्रोग्रेस बार
    progress = (idx + 1)
    bar = "🔹" * progress + "▫️" * (ud['total'] - progress)
    
    await context.bot.send_poll(
        chat_id=chat_id,
        question=f"✨ ({idx+1}/{ud['total']}) {q['variations'][0]}\n{bar}",
        options=q['options'],
        type=Poll.QUIZ,
        correct_option_id=q['answer'],
        is_anonymous=False
    )
    ud['idx'] += 1

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    user_id = ans.user.id
    ud = context.application.user_data.get(user_id)
    
    if ud and 'qs' in ud:
        current_q = ud['qs'][ud['idx']-1]
        if ans.option_ids[0] == current_q['answer']:
            ud['score'] += 1
        
        # 0.5s Fast Next
        await asyncio.sleep(0.5)
        
        # Mock Context for sending next poll
        class Dummy: pass
        dummy_ctx = Dummy()
        dummy_ctx.user_data = ud
        dummy_ctx.bot = context.bot
        await send_poll(dummy_ctx, user_id)

# --- गिटहब डेटा अपडेट (Upload/Delete) ---
async def handle_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = ""
    if update.message.document:
        file = await context.bot.get_file(update.message.document.file_id)
        raw_data = await file.download_as_bytearray()
        content = raw_data.decode('utf-8')
    else:
        content = update.message.text

    if "variations" in content:
        try:
            new_json = json.loads(content.replace('```json', '').replace('```', '').strip())
            m = await update.message.reply_text("⚙️ `Pushing to Vault...`")
            
            # GitHub Update Logic
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            async with httpx.AsyncClient() as client:
                # Get current file SHA
                r = await client.get(GITHUB_URL, headers=headers)
                sha = r.json().get('sha')
                old_data = json.loads(httpx.get(f"https://raw.githubusercontent.com/{REPO_NAME}/main/{DB_FILE}").text)
                old_data.update(new_json)
                
                payload = {
                    "message": "Vault Update via Bot",
                    "content": os.popen(f"echo '{json.dumps(old_data)}' | base64").read().replace('\n',''),
                    "sha": sha
                }
                await client.put(GITHUB_URL, headers=headers, json=payload)
            
            await sync_github()
            await m.edit_text(make_box("✅ **DATABASE UPDATED!**\n/refresh करें।", style_txt("SUCCESS")))
        except Exception as e:
            await update.message.reply_text(f"❌ Error: `{e}`")

async def delete_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args)
    if not topic: return await update.message.reply_text("💡 `/delete TopicName` लिखें।")
    
    if topic in QUIZ_CACHE:
        del QUIZ_CACHE[topic]
        # GitHub Update (Simplified for logic)
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        async with httpx.AsyncClient() as client:
            r = await client.get(GITHUB_URL, headers=headers)
            sha = r.json().get('sha')
            payload = {"message": f"Deleted {topic}", "content": os.popen(f"echo '{json.dumps(QUIZ_CACHE)}' | base64").read().replace('\n',''), "sha": sha}
            await client.put(GITHUB_URL, headers=headers, json=payload)
        
        await update.message.reply_text(make_box(f"💥 विषय: `{topic}` मिटा दिया गया।", style_txt("DELETED")))
    else:
        await update.message.reply_text("❌ विषय नहीं मिला।")

# --- सुपर रिसेट (Anti-Jam) ---
async def super_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.application.bot.delete_webhook(drop_pending_updates=True)
    # Re-set webhook (Use your actual Render URL here)
    webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
    await context.application.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    await update.message.reply_text(make_box("⚡ **System Flushed!**\nडबल टिक अब वापस आ जाएंगे।", style_txt("SUPER RESET")))

# --- मुख्य इंजन ---
def main():
    # concurrent_updates=True जाम को रोकता है
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh))
    app.add_handler(CommandHandler("reset", super_reset))
    app.add_handler(CommandHandler("delete", delete_topic))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(PollAnswerHandler(handle_answer))
    app.add_handler(MessageHandler(filters.Document.ALL | (filters.TEXT & ~filters.COMMAND), handle_data))

    # Render Webhook Setup
    PORT = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0", port=PORT, url_path=TOKEN,
        webhook_url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}",
        drop_pending_updates=True
    )

if __name__ == '__main__':
    main()
