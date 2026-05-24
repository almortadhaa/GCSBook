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
MY_ADMIN_ID = int(os.environ.get("ADMIN_ID", 1415885))

CHOOSING, ASKING_ID, ASKING_PHONE, ASKING_VERIFY = range(4)

# إعداد لوحة المفاتيح الثابتة (الأزرار العائمة)
KEYBOARD_LAYOUT = ReplyKeyboardMarkup(
    [['/start', '/help']], 
    resize_keyboard=True, 
    one_time_keyboard=False
)

async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start", "ابدأ الاستعلام"),
        BotCommand("help", "تعليمات الاستعلام")
    ])

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
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        SHEET_LOG.append_row([now, str(user.id), user.full_name, f"@{user.username}", status_type, "", phone])
    except: pass

async def start(update, context):
    await log_to_sheet(update.effective_user, "start")
    keyboard = [[InlineKeyboardButton("نعم أعرفه ✅", callback_data='know'), InlineKeyboardButton("لا أعرفه ❌", callback_data='dont_know')]]
    await update.message.reply_text(
        "أهلاً بك.. هل تعرف رقمك الوظيفي؟", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING

async def help_command(update, context):
    text = (
        "💡 *أخي الموظف:*\n\n"
        "البوت عبارة عن أوامر تتبعها لتصل إلى معرفة بياناتك ومستحقاتك من خلال:\n\n"
        "1️⃣ *أولاً:* الأمر /start لبدء الاستعلام، سيظهر لك خيار (هل تعرف رقمك الوظيفي؟).\n"
        "   - إذا كنت تعرفه: قم بإدخاله، فإذا كان صحيحاً سيطلب منك إدخال رقم هاتفك لتظهر بياناتك.\n\n"
        "2️⃣ *ثانياً:* إذا كانت إجابتك (لا أعرفه): سيطلب منك البوت رقم التحقق (رقم مزدوج مكون من 8 أرقام: 4 أرقام من هاتفك + 4 أرقام من بطاقتك الشخصية).\n"
        "   - إذا كان رقم التحقق صحيحاً: سيظهر لك البوت اسمك ورقمك الوظيفي، احفظه وعاود الاستعلام من جديد.\n\n"
        "يمكنك الضغط على /start في أي وقت للمواصلة."
    )
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=KEYBOARD_LAYOUT)

async def handle_choice(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == 'know':
        await query.edit_message_text("أدخل رقمك الوظيفي:")
        return ASKING_ID
    elif query.data == 'dont_know':
        await query.edit_message_text("أدخل رقم التحقق (أول 4 من الهاتف + آخر 4 من البطاقة):")
        return ASKING_VERIFY
    return CHOOSING

async def process_verify(update, context):
    code = update.message.text.strip()
    cell = SHEET_VERIFY.find(code, in_column=1)
    if cell:
        job_id = SHEET_VERIFY.cell(cell.row, 2).value
        name = SHEET_VERIFY.cell(cell.row, 3).value
        await update.message.reply_text(f"✅ تم التحقق!\nالرقم الوظيفي: `{job_id}`\nالاسم: `{name}`\n\nاضغط /start للبدء من جديد.", parse_mode='Markdown', reply_markup=KEYBOARD_LAYOUT)
        return ConversationHandler.END
    await update.message.reply_text("❌ رقم التحقق غير صحيح، حاول مجدداً:")
    return ASKING_VERIFY

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
    if phone == str(SHEET_MAIN.cell(row, 2).value).strip():
        await log_to_sheet(update.effective_user, "استعلام ناجح", phone)
        headers = SHEET_MAIN.row_values(1)
        values = SHEET_MAIN.row_values(row)
        res = "✅ *بيانات الاستعلام المالي*\n━━━━━━━━━━━━━━\n"
        for h, v in zip(headers, values):
            res += f"🔹 *{h}:* `{v}`\n"
        res += "━━━━━━━━━━━━━━\nاضغط /start للبدء من جديد."
        await update.message.reply_text(res, parse_mode='Markdown', reply_markup=KEYBOARD_LAYOUT)
        return ConversationHandler.END
    await update.message.reply_text("❌ رقم الهاتف غير مطابق:")
    return ASKING_PHONE

async def ignore(update, context):
    # الفلتر يتجاهل أي رسالة نصية خارج الأوامر
    pass

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
        fallbacks=[CommandHandler("start", start), CommandHandler("help", help_command)],
    )
    
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ignore))
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # تشغيل سيرفر الويب
    app_web = web.Application()
    app_web.router.add_get('/', lambda r: web.Response(text="Bot is running"))
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())