import logging
import os
import json
import asyncio
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

# الإعدادات
BOT_TOKEN = os.environ.get("TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL") # رابط موقعك على Render
SHEET_ID = os.environ.get("SHEET_ID")
MY_ADMIN_ID = int(os.environ.get("ADMIN_ID", 1415885))

CHOOSING, ASKING_ID, ASKING_PHONE, ASKING_VERIFY = range(4)

# إعداد الأزرار
KEYBOARD_LAYOUT = ReplyKeyboardMarkup([['/start', '/help']], resize_keyboard=True)

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

# --- الدوال البرمجية (تم الحفاظ عليها كما هي) ---
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
        await query.edit_message_text("أدخل رقم التحقق (أول 4 من الهاتف + آخر 4 من البطاقة):")
        return ASKING_VERIFY
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
    if phone == str(SHEET_MAIN.cell(row, 2).value).strip():
        headers = SHEET_MAIN.row_values(1)
        values = SHEET_MAIN.row_values(row)
        res = "✅ *بيانات الاستعلام المالي*\n━━━━━━━━━━━━━━\n"
        for h, v in zip(headers, values): res += f"🔹 *{h}:* `{v}`\n"
        await update.message.reply_text(res, parse_mode='Markdown', reply_markup=KEYBOARD_LAYOUT)
        return ConversationHandler.END
    await update.message.reply_text("❌ رقم الهاتف غير مطابق:")
    return ASKING_PHONE

# --- نظام الويب لاستقبال الطلبات ---
async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return web.Response(text="OK")

async def main():
    global bot_app
    bot_app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # إضافة المعالجات (Handlers)
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

    # ضبط الـ Webhook
    await bot_app.bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")

    # تشغيل سيرفر الويب
    app_web = web.Application()
    app_web.router.add_post(f"/{BOT_TOKEN}", handle_webhook)
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())