import logging
import asyncio
import os
import json
import re
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

# إعدادات البوت (تُسحب من Environment Variables في Render)
TOKEN = os.environ.get("TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")

# مراحل المحادثة
CHOOSING, ASKING_ID, ASKING_PHONE, ASKING_VERIFY = range(4)

# إعداد Flask
app = Flask(__name__)

# تهيئة البوت (نؤجل الـ build حتى نحتاجه في الـ webhook)
bot_app = Application.builder().token(TOKEN).build()

def escape_markdown(text):
    parse_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(parse_chars)}])', r'\\\1', str(text))

def get_sheets():
    try:
        creds_json_str = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
        if not creds_json_str:
            return None, None, None
        creds_json = json.loads(creds_json_str)
        creds = Credentials.from_service_account_info(creds_json, scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet.worksheet("Sheet1"), spreadsheet.worksheet("Sheet02"), spreadsheet.worksheet("Visitors_Log")
    except Exception as e:
        print(f"Error loading sheets: {e}")
        return None, None, None

SHEET_MAIN, SHEET_VERIFY, SHEET_LOG = get_sheets()

async def log_to_sheet(user, status_type, phone=""):
    try:
        if SHEET_LOG:
            SHEET_LOG.append_row([str(user.id), user.full_name, f"@{user.username}", status_type, phone])
    except: pass

async def start(update, context):
    user = update.effective_user
    await log_to_sheet(user, "زائر")
    keyboard = [[InlineKeyboardButton("نعم أعرفه ✅", callback_data='know'), InlineKeyboardButton("لا أعرفه ❌", callback_data='dont_know')]]
    await update.message.reply_text("أهلاً بك.. هل تعرف رقمك الوظيفي؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING

async def handle_choice(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == 'know':
        await query.edit_message_text("أدخل رقمك الوظيفي الآن:")
        return ASKING_ID
    elif query.data == 'dont_know':
        await query.edit_message_text("أدخل رقم التحقق:")
        return ASKING_VERIFY
    return CHOOSING

async def process_id(update, context):
    user_id = update.message.text.strip()
    cell = SHEET_MAIN.find(user_id, in_column=1)
    if cell:
        context.user_data['row'] = cell.row
        await update.message.reply_text("✅ تم العثور على الرقم. أرسل الآن رقم هاتفك:")
        return ASKING_PHONE
    await update.message.reply_text("❌ الرقم غير موجود.")
    return ASKING_ID

async def process_phone(update, context):
    phone = update.message.text.strip()
    row = context.user_data.get('row')
    sheet_phone = str(SHEET_MAIN.cell(row, 2).value).strip()
    if phone == sheet_phone:
        await log_to_sheet(update.effective_user, "تم التحقق", phone)
        values = SHEET_MAIN.row_values(row)
        res = "✅ بيانات الموظف:\n" + "\n".join([f"{v}" for v in values])
        await update.message.reply_text(escape_markdown(res), parse_mode='MarkdownV2')
        return ConversationHandler.END
    await update.message.reply_text("❌ رقم الهاتف غير مطابق. حاول مجدداً:")
    return ASKING_PHONE

# تعريف Handlers
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

# الـ Webhook مع معالجة غير متزامنة صحيحة
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        json_data = request.get_json(force=True)
        update = Update.de_json(json_data, bot_app.bot)
        # تشغيل التحديث في حلقة أحداث جديدة
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bot_app.process_update(update))
        return "OK", 200

# هذا الجزء لضمان عمل Render كـ Web Service
if __name__ == '__main__':
    # تشغيل تهيئة البوت (مهم جداً قبل الاستخدام)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(bot_app.initialize())
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)