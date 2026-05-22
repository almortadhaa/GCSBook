import logging
import asyncio
import os
import json
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
)
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials

# إعدادات البوت
TOKEN = "8404596881:AAELutS84xKY33Vk_BFrG-Fgxmt9YjbiXxA"
SHEET_ID = "1yUQQad8UVJpwJ1QfNKMkL2mTY7eSAS5MxPt-OxXCFCE"

# إعداد التطبيق
app = Flask(__name__)
bot_app = Application.builder().token(TOKEN).build()

# مراحل المحادثة
اختيار, طلب_رقم_وظيفي, طلب_هاتف, طلب_تحقق = range(4)

# دالة الاتصال المعدلة لقراءة متغير البيئة
def الحصول_على_الجداول():
    try:
        creds_json = json.loads(os.environ['GOOGLE_APPLICATION_CREDENTIALS_JSON'])
        scopes = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
        
        العميل = gspread.authorize(creds)
        جدول_البيانات = العميل.open_by_key(SHEET_ID)
        return جدول_البيانات.worksheet("Sheet1"), جدول_البيانات.worksheet("Sheet02"), جدول_البيانات.worksheet("Visitors_Log")
    except Exception as e:
        print(f"Error connecting to sheets: {e}")
        return None, None, None

SHEET_MAIN, SHEET_VERIFY, SHEET_LOG = الحصول_على_الجداول()

async def تسجيل_في_الجدول(المستخدم, نوع_الحالة, الهاتف=""):
    try:
        if SHEET_LOG:
            التاريخ_الحالي = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            SHEET_LOG.append_row([التاريخ_الحالي, str(المستخدم.id), المستخدم.full_name, f"@{المستخدم.username}", نوع_الحالة, "", الهاتف])
    except: pass

async def البدء(update, context):
    المستخدم = update.effective_user
    await تسجيل_في_الجدول(المستخدم, "زائر للبوت")
    لوحة_المفاتيح = [[InlineKeyboardButton("نعم، أعرفه ✅", callback_data='know'), InlineKeyboardButton("لا، لا أعرفه ❌", callback_data='dont_know')]]
    await update.message.reply_text("أهلاً بك.. هل تعرف رقمك الوظيفي؟", reply_markup=InlineKeyboardMarkup(لوحة_المفاتيح))
    return اختيار

async def معالجة_الاختيار(update, context):
    استعلام = update.callback_query
    await استعلام.answer()
    if استعلام.data == 'know':
        await استعلام.edit_message_text("يرجى إدخال رقمك الوظيفي الآن:")
        return طلب_رقم_وظيفي
    elif استعلام.data == 'dont_know':
        await استعلام.edit_message_text("يرجى إدخال رقم التحقق الخاص بك:")
        return طلب_تحقق
    return اختيار

async def معالجة_الرقم_الوظيفي(update, context):
    رقم_وظيفي = update.message.text.strip()
    خلية = SHEET_MAIN.find(رقم_وظيفي, in_column=1)
    if خلية:
        context.user_data['row'] = خلية.row
        await update.message.reply_text("✅ تم العثور على الرقم. يرجى إرسال رقم هاتفك للمطابقة:")
        return طلب_هاتف
    await update.message.reply_text("❌ الرقم الوظيفي غير موجود. حاول مجدداً:")
    return طلب_رقم_وظيفي

async def معالجة_الهاتف(update, context):
    هاتف = update.message.text.strip()
    رقم_الصف = context.user_data.get('row')
    هاتف_الجدول = str(SHEET_MAIN.cell(رقم_الصف, 2).value).strip()
    if هاتف == هاتف_الجدول:
        await تسجيل_في_الجدول(update.effective_user, "موظف قام بالاستعلام", هاتف)
        العناوين = SHEET_MAIN.row_values(1)
        القيم = SHEET_MAIN.row_values(رقم_الصف)
        النتيجة = "✅ تم التحقق بنجاح:\n" + "\n".join([f"{العناوين[i]}: {القيم[i]}" for i in range(len(العناوين))])
        await update.message.reply_text(النتيجة)
        return ConversationHandler.END
    await update.message.reply_text("❌ رقم الهاتف غير مطابق. حاول مجدداً:")
    return طلب_هاتف

# إضافة Handlers
محول_المحادثة = ConversationHandler(
    entry_points=[CommandHandler("start", البدء)],
    states={
        اختيار: [CallbackQueryHandler(معالجة_الاختيار)],
        طلب_رقم_وظيفي: [MessageHandler(filters.TEXT & ~filters.COMMAND, معالجة_الرقم_الوظيفي)],
        طلب_هاتف: [MessageHandler(filters.TEXT & ~filters.COMMAND, معالجة_الهاتف)],
    },
    fallbacks=[CommandHandler("start", البدء)],
)
bot_app.add_handler(محول_المحادثة)

# تهيئة البوت
async def init_bot():
    await bot_app.initialize()
    await bot_app.post_init()

asyncio.run(init_bot())

# مسار الويب هوك
@app.route('/', methods=['GET'])
def home():
    return "البوت يعمل بنجاح", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    json_data = request.get_json(force=True)
    update = Update.de_json(json_data, bot_app.bot)
    asyncio.run(bot_app.process_update(update))
    return "OK", 200

if __name__ == '__main__':
    # التعديل الهام هنا: قراءة المنفذ من البيئة
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)