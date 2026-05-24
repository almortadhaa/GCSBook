import logging
import os
import json
import random
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, 
    ChatMemberHandler, filters, ContextTypes, ConversationHandler
)
import gspread
from google.oauth2.service_account import Credentials

# 1. إعداد التسجيل للمساعدة في تتبع الأخطاء
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 2. إعدادات البيانات من Render
TOKEN = os.environ.get("TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 1415885))

CHOOSING, ASKING_ID, ASKING_PHONE, ASKING_VERIFY = range(4)
COLOR_EMOJIS = ["🔴", "🔵", "🟢", "🟡", "🟠", "🟣", "💎", "🌟"]

def escape_markdown(text):
    parse_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(parse_chars)}])', r'\\\1', str(text))

# 3. دالة الاتصال المحدثة (مع معالجة الأخطاء)
def get_sheets():
    try:
        creds_json = json.loads(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
        creds = Credentials.from_service_account_info(creds_json, scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        # محاولة فتح الأوراق - إذا لم تجدها ستعطي None لتجنب انهيار البوت
        return spreadsheet.worksheet("Sheet1"), spreadsheet.worksheet("Sheet02"), spreadsheet.worksheet("Visitors_Log")
    except Exception as e:
        logging.error(f"خطأ في الاتصال بجوجل شيت: {e}")
        return None, None, None

# 4. الدوال الأساسية
async def log_to_sheet(user, status_type, phone=""):
    _, _, sheet_log = get_sheets()
    if sheet_log:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet_log.append_row([now, str(user.id), user.full_name, f"@{user.username}", status_type, "", phone])
        except: pass

async def start(update, context):
    await log_to_sheet(update.effective_user, "زائر")
    keyboard = [[InlineKeyboardButton("نعم أعرفه ✅", callback_data='know'), InlineKeyboardButton("لا أعرفه ❌", callback_data='dont_know')]]
    await update.message.reply_text(r"أهلاً بك\.\. هل تعرف رقمك الوظيفي؟", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2')
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
    elif query.data.startswith('auto_id_'):
        job_id = query.data.replace('auto_id_', '')
        sheet_main, _, _ = get_sheets()
        if sheet_main:
            cell = sheet_main.find(job_id, in_column=1)
            if cell:
                context.user_data['row'] = cell.row
                await query.edit_message_text(f"✅ تم اختيار {job_id}، أرسل هاتفك:", parse_mode='MarkdownV2')
                return ASKING_PHONE
    return CHOOSING

async def process_id(update, context):
    user_id = update.message.text.strip()
    sheet_main, _, _ = get_sheets()
    if sheet_main:
        cell = sheet_main.find(user_id, in_column=1)
        if cell:
            context.user_data['row'] = cell.row
            await update.message.reply_text("✅ تم العثور على الرقم. أرسل الآن رقم هاتفك:", parse_mode='MarkdownV2')
            return ASKING_PHONE
    await update.message.reply_text("❌ الرقم غير موجود أو خطأ في الاتصال.")
    return ASKING_ID

async def process_phone(update, context):
    phone = update.message.text.strip()
    row = context.user_data.get('row')
    sheet_main, _, _ = get_sheets()
    if sheet_main:
        sheet_phone = str(sheet_main.cell(row, 2).value).strip()
        if phone == sheet_phone:
            values = sheet_main.row_values(row)
            res = "✅ بيانات الموظف:\n" + "\n".join([f"{v}" for v in values])
            await update.message.reply_text(escape_markdown(res), parse_mode='MarkdownV2')
            return ConversationHandler.END
    await update.message.reply_text("❌ خطأ في المطابقة أو الاتصال.")
    return ASKING_PHONE

def main():
    app = Application.builder().token(TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [CallbackQueryHandler(handle_choice)],
            ASKING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_id)],
            ASKING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_phone)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == '__main__':
    main()