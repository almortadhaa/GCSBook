import logging
import os
import json
import asyncio
import re
import random
from datetime import datetime
from aiohttp import web
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler,
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# إعداد السجلات
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

BOT_TOKEN = os.environ.get("TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")
MY_ADMIN_ID = int(os.environ.get("ADMIN_ID", 1415885))
PORT = int(os.environ.get("PORT", 8080))

CHOOSING, ASKING_ID, ASKING_PHONE, ASKING_VERIFY = range(4)
COLOR_EMOJIS = ["🔴", "🔵", "🟢", "🟡", "🟠", "🟣", "💎", "🌟"]

KEYBOARD_LAYOUT = ReplyKeyboardMarkup(
    [['/start', '/help']], 
    resize_keyboard=True, 
    one_time_keyboard=False
)

def escape_markdown(text):
    parse_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(parse_chars)}])', r'\\\1', str(text))

# --- إعدادات Google Sheets ---
def get_sheets():
    try:
        creds_dict = json.loads(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON'))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet.worksheet("Sheet1"), spreadsheet.worksheet("Sheet02"), spreadsheet.worksheet("Visitors_Log")
    except Exception as e:
        logging.error(f"Error connecting to sheets: {e}")
        return None, None, None

SHEET_MAIN, SHEET_VERIFY, SHEET_LOG = get_sheets()

# --- معالجة الأخطاء ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(f"Update {update} caused error {context.error}")

# --- دوال العمل ---
async def log_to_sheet(user, status_type, phone=""):
    try:
        if SHEET_LOG:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            SHEET_LOG.append_row([now, str(user.id), user.full_name, f"@{user.username}", status_type, "", phone])
    except Exception as e:
        logging.warning(f"Logging failed: {e}")

async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start", "ابدأ الاستعلام"),
        BotCommand("help", "تعليمات الاستعلام")
    ])

async def start(update, context):
    await log_to_sheet(update.effective_user, "start")
    keyboard = [[InlineKeyboardButton("نعم أعرفه ✅", callback_data='know'), InlineKeyboardButton("لا أعرفه ❌", callback_data='dont_know')]]
    await update.message.reply_text("أهلاً بك عزيزي الموظف\.\. هل تعرف رقمك الوظيفي؟", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2')
    return CHOOSING

async def help_command(update, context):
    text = (
        "💡 *أخي الموظف:*\n\n"
        "البوت عبارة عن أوامر تتبعها لتصل إلى معرفة بياناتك ومستحقاتك من خلال:\n\n"
        "1️⃣ *أولاً:* الأمر /start لبدء الاستعلام، سيظهر لك خيار \(هل تعرف رقمك الوظيفي؟\).\n"
        "   \- إذا كنت تعرفه: قم بإدخاله \(باللغة الإنجليزية\)، فإذا كان صحيحاً سيطلب منك إدخال رقم هاتفك لتظهر بياناتك\.\n\n"
        "2️⃣ *ثانياً:* إذا كانت إجابتك \(لا أعرفه\): سيطلب منك البوت رقم التحقق وهو \(رقم مزدوج مكون من 8 أرقام: الجزء الاول يمثل الاربعة الأرقام الاولى من هاتفك والجزء الثاني يمثل الاربعة الارقام الاخيرة من بطاقتك الشخصية\)\.\n"
        "   \- إذا كان رقم التحقق صحيحاً: سيظهر لك البوت اسمك ورقمك الوظيفي، احفظه وعاود الاستعلام من جديد\.\n\n"
        "يمكنك الضغط على /start في أي وقت للمواصلة\."
        )
    await update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=KEYBOARD_LAYOUT)

async def handle_choice(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == 'know':
        await query.edit_message_text("أدخل رقمك الوظيفي الآن \(باللغة الإنجليزية\):", parse_mode='MarkdownV2')
        return ASKING_ID
    elif query.data == 'dont_know':
        await query.edit_message_text("أدخل رقم التحقق المكون من \(أول اربعة ارقام من رقم هاتفك \+ آخر اربعة ارقام من بطاقتك\):", parse_mode='MarkdownV2')
        return ASKING_VERIFY
    return CHOOSING

async def process_verify(update, context):
    code = update.message.text.strip()
    cell = SHEET_VERIFY.find(code, in_column=1)
    if cell:
        job_id = escape_markdown(SHEET_VERIFY.cell(cell.row, 2).value)
        name = escape_markdown(SHEET_VERIFY.cell(cell.row, 3).value)
        await update.message.reply_text(f"✅ *تم التحقق\!*\n🆔 رقمك الوظيفي هو: `{job_id}`\n👤الاسم: `{name}`", parse_mode='MarkdownV2', reply_markup=KEYBOARD_LAYOUT)
        return ConversationHandler.END
    await update.message.reply_text("❌ رقم التحقق الذي ادخلته غير مطابق، حاول مجدداً \(باللغة الإنجليزية\):", parse_mode='MarkdownV2')
    return ASKING_VERIFY

async def process_id(update, context):
    user_id = update.message.text.strip()
    cell = SHEET_MAIN.find(user_id, in_column=1)
    if cell:
        context.user_data['row'] = cell.row
        await update.message.reply_text("✅ تم العثور على الرقم\. أرسل رقم هاتفك للتحقق \(باللغة الإنجليزية\):", parse_mode='MarkdownV2')
        return ASKING_PHONE
    await update.message.reply_text("❌ الرقم غير موجود\. حاول مجدداً \(باللغة الإنجليزية\):", parse_mode='MarkdownV2')
    return ASKING_ID

async def process_phone(update, context):
    phone = update.message.text.strip()
    row = context.user_data.get('row')
    row_data = SHEET_MAIN.row_values(row)
    headers = SHEET_MAIN.row_values(1)
    
    if phone == str(row_data[1]).strip():
        await log_to_sheet(update.effective_user, "استعلام ناجح", phone)
        emoji = random.choice(COLOR_EMOJIS)
        res = f"{emoji} *__نتائج الاستعلام المالي__*\n━━━━━━━━━━━━━━\n"
        for h, v in zip(headers, row_data):
            res += f"{emoji} **{escape_markdown(h)}:** __**{escape_markdown(v)}**__\n"
        res += "━━━━━━━━━━━━━━"
        await update.message.reply_text(res, parse_mode='MarkdownV2', reply_markup=KEYBOARD_LAYOUT)
        return ConversationHandler.END
    
    await update.message.reply_text("❌ رقم الهاتف غير مطابق\. حاول مجدداً \(باللغة الإنجليزية\):", parse_mode='MarkdownV2')
    return ASKING_PHONE

# --- تشغيل السيرفر ---
async def start_web_server():
    app_web = web.Application()
    app_web.router.add_get('/', lambda r: web.Response(text="Bot is running 24/7"))
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logging.info(f"Web server started on port {PORT}")

async def main():
    await start_web_server()
    
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    app.add_error_handler(error_handler)
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [CallbackQueryHandler(handle_choice)],
            ASKING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_id)],
            ASKING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_phone)],
            ASKING_VERIFY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_verify)],
        },
        fallbacks=[CommandHandler("start", start), CommandHandler("help", help_command)],
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True) 
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())