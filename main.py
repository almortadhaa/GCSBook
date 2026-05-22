import logging
import asyncio
import os
import json
import random
import re
import requests # تم إضافة المكتبة اللازمة لتنظيف الويب هوك
from datetime import datetime
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)
import gspread
from google.oauth2.service_account import Credentials

# إعدادات البوت
TOKEN = "8404596881:AAELutS84xKY33Vk_BFrG-Fgxmt9YjbiXxA"
SHEET_ID = "1yUQQad8UVJpwJ1QfNKMkL2mTY7eSAS5MxPt-OxXCFCE"
MY_ADMIN_ID = 1415885

# مراحل المحادثة
CHOOSING, ASKING_ID, ASKING_PHONE, ASKING_VERIFY = range(4)
COLOR_EMOJIS = ["🔴", "🔵", "🟢", "🟡", "🟠", "🟣", "💎", "🌟"]

# إعداد Flask و البوت
app = Flask(__name__)
bot_app = Application.builder().token(TOKEN).build()

def escape_markdown(text):
    parse_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(parse_chars)}])', r'\\\1', str(text))

# دالة تنظيف الـ Webhook المزعج
def delete_webhook():
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/deleteWebhook"
        requests.get(url)
        print("✅ Webhook cleaned successfully.")
    except Exception as e:
        print(f"❌ Error cleaning webhook: {e}")

def get_sheets():
    try:
        creds_json_str = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        creds_json = json.loads(creds_json_str)
        creds = Credentials.from_service_account_info(creds_json, scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet.worksheet("Sheet1"), spreadsheet.worksheet("Sheet02"), spreadsheet.worksheet("Visitors_Log")
    except Exception as e:
        return None, None, None

SHEET_MAIN, SHEET_VERIFY, SHEET_LOG = get_sheets()

async def log_to_sheet(user, status_type, phone=""):
    try:
        if SHEET_LOG:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            SHEET_LOG.append_row([now, str(user.id), user.full_name, f"@{user.username}", status_type, "", phone])
    except: pass

async def start(update, context):
    user = update.effective_user
    await log_to_sheet(user, "زائر للبوت")
    keyboard = [[InlineKeyboardButton("نعم أعرفه ✅", callback_data='know'), InlineKeyboardButton("لا أعرفه ❌", callback_data='dont_know')]]
    await update.message.reply_text(r"أهلاً بك.. هل تعرف رقمك الوظيفي؟", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2')
    return CHOOSING

async def handle_choice(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == 'know':
        await query.edit_message_text("أدخل رقمك الوظيفي الآن:", parse_mode='MarkdownV2')
        return ASKING_ID
    elif query.data == 'dont_know':
        await query.edit_message_text("أدخل رقم التحقق:", parse_mode='MarkdownV2')
        return ASKING_VERIFY
    return CHOOSING

async def process_id(update, context):
    user_id = update.message.text.strip()
    cell = SHEET_MAIN.find(user_id, in_column=1)
    if cell:
        context.user_data['row'] = cell.row
        await update.message.reply_text("✅ تم العثور على الرقم. أرسل الآن رقم هاتفك:", parse_mode='MarkdownV2')
        return ASKING_PHONE
    await update.message.reply_text("❌ الرقم غير موجود.", parse_mode='MarkdownV2')
    return ASKING_ID

async def process_phone(update, context):
    phone = update.message.text.strip()
    row = context.user_data.get('row')
    sheet_phone = str(SHEET_MAIN.cell(row, 2).value).strip()
    if phone == sheet_phone:
        await log_to_sheet(update.effective_user, "موظف قام بالاستعلام", phone)
        headers = SHEET_MAIN.row_values(1)
        values = SHEET_MAIN.row_values(row)
        res = "✅ نتائج الاستعلام:\n" + "\n".join([f"{headers[i]}: {values[i]}" for i in range(len(headers))])
        await update.message.reply_text(escape_markdown(res))
        return ConversationHandler.END
    await update.message.reply_text("❌ رقم الهاتف غير مطابق. حاول مجدداً:", parse_mode='MarkdownV2')
    return ASKING_PHONE

# Handlers
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        CHOOSING: [CallbackQueryHandler(handle_choice)],
        ASKING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_id)],
        ASKING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_phone)],
    },
    fallbacks=[CommandHandler("start", start)],
)
bot_app.add_handler(conv_handler)

@app.route('/webhook', methods=['POST'])
def webhook():
    json_data = request.get_json(force=True)
    update = Update.de_json(json_data, bot_app.bot)
    asyncio.run(bot_app.process_update(update))
    return "OK", 200

if __name__ == '__main__':
    # تنفيذ التنظيف عند بدء التشغيل
    delete_webhook()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot_app.initialize())
    loop.run_until_complete(bot_app.start())
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)