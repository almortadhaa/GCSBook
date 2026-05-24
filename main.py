import logging
import asyncio
import os
import json
import re
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
import gspread
from google.oauth2.service_account import Credentials

# --- الإعدادات ---
TOKEN = os.environ.get("TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")
MY_ADMIN_ID = int(os.environ.get("ADMIN_ID", 1415885))

# مراحل المحادثة
CHOOSING, ASKING_ID, ASKING_PHONE, ASKING_VERIFY = range(4)
COLOR_EMOJIS = ["🔴", "🔵", "🟢", "🟡", "🟠", "🟣", "💎", "🌟"]

# --- دوال الخدمة ---
def escape_markdown(text):
    parse_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(parse_chars)}])', r'\\\1', str(text))

def get_sheets():
    try:
        creds_json = json.loads(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
        creds = Credentials.from_service_account_info(creds_json, scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet.worksheet("Sheet1"), spreadsheet.worksheet("Sheet02"), spreadsheet.worksheet("Visitors_Log")
    except Exception as e:
        logging.error(f"فشل الاتصال: {e}")
        return None, None, None

SHEET_MAIN, SHEET_VERIFY, SHEET_LOG = get_sheets()

async def log_to_sheet(user, status_type, phone=""):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row_data = [now, str(user.id), user.full_name, f"@{user.username}", status_type, "", phone]
        SHEET_LOG.append_row(row_data)
    except: pass

# --- منطق البوت (من ملف main0.py) ---
async def start(update, context):
    user = update.effective_user
    await log_to_sheet(user, "زائر للبوت")
    try:
        alert = f"👤 *__دخول زائر جديد__*\n━━━━━━━━━━━━━━\nالاسم: {escape_markdown(user.full_name)}\nالآيدي: `{user.id}`"
        await context.bot.send_message(chat_id=MY_ADMIN_ID, text=alert, parse_mode='MarkdownV2')
    except: pass
    
    keyboard = [[InlineKeyboardButton("نعم أعرفه ✅", callback_data='know'), InlineKeyboardButton("لا أعرفه ❌", callback_data='dont_know')]]
    await update.message.reply_text(r"أهلاً بك\.\. هل تعرف رقمك الوظيفي؟", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2')
    return CHOOSING

async def handle_choice(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == 'know':
        await query.edit_message_text("أدخل رقمك الوظيفي الآن \(باللغة الإنجليزية\):", parse_mode='MarkdownV2')
        return ASKING_ID
    elif query.data == 'dont_know':
        await query.edit_message_text("أدخل رقم التحقق \(أول 4 من الهاتف \+ آخر 4 من البطاقة\):", parse_mode='MarkdownV2')
        return ASKING_VERIFY
    elif query.data.startswith('auto_id_'):
        job_id = query.data.replace('auto_id_', '')
        cell = SHEET_MAIN.find(job_id, in_column=1)
        if cell:
            context.user_data['row'] = cell.row
            await query.edit_message_text(f"✅ تم اختيار الرقم: {job_id}\n\nالآن أدخل رقم الهاتف المربوط بالرقم:", parse_mode='MarkdownV2')
            return ASKING_PHONE
    return CHOOSING

async def process_id(update, context):
    user_id = update.message.text.strip()
    cell = SHEET_MAIN.find(user_id, in_column=1)
    if cell:
        context.user_data['row'] = cell.row
        await update.message.reply_text("✅ تم العثور على الرقم\. أرسل الآن رقم هاتفك للتحقق:", parse_mode='MarkdownV2')
        return ASKING_PHONE
    await update.message.reply_text("❌ الرقم الوظيفي غير موجود\. حاول مجدداً:", parse_mode='MarkdownV2')
    return ASKING_ID

async def process_verify_code(update, context):
    verify_code = update.message.text.strip()
    cell = SHEET_VERIFY.find(verify_code)
    if cell:
        row_data = SHEET_VERIFY.row_values(cell.row)
        res = f"✅ *__تم استرجاع بياناتك__*\nالاسم: {escape_markdown(row_data[1])}\nالرقم: `{escape_markdown(row_data[2])}`"
        keyboard = [[InlineKeyboardButton(f"الاستعلام عن مستحقات الرقم: {row_data[2]} ➡️", callback_data=f"auto_id_{row_data[2]}")]]
        await update.message.reply_text(res, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("❌ رقم التحقق غير موجود\.", parse_mode='MarkdownV2')
    return CHOOSING

async def process_phone(update, context):
    phone = update.message.text.strip()
    row = context.user_data.get('row')
    user = update.effective_user
    sheet_phone = str(SHEET_MAIN.cell(row, 2).value).strip()
    
    if phone == sheet_phone:
        await log_to_sheet(user, "موظف قام بالاستعلام", phone)
        headers = SHEET_MAIN.row_values(1)
        values = SHEET_MAIN.row_values(row)
        emoji = random.choice(COLOR_EMOJIS)
        res = f"{emoji} *__نتائج الاستعلام المالي__*\n━━━━━━━━━━━━━━\n"
        for i in range(len(headers)):
            res += f"{emoji} **{escape_markdown(headers[i])}:** __**{escape_markdown(values[i])}**__\n"
        await update.message.reply_text(res + "━━━━━━━━━━━━━━", parse_mode='MarkdownV2')
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ رقم الهاتف غير مطابق\. حاول مجدداً:", parse_mode='MarkdownV2')
        return ASKING_PHONE

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [CallbackQueryHandler(handle_choice)],
            ASKING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_id)],
            ASKING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_phone)],
            ASKING_VERIFY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_verify_code)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    application.add_handler(conv_handler)
    print("🚀 البوت يعمل الآن بنظام الاستعلام المتقدم (Polling)...")
    application.run_polling()