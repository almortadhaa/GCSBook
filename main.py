import logging
import os
import json
import asyncio
from datetime import datetime
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ChatMemberHandler, filters, ContextTypes, ConversationHandler,
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# إعداد السجلات
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

BOT_TOKEN = os.environ.get("TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")

CHOOSING, ASKING_ID, ASKING_PHONE, ASKING_VERIFY = range(4)

KEYBOARD_LAYOUT = ReplyKeyboardMarkup([['/start', '/help']], resize_keyboard=True)

async def post_init(application: Application):
    await application.bot.set_my_commands([BotCommand("start", "ابدأ الاستعلام"), BotCommand("help", "تعليمات")])

def get_sheets():
    try:
        creds_dict = json.loads(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet.worksheet("Sheet1"), spreadsheet.worksheet("Sheet02"), spreadsheet.worksheet("Visitors_Log")
    except: return None, None, None

SHEET_MAIN, SHEET_VERIFY, SHEET_LOG = get_sheets()

async def log_to_sheet(user, status_type, phone=""):
    try:
        SHEET_LOG.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(user.id), user.full_name, f"@{user.username}", status_type, "", phone])
    except: pass

async def start(update, context):
    keyboard = [[InlineKeyboardButton("نعم أعرفه ✅", callback_data='know'), InlineKeyboardButton("لا أعرفه ❌", callback_data='dont_know')]]
    await update.message.reply_text("أهلاً بك.. هل تعرف رقمك الوظيفي؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING

async def handle_choice(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == 'know':
        await query.edit_message_text("أدخل رقمك الوظيفي:")
        return ASKING_ID
    elif query.data == 'dont_know':
        await query.edit_message_text("أدخل رقم التحقق (4 أرقام من الهاتف + 4 أرقام من البطاقة):")
        return ASKING_VERIFY

async def process_verify(update, context):
    code = update.message.text.strip()
    cell = SHEET_VERIFY.find(code, in_column=1)
    if cell:
        # حفظ الرقم الوظيفي للبحث عنه لاحقاً في Sheet1
        job_id = SHEET_VERIFY.cell(cell.row, 2).value
        context.user_data['temp_job_id'] = job_id
        await update.message.reply_text("✅ تم التحقق. الآن أرسل رقم هاتفك لمطابقة البيانات:")
        return ASKING_PHONE
    await update.message.reply_text("❌ رقم التحقق غير صحيح، حاول مجدداً:")
    return ASKING_VERIFY

async def process_phone(update, context):
    phone = update.message.text.strip()
    
    # البحث عن الموظف في Sheet1 (إما من خلال ID مباشر أو عبر التحقق المسبق)
    job_id = context.user_data.get('temp_job_id')
    cell = SHEET_MAIN.find(job_id, in_column=1) if job_id else None
    
    # إذا لم يكن هناك job_id مؤقت، البحث بالرقم الذي أدخله في عملية ID عادية
    if not cell:
        row = context.user_data.get('row')
        cell = SHEET_MAIN.cell(row, 1) if row else None
    
    if cell and str(SHEET_MAIN.cell(cell.row, 2).value).strip() == phone:
        values = SHEET_MAIN.row_values(cell.row)
        headers = SHEET_MAIN.row_values(1)
        res = "✅ *بياناتك المالية*\n━━━━━━━━━━━━━━\n"
        for h, v in zip(headers, values):
            res += f"🔹 *{h}:* `{v}`\n"
        res += "━━━━━━━━━━━━━━\nاضغط /start للاستعلام من جديد."
        await update.message.reply_text(res, parse_mode='Markdown', reply_markup=KEYBOARD_LAYOUT)
        return ConversationHandler.END
    
    await update.message.reply_text("❌ البيانات غير مطابقة. حاول مجدداً:")
    return ASKING_PHONE

async def process_id(update, context):
    user_id = update.message.text.strip()
    cell = SHEET_MAIN.find(user_id, in_column=1)
    if cell:
        context.user_data['row'] = cell.row
        context.user_data['temp_job_id'] = user_id
        await update.message.reply_text("✅ تم العثور على الرقم. أرسل رقم هاتفك للتحقق:")
        return ASKING_PHONE
    await update.message.reply_text("❌ الرقم غير موجود:")
    return ASKING_ID

async def ignore(update, context): pass

async def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [CallbackQueryHandler(handle_choice)],
            ASKING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_id)],
            ASKING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_phone)],
            ASKING_VERIFY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_verify)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ignore))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    app_web = web.Application()
    app_web.router.add_get('/', lambda r: web.Response(text="Bot is running"))
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())