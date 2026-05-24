import logging
import os
import json
import random
import re
import asyncio
from datetime import datetime
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ChatMemberHandler, filters, ContextTypes, ConversationHandler,
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# إعداد السجلات
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# البيانات الأساسية
BOT_TOKEN = os.environ.get("TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")
MY_ADMIN_ID = int(os.environ.get("ADMIN_ID", 1415885))

CHOOSING, ASKING_ID, ASKING_PHONE, ASKING_VERIFY = range(4)
COLOR_EMOJIS = ["🔴", "🔵", "🟢", "🟡", "🟠", "🟣", "💎", "🌟"]

def escape_markdown(text):
    parse_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(parse_chars)}])', r'\\\1', str(text))

def get_sheets():
    try:
        creds_dict = json.loads(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet.worksheet("Sheet1"), spreadsheet.worksheet("Sheet02"), spreadsheet.worksheet("Visitors_Log")
    except Exception as e:
        logging.error(f"خطأ في الاتصال بالشيت: {e}")
        return None, None, None

SHEET_MAIN, SHEET_VERIFY, SHEET_LOG = get_sheets()

async def log_to_sheet(user, status_type, phone=""):
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        SHEET_LOG.append_row([now, str(user.id), user.full_name, f"@{user.username}", status_type, "", phone])
    except Exception as e:
        logging.error(f"خطأ في التسجيل: {e}")

async def start(update, context):
    await log_to_sheet(update.effective_user, "استخدام أمر start")
    keyboard = [[InlineKeyboardButton("نعم أعرفه ✅", callback_data='know'), InlineKeyboardButton("لا أعرفه ❌", callback_data='dont_know')]]
    await update.message.reply_text("أهلاً بك.. هل تعرف رقمك الوظيفي؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING

async def help_command(update, context):
    await log_to_sheet(update.effective_user, "استخدام أمر help")
    await update.message.reply_text("مرحباً! هذا البوت مخصص للاستعلام عن المستحقات.\nاستخدم /start للبدء.")

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
        await update.message.reply_text("✅ تم العثور على الرقم. أرسل رقم هاتفك للتحقق:")
        return ASKING_PHONE
    await update.message.reply_text("❌ الرقم غير موجود. حاول مجدداً:")
    return ASKING_ID

async def process_phone(update, context):
    phone = update.message.text.strip()
    row = context.user_data.get('row')
    sheet_phone = str(SHEET_MAIN.cell(row, 2).value).strip()
    
    if phone == sheet_phone:
        await log_to_sheet(update.effective_user, "استعلام ناجح", phone)
        headers = SHEET_MAIN.row_values(1)
        values = SHEET_MAIN.row_values(row)
        
        res = "✅ *بيانات الاستعلام المالي*\n━━━━━━━━━━━━━━\n"
        for h, v in zip(headers, values):
            res += f"🔹 *{escape_markdown(h)}:* `{escape_markdown(v)}`\n"
        res += "━━━━━━━━━━━━━━\n💡 *شكراً لاستخدامك البوت*"
        
        await update.message.reply_text(res, parse_mode='Markdown')
        return ConversationHandler.END
    
    await update.message.reply_text("❌ رقم الهاتف غير مطابق. حاول مجدداً:")
    return ASKING_PHONE

async def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [CallbackQueryHandler(handle_choice)],
            ASKING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_id)],
            ASKING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_phone)],
        },
        fallbacks=[CommandHandler("start", start), CommandHandler("help", help_command)],
    )
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

async def main():
    # تشغيل البوت
    await run_bot()
    # تشغيل السيرفر لإرضاء Render
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text="Bot is running"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())