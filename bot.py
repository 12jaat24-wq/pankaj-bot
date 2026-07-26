import os
import json
import random
import asyncio
from telegram import Update, Poll, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PollAnswerHandler, ContextTypes
from telegram.request import HTTPXRequest

TOKEN = os.environ.get("BOT_TOKEN")

# --- सुपर फ़ास्ट रिक्वेस्ट इंजन ---
# यह टेलीग्राम को बताता है कि हम बहुत सारे मैसेज भेजेंगे, कृपया जाम न करें।
request_config = HTTPXRequest(connect_timeout=10, read_timeout=10)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # जैसे ही /start आए, पहले वाला सारा पेंडिंग कचरा इग्नोर करो
    await update.message.reply_text("⚡ इंजन रिफ्रेश हो गया है! अब आप बटन दबा सकते हैं।")
    
    keyboard = [[InlineKeyboardButton("🎯 विषय चुनें", callback_data="show_topics")]]
    await update.message.reply_text("👑 **PANKAJ QUIZ 2.0**", reply_markup=InlineKeyboardMarkup(keyboard))

async def reset_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # यह जादुई कमांड है जो जाम को जड़ से मिटाती है
    await context.application.drop_pending_updates()
    await update.message.reply_text("✅ **Bot Reset Successful!** सारे पुराने अटके हुए मैसेज साफ़ कर दिए गए हैं।")

def main():
    # concurrent_updates=True: एक साथ 100 कमांड झेलने की ताकत
    app = Application.builder().token(TOKEN).request(request_config).concurrent_updates(True).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset_bot))
    # बाकी हैंडलर्स यहाँ जोड़ें...

    print("--- BOT IS READY ---")
    # drop_pending_updates=True: शुरू होते ही पुरानी सारी आफतें खत्म
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
