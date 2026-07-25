import os
import json
import random
import logging
import asyncio
import requests
import time
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, ContextTypes

# 1. लॉगिंग
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. कॉन्फ़िगरेशन
TOKEN = "7908449655:AAFU5S4qmv223fQ0ffK6g80acVxGX3SpO7A"
GITHUB_URL = "https://raw.githubusercontent.com/12jaat24-wq/pankaj-bot/main/quiz_database.json"
WEBHOOK_URL = f"https://pankaj-bot.onrender.com/{TOKEN}"

DB_CACHE = {}

def sync_db():
    """GitHub से तुरंत और पक्का नया डेटा लाने के लिए"""
    global DB_CACHE
    try:
        # यहाँ '?cache_buster=' लगाया है ताकि GitHub पुराने डेटा को न भेजे
        headers = {'Cache-Control': 'no-cache'}
        r = requests.get(f"{GITHUB_URL}?cb={int(time.time())}", headers=headers, timeout=20)
        if r.status_code == 200:
            DB_CACHE = r.json()
            logger.info(f"Sync Successful: {len(DB_CACHE)} topics.")
            return True
    except Exception as e:
        logger.error(f"Sync Error: {e}")
        return False

# 3. क्विज़ लॉजिक
async def send_q(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    ud = context.user_data
    if not ud or 'qs' not in ud: return

    idx = ud.get('idx', 0)
    qs = ud['qs']
    total_qs = len(qs) # अब यह ऑटोमैटिक PDF के सारे सवाल गिनेगा

    if idx >= total_qs:
        score = ud.get('score', 0)
        await context.bot.send_message(chat_id, f"🎊 **रिवीजन संपन्न!**\n\n📊 आपका स्कोर: `{score}/{total_qs}` सही\n\nनया टॉपिक चुनने के लिए /start दबाएँ।")
        ud['busy'] = False
        return

    q = qs[idx]
    try:
        # यहाँ 'total_qs' का उपयोग हो रहा है, जो पक्का PDF के कुल सवाल दिखाएगा
        await context.bot.send_poll(
            chat_id=chat_id,
            question=f"✨ ({idx+1}/{total_qs}) {random.choice(q['variations'])}",
            options=q['options'],
            type=Poll.QUIZ,
            correct_option_id=q['answer'],
            is_anonymous=False,
            explanation="सही उत्तर आपकी मेहनत का परिणाम है! 📚"
        )
        ud['idx'] = idx + 1
    except Exception as e:
        logger.error(f"Poll Error: {e}")

# 4. हैंडलर्स
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    context.user_data.clear()
    
    # अगर शुरू में डेटा नहीं है तो लोड करें
    if not DB_CACHE: sync_db()

    if not DB_CACHE:
        await update.message.reply_text("❌ डेटाबेस लोड नहीं हो सका।")
        return

    icons = ["🔴", "🔵", "🟢", "🟡", "🟣", "💎", "🔥", "🌈"]
    keyboard = [[InlineKeyboardButton(f"{random.choice(icons)} {t}", callback_data=t)] for t in DB_CACHE.keys()]
    
    await update.message.reply_text("🎯 **अपना टॉपिक चुनें:**", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    
    topic_name = query.data
    # पक्का करना कि उस टॉपिक के सारे सवाल लिस्ट में आएँ
    all_qs = list(DB_CACHE.get(topic_name, []))
    
    if not all_qs:
        await query.message.reply_text("❌ इस टॉपिक में कोई सवाल नहीं मिले।")
        return

    # रैंडम शफल ताकि क्रम बदल जाए पर सवाल सारे रहें
    random.shuffle(all_qs)
    
    # यूजर डेटा में पूरे सवाल सेव करना
    context.user_data.update({
        'qs': all_qs, 
        'idx': 0, 
        'score': 0, 
        'busy': True
    })
    
    await query.delete_message()
    # यहाँ यूजर को मैसेज भी दे सकते हैं कि कितने सवाल मिले
    await context.bot.send_message(chat_id, f"📝 इस टॉपिक में कुल {len(all_qs)} सवाल मिले हैं। चलिए शुरू करते हैं!")
    await send_q(context, chat_id)

async def handle_ans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.poll_answer
    user_id = ans.user.id
    ud = context.application.user_data.get(user_id)
    
    if ud and ud.get('busy'):
        idx = ud['idx'] - 1
        if ans.option_ids[0] == ud['qs'][idx]['answer']:
            ud['score'] += 1
        await asyncio.sleep(0.6)
        await send_q(context, user_id)

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """नया डेटा GitHub से तुरंत खींचने के लिए"""
    await update.message.reply_text("⏳ GitHub से ताज़ा सवाल लोड किए जा रहे हैं...")
    if sync_db():
        # यहाँ कुल टॉपिक्स और कुल सवालों की गिनती दिखाएगा
        total_questions = sum(len(v) for v in DB_CACHE.values())
        await update.message.reply_text(f"✅ सिंक सफल!\n📂 कुल टॉपिक्स: {len(DB_CACHE)}\n📚 कुल सवाल: {total_questions}")
    else:
        await update.message.reply_text("❌ सिंक फेल हो गया।")

# 5. MAIN
def main():
    sync_db()
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("refresh", refresh)) # ताज़ा डेटा के लिए
    application.add_handler(CallbackQueryHandler(handle_topic))
    application.add_handler(PollAnswerHandler(handle_ans))

    port = int(os.environ.get("PORT", 10000))
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL,
        drop_pending_updates=True
    )

if __name__ == '__main__':
# --- नया ऑटोमेशन कोड (यहाँ से कॉपी करें) ---
from github import Github
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi

# अपनी चाबियाँ यहाँ भरें
G_KEY = "अपनी_Gemini_Key"
GH_TOKEN = "अपना_GitHub_Token"
MY_REPO = "12jaat24-wq/pankaj-bot"

genai.configure(api_key=G_KEY, transport='rest')
ai_model = genai.GenerativeModel('gemini-pro')

async def add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text
    if "youtube.com" not in link and "youtu.be" not in link:
        return # अगर लिंक नहीं है तो कुछ न करें

    msg = await update.message.reply_text("⏳ वीडियो पढ़ रहा हूँ और सवाल बना रहा हूँ... इसमें 1-2 मिनट लग सकते हैं।")
    
    try:
        # 1. ID निकालना
        v_id = link.split("v=")[1].split("&")[0] if "v=" in link else link.split("/")[-1]
        
        # 2. सबटाइटल्स लाना
        ts = YouTubeTranscriptApi.list_transcripts(v_id)
        try:
            transcript = ts.find_transcript(['hi', 'en'])
        except:
            transcript = ts.find_generated_transcript(['hi', 'en'])
        
        data = transcript.fetch()
        text = " ".join([i['text'] for i in data])

        # 3. AI से सवाल बनवाना
        prompt = f"Make 20 MCQ quiz from this text. JSON format ONLY. Key: 'Class X: Topic'. Text: {text[:8000]}"
        response = ai_model.generate_content(prompt)
        new_quiz = json.loads(response.text.replace('```json', '').replace('```', '').strip())

        # 4. GitHub अपडेट करना
        g = Github(GH_TOKEN)
        repo = g.get_repo(MY_REPO)
        file = repo.get_contents("quiz_database.json")
        db = json.loads(file.decoded_content.decode())
        db.update(new_quiz)
        repo.update_file(file.path, "Bot Auto Update", json.dumps(db, indent=4, ensure_ascii=False), file.sha)

        await msg.edit_text("✅ सफलता! नया टॉपिक जुड़ गया है। अब /start दबाकर देखें।")
    except Exception as e:
        await msg.edit_text(f"❌ गड़बड़ हुई: {str(e)}")

# इसे अपने main() फंक्शन के अंदर handlers के साथ जोड़ें:
# application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), add_link))    
    main()
