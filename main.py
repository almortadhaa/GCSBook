import logging
import os
import json
import random
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ChatMemberHandler, filters, ContextTypes, ConversationHandler,
)
import gspread
from google.oauth2.service_account import Credentials

# إعداد تسجيل الأخطاء
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# إعداد المتغيرات من Render Environment Variables
BOT_TOKEN = os.environ.get("TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")
MY_ADMIN_ID = int(os.environ.get("ADMIN_ID", 1415885))

# مراحل المحادثة
CHOOSING, ASKING_ID, ASKING_PHONE, ASKING_VERIFY = range(4)
COLOR_EMOJIS = ["🔴", "🔵", "🟢", "🟡", "🟠", "🟣", "💎", "🌟"]

def escape_markdown(text):
    parse_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(parse_chars)}])', r'\\\1', str(text))

# دالة الاتصال الموحدة
def get_sheets():
    try:
        creds_json = json.loads(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
        creds = Credentials.from_service_account_info(creds_json, scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        try:
            sheet_log = spreadsheet.worksheet("Visitors_Log")
        except:
            sheet_log = spreadsheet.add_worksheet(title="Visitors_Log", rows="1000", cols="7")
            sheet_log.append_row(["التاريخ", "ID المستخدم", "الاسم الكامل", "اليوزر نيم", "النوع", "الموقع", "رقم الهاتف للزائر"])
        return spreadsheet.worksheet("Sheet1"), spreadsheet.worksheet("Sheet02"), sheet_log
    except Exception as e:
        logging.error(f"فشل الاتصال: {e}")
        return None, None, None

SHEET_MAIN, SHEET_VERIFY, SHEET_LOG = get_sheets()

async def log_to_sheet(user, status_type, phone=""):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        SHEET_LOG.append_row([now, str(user.id), user.full_name, f"@{user.username}", status_type, "", phone])
    except Exception as e:
        logging.error(f"خطأ في التسجيل: {e}")

# --- الدوال البرمجية (من كود 55.py) ---
async def start(update, context):
    user = update.effective_user
    await log_to_sheet(user, "زائر للبوت")
    context.user_data.clear()
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
    elif query.data.startswith('auto_id_'):
        job_id = query.data.replace('auto_id_', '')
        cell = SHEET_MAIN.find(job_id, in_column=1)
        if cell:
            context.user_data['row'] = cell.row
            context.user_data['job_id'] = job_id
            await query.edit_message_text(f"✅ تم اختيار {job_id}، أرسل رقم الهاتف:")
            return ASKING_PHONE
    return ConversationHandler.END

async def process_id(update, context):
    user_id = update.message.text.strip()
    cell = SHEET_MAIN.find(user_id, in_column=1)
    if cell:
        context.user_data['row'] = cell.row
        context.user_data['job_id'] = user_id
        await update.message.reply_text("✅ تم العثور عليه. أرسل رقم هاتفك:")
        return ASKING_PHONE
    await update.message.reply_text("❌ الرقم غير موجود.")
    return ASKING_ID

async def process_phone(update, context):
    phone = update.message.text.strip()
    row = context.user_data.get('row')
    sheet_phone = str(SHEET_MAIN.cell(row, 2).value).strip()
    if phone == sheet_phone:
        await log_to_sheet(update.effective_user, "موظف قام بالاستعلام", phone)
        values = SHEET_MAIN.row_values(row)
        res = "✅ البيانات:\n" + "\n".join([str(v) for v in values])
        await update.message.reply_text(res)
        return ConversationHandler.END
    await update.message.reply_text("❌ رقم الهاتف غير مطابق.")
    return ASKING_PHONE

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [CallbackQueryHandler(handle_choice)],
            ASKING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_id)],
            ASKING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_phone)],
            ASKING_VERIFY: [MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: None)], # أكمل باقي المعالجات
        },
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()