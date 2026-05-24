import logging
import asyncio
import os
import json
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)
import gspread
from google.oauth2.service_account import Credentials

# إعدادات البوت (تأكد من تحديثها في إعدادات Render إذا لزم الأمر)
TOKEN = os.environ.get("TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")
CHOOSING, ASKING_ID, ASKING_PHONE = range(3)

# دالة لتنسيق النصوص مع استثناء الشرطة (-) لتظهر في الرسائل
def escape_markdown(text):
    parse_chars = r'_*[]()~`>#+.=|{}.!'
    return re.sub(f'([{re.escape(parse_chars)}])', r'\\\1', str(text))

def get_sheets():
    try:
        creds_json = json.loads(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
        creds = Credentials.from_service_account_info(creds_json, scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet.worksheet("Sheet1"), spreadsheet.worksheet("Visitors_Log")
    except Exception as e:
        print(f"Error loading sheets: {e}")
        return None, None

SHEET_MAIN, SHEET_LOG = get_sheets()

async def start(update, context):
    keyboard = [[InlineKeyboardButton("نعم أعرفه ✅", callback_data='know'), InlineKeyboardButton("لا أعرفه ❌", callback_data='dont_know')]]
    await update.message.reply_text("أهلاً بك في GCSBook.. هل تعرف رقمك الوظيفي؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING

async def handle_choice(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == 'know':
        await query.edit_message_text("أدخل رقمك الوظيفي الآن:")
        return ASKING_ID
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
        values = SHEET_MAIN.row_values(row)
        res = "✅ بيانات الموظف:\n" + "\n".join([f"{v}" for v in values])
        await update.message.reply_text(escape_markdown(res), parse_mode='MarkdownV2')
        return ConversationHandler.END
    await update.message.reply_text("❌ رقم الهاتف غير مطابق. حاول مجدداً:")
    return ASKING_PHONE

if __name__ == '__main__':
    # استخدام Polling بدلاً من Webhook لضمان استقرار البوت
    application = ApplicationBuilder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [CallbackQueryHandler(handle_choice)],
            ASKING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_id)],
            ASKING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_phone)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    
    application.add_handler(conv_handler)
    print("البوت يعمل الآن في وضع Polling... GCSBook")
    application.run_polling()