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
    [['/start1', '/start2', '/help']],
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
        return (
            spreadsheet.worksheet("Sheet1"),
            spreadsheet.worksheet("Sheet02"),
            spreadsheet.worksheet("Visitors_Log"),
            spreadsheet.worksheet("Sheet03")
        )
    except Exception as e:
        logging.error(f"Error connecting to sheets: {e}")
        return None, None, None, None

SHEET_MAIN, SHEET_VERIFY, SHEET_LOG, SHEET_DEBTS = get_sheets()

# --- معالجة الأخطاء ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error(f"Update {update} caused error {context.error}")

# --- دوال العمل ---
async def log_to_sheet(user, status_type, phone="", visit_type=""):
    try:
        if SHEET_LOG:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            SHEET_LOG.append_row([now, str(user.id), user.full_name, f"@{user.username}", status_type, "", phone, "", visit_type])
    except Exception as e:
        logging.warning(f"Logging failed: {e}")

async def has_used(user_id, command_key):
    """
    يعيد True إذا وُجد في SHEET_LOG سجل لنفس user_id و status_type == command_key
    داخل نفس السنة والشهر الحاليين. إذا لم نتمكن من الوصول إلى SHEET_LOG نعيد False.
    """
    try:
        if not SHEET_LOG:
            # لا يمكن التحقق من السجل — نسمح بالاستخدام (نتجنب منع المستخدمين بسبب فشل الاتصال)
            logging.warning("SHEET_LOG unavailable for has_used check; allowing use by default.")
            return False

        rows = SHEET_LOG.get_all_values()  # كل الصفوف كقائمة قوائم
        now = datetime.now()
        for row in rows:
            try:
                # append_row يضيف: [timestamp, user_id, full_name, @username, status_type, "", phone, "", visit_type]
                if len(row) > 4 and row[1] == str(user_id) and row[4] == command_key:
                    ts_str = row[0]
                    try:
                        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        # محاولة أنماط أخرى إن احتجنا (تجاهل صفوف التوقيت غير المتوقع)
                        continue
                    if ts.year == now.year and ts.month == now.month:
                        return True
            except Exception:
                continue
    except Exception as e:
        logging.warning(f"has_used check failed: {e}")
    return False

async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start1", "استعلام المستحقات"),
        BotCommand("start2", "استعلام الخصميات (الديون)"),
        BotCommand("help", "تعليمات الاستعلام")
    ])

# --- أوامر start1 و start2 ---
async def start1(update, context):
    user = update.effective_user
    # تحقق إن استُخدم /start1 هذا الشهر
    if await has_used(user.id, "start1_initiated"):
        await update.message.reply_text("⚠️ يمكنك الاستعلام عن /start1 مرة واحدة فقط خلال الشهر الجاري\. إذا احتجت المزيد تواصل مع الدعم\.", reply_markup=KEYBOARD_LAYOUT, parse_mode='MarkdownV2')
        return ConversationHandler.END

    # سجل الاستخدام (نحتفظ بالمفتاح start1_initiated كما في السجل القديم)
    await log_to_sheet(user, "start1_initiated")

    context.user_data['inquiry_type'] = 'start1'
    context.user_data['sheet_name'] = 'المستحقات'
    context.user_data['visit_type'] = 'استعلام مستحقات'

    keyboard = [[InlineKeyboardButton("نعم أعرفه ✅", callback_data='know'), InlineKeyboardButton("لا أعرفه ❌", callback_data='dont_know')]]
    await update.message.reply_text(
        "استعلام المستحقات 📊\n\nهل تعرف رقمك الوظيفي؟",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING

async def start2(update, context):
    user = update.effective_user
    # تحقق إن استُخدم /start2 هذا الشهر
    if await has_used(user.id, "start2_initiated"):
        await update.message.reply_text("⚠️ يمكنك الاستعلام عن /start2 مرة واحدة فقط خلال الشهر الجاري\. إذا احتجت المزيد تواصل مع الدعم\.", reply_markup=KEYBOARD_LAYOUT, parse_mode='MarkdownV2')
        return ConversationHandler.END

    await log_to_sheet(user, "start2_initiated")

    context.user_data['inquiry_type'] = 'start2'
    context.user_data['sheet_name'] = 'الخصميات'
    context.user_data['visit_type'] = 'استعلام خصميات'

    keyboard = [[InlineKeyboardButton("نعم أعرفه ✅", callback_data='know'), InlineKeyboardButton("لا أعرفه ❌", callback_data='dont_know')]]
    await update.message.reply_text(
        "استعلام الخصميات (الديون) 💰\n\nهل تعرف رقمك الوظيفي؟",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING

async def help_command(update, context):
    user = update.effective_user
    if await has_used(user.id, "help_used"):
        await update.message.reply_text("⚠️ يمكنك الاطلاع على تعليمات البوت (/help) مرة واحدة فقط خلال الشهر الجاري\. إذا احتجت إعادة التعليمات تواصل مع الدعم\.", reply_markup=KEYBOARD_LAYOUT, parse_mode='MarkdownV2')
        return

    text = (
        "💡 *أخي الموظف:*\n\n"
        "البوت عبارة عن أوامر تتبعها لتصل إلى معرفة بياناتك ومستحقاتك من خلال:\n\n"
        "*أولاً: الأمر /start1 \\(استعلام المستحقات\\):*\n"
        "   \\- سيظهر لك خيار \\(هل تعرف رقمك الوظيفي؟\\)\\.\n"
        "   \\- إذا كنت تعرفه: قم بإدخاله، فإذا كان صحيحاً سيطلب منك إدخال رقم هاتفك لتظهر بيانات مستحقاتك\\.\n\n"
        "*ثانياً: الأمر /start2 \\(استعلام الخصميات\\):*\n"
        "   \\- نفس الخطوات، لكن ستظهر لك بيانات الخصميات والديون المستحقة عليك\\.\n\n"
        "*ثالثاً: إذا كنت لا تعرف رقمك الوظيفي:*\n"
        "   \\- سيطلب منك البوت رقم التحقق \\(رقم مزدوج مكون من 8 أرقام: الجزء الأول الأربعة أرقام الأولى من رقم هاتفك \\+ الجزء الثاني الأربعة أرقام الأخيرة من بطاقتك الشخصية\\)\\.\n"
        "   \\- إذا كان رقم التحقق صحيحاً: سيظهر لك البوت اسمك ورقمك الوظيفي، احفظه وعاود الاستعلام من جديد\\.\n\n"
        "يمكنك الضغط على /start1 أو /start2 في أي وقت للمواصلة\\."
    )
    await update.message.reply_text(text, parse_mode='MarkdownV2', reply_markup=KEYBOARD_LAYOUT)
    await log_to_sheet(user, "help_used")

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
        await update.message.reply_text(
            f"✅ *تم التحقق\!*\n\n"
            f"👤 الاسم: `{name}`\n"
            f"🆔 رقمك الوظيفي هو: `{job_id}`\n\n"
            f"⚠️ *ملاحظة:* احفظ رقمك الوظيفي واضغط /start1 أو /start2 مرة أخرى لمواصلة الاستعلام\.",
            parse_mode='MarkdownV2',
            reply_markup=KEYBOARD_LAYOUT
        )
        return ConversationHandler.END
    await update.message.reply_text("❌ رقم التحقق الذي ادخلته غير مطابق، حاول مجدداً \(باللغة الإنجليزية\):", parse_mode='MarkdownV2')
    return ASKING_VERIFY

async def process_id(update, context):
    user_id = update.message.text.strip()
    inquiry_type = context.user_data.get('inquiry_type', 'start1')

    # اختيار الورقة المناسبة
    sheet = SHEET_MAIN if inquiry_type == 'start1' else SHEET_DEBTS

    if sheet is None:
        await update.message.reply_text("❌ خطأ في الاتصال بقاعدة البيانات\. حاول لاحقاً\.", parse_mode='MarkdownV2')
        return ConversationHandler.END

    try:
        cell = sheet.find(user_id, in_column=1)
        if cell:
            context.user_data['row'] = cell.row
            context.user_data['sheet'] = sheet
            await update.message.reply_text("✅ تم العثور على الرقم\. أرسل رقم هاتفك للتحقق \(باللغة الإنجليزية\):", parse_mode='MarkdownV2')
            return ASKING_PHONE
    except Exception as e:
        logging.error(f"Error finding ID: {e}")

    await update.message.reply_text("❌ الرقم غير موجود\. حاول مجدداً \(باللغة الإنجليزية\):", parse_mode='MarkdownV2')
    return ASKING_ID

async def process_phone(update, context):
    phone = update.message.text.strip()
    row = context.user_data.get('row')
    sheet = context.user_data.get('sheet')

    if sheet is None:
        await update.message.reply_text("❌ خطأ في الاتصال بقاعدة البيانات\. حاول لاحقاً\.", parse_mode='MarkdownV2')
        return ConversationHandler.END

    try:
        row_data = sheet.row_values(row)
        headers = sheet.row_values(1)

        # التحقق من رقم الهاتف
        if phone == str(row_data[1]).strip():
            visit_type = context.user_data.get('visit_type', 'استعلام')
            await log_to_sheet(update.effective_user, "استعلام ناجح", phone, visit_type)

            emoji = random.choice(COLOR_EMOJIS)
            sheet_name = context.user_data.get('sheet_name', 'البيانات')
            res = f"{emoji} *__نتائج استعلام {sheet_name}__*\n━━━━━━━━━━━━━━\n"

            for h, v in zip(headers, row_data):
                if h and v:  # عرض الأعمدة التي لها رؤوس وبيانات
                    res += f"{emoji} **{escape_markdown(h)}:** __**{escape_markdown(v)}**__\n"

            res += "━━━━━━━━━━━━━━"
            await update.message.reply_text(res, parse_mode='MarkdownV2', reply_markup=KEYBOARD_LAYOUT)
            return ConversationHandler.END
        else:
            await update.message.reply_text("❌ رقم الهاتف غير مطابق\. حاول مجدداً \(باللغة الإنجليزية\):", parse_mode='MarkdownV2')
            return ASKING_PHONE

    except Exception as e:
        logging.error(f"Error processing phone: {e}")
        await update.message.reply_text("❌ حدث خطأ\. حاول لاحقاً\.", parse_mode='MarkdownV2')
        return ConversationHandler.END

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

    # ConversationHandler للأوامر
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start1", start1),
            CommandHandler("start2", start2)
        ],
        states={
            CHOOSING: [CallbackQueryHandler(handle_choice)],
            ASKING_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_id)],
            ASKING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_phone)],
            ASKING_VERIFY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_verify)],
        },
        fallbacks=[
            CommandHandler("start1", start1),
            CommandHandler("start2", start2),
            CommandHandler("help", help_command)
        ],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("help", help_command))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())