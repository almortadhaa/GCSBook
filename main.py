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

# 1. إعداد تسجيل الأخطاء
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 2. البيانات الأساسية (تُجلب من إعدادات البيئة في Render)
# يرجى وضع هذه المتغيرات في Render Environment Variables
BOT_TOKEN = os.environ.get("TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")
MY_ADMIN_ID = int(os.environ.get("ADMIN_ID", 1415885))

# مراحل المحادثة
CHOOSING, ASKING_ID, ASKING_PHONE, ASKING_VERIFY = range(4)
COLOR_EMOJIS = ["🔴", "🔵", "🟢", "🟡", "🟠", "🟣", "💎", "🌟"]

def escape_markdown(text):
    parse_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(parse_chars)}])', r'\\\1', str(text))

# 3. اتصال Google Sheets (معدل للعمل مع المتغيرات البيئية)
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
        logging.error(f"فشل الاتصال بجوجل شيت: {e}")
        return None, None, None

# تحميل البيانات (يُنصح باستدعاء get_sheets داخل الدوال عند الحاجة لضمان الاستقرار)
SHEET_MAIN, SHEET_VERIFY, SHEET_LOG = get_sheets()

async def log_to_sheet(user, status_type, phone=""):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row_data = [now, str(user.id), user.full_name, f"@{user.username}", status_type, "", phone]
        SHEET_LOG.append_row(row_data)
    except Exception as e:
        logging.error(f"خطأ في تسجيل البيانات: {e}")

# (هنا يتم لصق باقي دوال البوت من ملف 55.py: start, handle_choice, process_id, إلخ...)
# يرجى التأكد من أن كل دالة تستخدم SHEET_MAIN و SHEET_VERIFY بشكل صحيح.

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    # إضافة المعالجات كما في 55.py
    # ...
    print("🚀 البوت يعمل الآن بنظام الاستقرار لـ Render...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()