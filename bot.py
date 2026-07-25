import os
import json
import random
import logging
import asyncio
import requests
import time
from github import Github
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, MessageHandler, filters, ContextTypes

# --- 1. अपनी चाबियाँ यहाँ भरें ---
TOKEN = "7908449655:AAFU5S4qmv223fQ0ffK6g80acVxGX3SpO7A"
GEMINI_KEY = "AQ.Ab8RN6In1gJ34mMQwtf42udm0EWVLWY0eACvCp2PXXfl5xl8IA"
GITHUB_TOKEN = "ghp_WKcuNgj3oRbZvYSb0X4U3f6tuqc2MF2DXh5K"
REPO_NAME = "12jaat24-wq/pankaj-bot"
DB_FILE = "quiz_database.json"
GITHUB_URL = f"https://raw.githubusercontent.com/{REPO_NAME}/main/{DB_FILE}"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_CACHE = {}

def sync_db():
    global DB_CACHE
    try:
        r = requests.get(f"{GITHUB_URL}?cb={int(time.time())}", timeout=20)
        if r.status_code == 200:
            DB_CACHE = r.json()
            return True
    except: return False

# --- नया जेमिनी फंक्शन (Direct API Call - 'AQ' की के लिए स्पेशल) ---
def ask_gemini_direct(prompt_text):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        res_json = response.json()
        # AI का जवाब निकालना
        return res_json['candidates'][0]['content']['parts'][0]['text']
    else:
        raise Exception(f"API Error {response.status_code}: {response.text}")

async def handle_transcript(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if len(text) < 400: return 

    msg = await update.message.reply_text("⏳ ट्रांसक्रिप्ट मिल गई है! 'AQ' की के साथ AI से बात कर रहा हूँ...")
    
    try:
        # AI को निर्देश
        prompt = f"Make 10 MCQ quiz from this text. Output MUST be ONLY JSON. Format: {{ 'Class X: Topic': [ {{ 'variations': ['Q'], 'options': ['A','B','C','D'], 'answer': 0 }} ] }}. Text: {text[:15000]}"
        
        ai_response = ask_gemini_direct(prompt)
        new_quiz = json.loads(ai_response.replace('```json', '').replace('```', '').strip())

        # GitHub अपडेट
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        file = repo.get_contents(DB_FILE)
        current_db = json.loads(file.decoded_content.decode())
        current_db.update(new_quiz)
        repo.update_file(file.path, "Direct API Update", json.dumps(current_db, indent=4, ensure_ascii=False), file.sha)

        sync_db()
        await msg.edit_text("✅ सफलता! 'AQ' की ने काम कर दिया। नया बटन जुड़ गया है। /start दबाएँ।")
    except Exception as e:
        await msg.edit_text(f"❌ गड़बड़ हुई: {str(e)}")

# --- बाकी बॉट लॉजिक ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sync_db()
    if not DB_CACHE: return await update.message.reply_text("❌ डेटाबेस लोड नहीं हुआ।")
    keyboard = [[InlineKeyboardButton(t, callback_data=t)] for t in DB_CACHE.keys()]
    await update.message.reply_text("🎯 **विषय चुनें:**", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = query.data
    qs = list(DB_CACHE.get(topic, []))
    random.shuffle(qs)
    context.user_data.update({'qs': qs, 'idx': 0, 'score': 0, 'busy': True})
    await query.delete_message()
    await send_q(context, query.message.chat_id)

async def send_q(context, chat_id):
    ud = context.user_data
    idx = ud.get('idx', 0)
    qs = ud['qs']
    if idx >= len(qs):
        await context.bot.send_message(chat_id, f"🎊 क्विज़ खत्म! स्कोर: {ud['score']}/{len(qs)}")
        return
    q = qs[idx]
    await context.bot.send_poll(chat_id=chat_id, question=q['variations'][0], options=q['options'], type=Poll.QUIZ, correct_option_id=q['answer'], is_anonymous=False)
    ud['idx'] = idx + 1

async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    ud = context.application.user_data.get(ans.user.id)
    if ud and ud.get('busy'):
        if ans.option_ids[0] == ud['qs'][ud['idx']-1]['answer']: ud['score'] += 1
        await asyncio.sleep(1)
        await send_q(context, ans.user.id)

def main():
    sync_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_topic))
    app.add_handler(PollAnswerHandler(handle_ans))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_transcript))

    port = int(os.environ.get("PORT", 10000))
    app.run_webhook(listen="0.0.0.0", port=port, url_path=TOKEN, webhook_url=f"https://pankaj-bot.onrender.com/{TOKEN}")

if __name__ == '__main__':
    main()
