import os
import json
import random
import asyncio
import httpx
import time
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# --- ENV SETTINGS ---
TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = os.environ.get("REPO_NAME")
DB_FILE = os.environ.get("DB_FILE", "quiz_database.json")
GITHUB_URL = f"https://api.github.com/repos/{REPO_NAME}/contents/{DB_FILE}"

QUIZ_CACHE = {}

# --- STYLISH TOOLS ---
def style_txt(text):
    n = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    s = "𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝘅𝗬𝘡𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
    return str(text).translate(str.maketrans(n, s))

def make_box(title, content):
    return f"╔════════════════════╗\n   {style_txt(title)}   \n╚════════════════════╝\n\n{content}"

SHAYARIS = [
    "✨ *मंज़िल उन्हीं को मिलती है, जिनके सपनों में जान होती है...*",
    "🔥 *हौसले के तरकश में कोशिश का वो तीर ज़िंदा रख...*",
    "🚀 *शुरुआत करने के लिए महान होना ज़रूरी नहीं...*"
]

# --- CORE ENGINE: SYNC ---
async def sync_db():
    global QUIZ_CACHE
    async with httpx.AsyncClient() as client:
        try:
            # Cache buster added (?t=...)
            r = await client.get(f"https://raw.githubusercontent.com/{REPO_NAME}/main/{DB_FILE}?t={int(time.time())}", timeout=15.0)
            if r.status_code == 200:
                QUIZ_CACHE = r.json()
                return True
        except: return False
    return False

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if not QUIZ_CACHE: await sync_db()
    
    text = make_box("PANKAJ QUIZ 2.0", f"{random.choice(SHAYARIS)}\n\n🎯 **तैयारी के लिए विषय चुनें:**")
    btns = [[InlineKeyboardButton(f"💠 {style_txt(t)}", callback_data=f"t_{t}")] for t in sorted(QUIZ_CACHE.keys())]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(btns), parse_mode=ParseMode.MARKDOWN)

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = await update.message.reply_text("🔄 `Syncing Engine...`")
    if await sync_db():
        table = "┌──────────────────┐\n   TOPIC    | MCQS \n├──────────────────┤\n"
        for t, q in QUIZ_CACHE.items():
            table += f" 🔹 {t[:10].ljust(10)} | {len(q)} Q\n"
        table += "└──────────────────┘"
        await m.edit_text(make_box("REFRESHED", f"```\n{table}\n```"), parse_mode=ParseMode.MARKDOWN)

# --- DATA HANDLING (Text & File) ---
async def handle_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = ""
    # फाइल और बड़े टेक्स्ट दोनों को हैंडल करेगा
    if update.message.document:
        file = await context.bot.get_file(update.message.document.file_id)
        b_arr = await file.download_as_bytearray()
        content = b_arr.decode('utf-8')
    else:
        content = update.message.text

    if "variations" in content:
        try:
            new_data = json.loads(content.replace('```json', '').replace('```', '').strip())
            m = await update.message.reply_text("⏳ `Updating GitHub...`")
            
            async with httpx.AsyncClient() as client:
                headers = {"Authorization": f"token {GITHUB_TOKEN}"}
                # Get SHA
                res = await client.get(GITHUB_URL, headers=headers)
                sha = res.json().get('sha')
                
                # Merge and Push
                current_db = QUIZ_CACHE.copy()
                current_db.update(new_data)
                
                import base64
                encoded = base64.b64encode(json.dumps(current_db, indent=4).encode()).decode()
                
                payload = {"message": "Update DB", "content": encoded, "sha": sha}
                await client.put(GITHUB_URL, headers=headers, json=payload)
            
            await sync_db()
            await m.edit_text(make_box("SUCCESS", "✅ डेटा सुरक्षित जोड़ दिया गया!"))
        except Exception as e:
            await update.message.reply_text(f"❌ Error: `{e}`")

# --- QUIZ LOGIC (0.5s Fast Next) ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    topic = query.data[2:]
    qs = list(QUIZ_CACHE.get(topic, []))
    random.shuffle(qs)
    context.user_data.update({'qs': qs, 'idx': 0, 'score': 0, 'topic': topic})
    await query.delete_message()
    await send_poll(context, query.message.chat_id)

async def send_poll(context, chat_id):
    ud = context.user_data
    idx, total = ud['idx'], len(ud['qs'])
    if idx >= total:
        per = int((ud['score']/total)*100)
        medal = "🏆" if per >= 80 else "🥇"
        res = f"📊 **{style_txt('REPORT CARD')}**\n✅ सही: `{ud['score']}/{total}`\n🏆 स्कोर: `{per}%` {medal}"
        await context.bot.send_message(chat_id, make_box("FINISHED", res), parse_mode=ParseMode.MARKDOWN)
        return

    q = ud['qs'][idx]
    bar = "🔹" * (idx + 1) + "▫️" * (total - (idx + 1))
    await context.bot.send_poll(chat_id, f"❓ {q['variations'][0]}\n{bar}", q['options'], type=Poll.QUIZ, correct_option_id=q['answer'], is_anonymous=False)
    ud['idx'] += 1

async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer; uid = ans.user.id
    ud = context.application.user_data.get(uid)
    if ud and 'qs' in ud:
        if ans.option_ids[0] == ud['qs'][ud['idx']-1]['answer']: ud['score'] += 1
        await asyncio.sleep(0.5) # 0.5s Turbo Next
        class TC:
            def __init__(self, u, b): self.user_data=u; self.bot=b
        await send_poll(TC(ud, context.bot), uid)

# --- MAIN ENGINE ---
def main():
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(PollAnswerHandler(handle_ans))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, handle_data))
    
    # Webhook mode logic for Render
    PORT = int(os.environ.get("PORT", 10000))
    app.run_webhook(listen="0.0.0.0", port=PORT, url_path=TOKEN, 
                    webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}", drop_pending_updates=True)

if __name__ == '__main__':
    main()
