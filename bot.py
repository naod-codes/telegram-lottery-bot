import logging
import sqlite3
import traceback
import time
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes
)

# ----------------- ዋና መረጃዎች -----------------
TOKEN = "8935886340:AAGKdI-_gn1a778MsviuUcdTwlH8UKbRL2s"
ADMIN_ID = 6655136480                   # የአንተ Telegram User ID

TELEBIRR_NO = "0911010349"              # የቴሌብር ቁጥርህ
CBE_ACCOUNT = "1000123456789"           # የባንክ ቁጥርህ
CBE_NAME = "ናኦድ ..."                    # የባንክ አካውንትህ ስም

TEMP_LOCKS = {}
LOCK_DURATION = 60  # ሰከንድ
# --------------------------------------------------

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_current_ethiopian_date():
    now = datetime.now()
    year = now.year
    month = now.month
    day = now.day

    eth_year = year - 8
    if (month == 9 and day >= 11) or month > 9:
        eth_year = year - 7

    eth_month_num = (month - 9) % 12
    if eth_month_num == 0:
        eth_month_num = 12
        
    return f"{day:02d}/{eth_month_num:02d}/{eth_year} ዓ.ም."

def get_db_connection():
    return sqlite3.connect('lottery.db', timeout=10)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            number INTEGER PRIMARY KEY,
            user_id INTEGER,
            name TEXT,
            status TEXT DEFAULT 'EMPTY',
            pay_type TEXT DEFAULT 'FULL',
            date_registered TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    cursor.execute('SELECT value FROM game_settings WHERE key="start_date"')
    if not cursor.fetchone():
        today_eth = get_current_ethiopian_date()
        cursor.execute('INSERT INTO game_settings (key, value) VALUES ("start_date", ?)', (today_eth,))

    for i in range(1, 101):
        cursor.execute('INSERT OR IGNORE INTO tickets (number, status, pay_type) VALUES (?, "EMPTY", "FULL")', (i,))
    conn.commit()
    conn.close()

init_db()

def get_game_start_date():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM game_settings WHERE key="start_date"')
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return get_current_ethiopian_date()

def is_num_locked_by_other(num, user_id):
    num = str(num)
    if num in TEMP_LOCKS:
        locked_user, lock_time = TEMP_LOCKS[num]
        if time.time() - lock_time < LOCK_DURATION:
            if locked_user != user_id:
                return True
        else:
            del TEMP_LOCKS[num]
    return False

def check_game_completion():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM tickets WHERE status="TAKEN" AND pay_type="FULL"')
    full_count = cursor.fetchone()[0]
    conn.close()
    return full_count == 100

async def notify_all_players_completion(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT user_id FROM tickets WHERE status="TAKEN"')
    rows = cursor.fetchall()
    conn.close()

    unique_user_ids = set()
    for r in rows:
        if r[0]:
            for uid in str(r[0]).split(','):
                if uid.strip().isdigit():
                    unique_user_ids.add(int(uid.strip()))

    broadcast_msg = (
        "🎉 **ደስ የሚስስ ዜና!**\n\n"
        "100ውም የዕጣ ቁጥሮች ተይዘው ሙሉ በሙሉ አልቀዋል! 🥳\n\n"
        "ዕጣው በቅርቡ የሚወጣ ይሆናል። ለሁሉም ተጫዋቾቻችን መልካም ዕድል እንመኛለን! 🤞"
    )

    for uid in unique_user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=broadcast_msg, parse_mode="Markdown")
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Error sending message to {uid}: {e}")

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text="🔔 **100ውም የዕጣ ቁጥሮች ሙሉ በሙሉ ተይዘው አልቀዋል!**\n\nለተሳታፊዎች በሙሉ አውቶማቲክ መልእክት ተልኳል። አሁን ዕጣ ማውጣት ይችላሉ!",
        parse_mode="Markdown"
    )

def get_disclaimer_text():
    game_date = get_game_start_date()
    return (
        f"📜 **የዕጣው ጨዋታ ደንብና መመሪያ (Rules)**\n"
        f"📅 የጨዋታው መጀመሪያ ቀን፦ **{game_date}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"1️⃣ **ቁጥር መምረጥ፦** ከ 1 እስከ 100 ከተዘረዘሩት ክፍት ቁጥሮች ውስጥ የሚፈልጉትን ይምረጡ።\n"
        f"2️⃣ **ክፍያ መፈጸም፦** የተሰጠውን የቴሌብር ወይም የንግድ ባንክ ሂሳብ ቁጥር በመጠቀም ክፍያውን ይላኩ።\n"
        f"💡 በግማሽ ዋጋ (50%) መጫወት ይችላሉ! በግማሽ የተያዘ ቁጥርን የቀረውን 50% በመክፈል ሌላ ሰው ሁለተኛ አጋማሹን መውሰድ ይችላል።\n"
        f"3️⃣ **ማረጋገጫ መላክ፦** ክፍያ ፈጽመው ሲጨርሱ የክፍያውን Screenshot (ፎቶ) ወይም የትራንዛክሽን SMS እዚህ ቦት ላይ ይላኩ።\n"
        f"4️⃣ **ማጽደቅ፦** አድሚኑ ክፍያውን አረጋግጦ ሲያጸድቀው ቁጥሩ በስምዎ በይፋ ይያዛል።\n"
        f"5️⃣ **የዕጣው አሸናፊ፦** 100ውም ቁጥሮች ተይዘው ሲያልቁ አሸናፊው በይፋ የሚታወቅ ይሆናል።\n\n"
        f"💡 የሚፈልጉትን ያህል ቁጥሮች መምረጥ እና መግዛት ይችላሉ!"
    )

def get_dashboard_data():
    game_date = get_game_start_date()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM tickets WHERE status="TAKEN" AND pay_type="FULL"')
    full_taken = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM tickets WHERE status="TAKEN" AND pay_type="HALF"')
    half_taken = cursor.fetchone()[0]
    conn.close()
    
    total = 100
    available = total - full_taken - (half_taken * 0.5)
    percentage = int(((total - available) / total) * 100)
    
    filled_blocks = int(percentage / 10)
    empty_blocks = 10 - filled_blocks
    progress_bar = "▓" * filled_blocks + "░" * empty_blocks
    
    return (
        f"📊 የዕጣው ጨዋታ ሁኔታ (Live Dashboard)\n"
        f"📅 የጨዋታው መጀመሪያ ቀን፦ {game_date}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ በሙሉ የተያዙ፦ {full_taken}\n"
        f"🌓 በግማሽ የተያዙ፦ {half_taken}\n"
        f"🔓 ክፍት እድሎች፦ {available:.1f} / 100\n\n"
        f"📈 የጨዋታው ሂደት፦ {percentage}%\n"
        f"[{progress_bar}]\n\n"
        f"💡 100ውም ቁጥሮች ሲያልቁ የዕጣው አሸናፊ በይፋ ይፋ ይደረጋል!"
    )

def get_user_tickets(user_id):
    game_date = get_game_start_date()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT number, pay_type, user_id FROM tickets WHERE (user_id=? OR user_id LIKE ?) AND status="TAKEN" ORDER BY number ASC', (user_id, f"%{user_id}%"))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return (
            f"👤 የእኔ ቁጥሮች\n"
            f"📅 የጨዋታው መጀመሪያ ቀን፦ {game_date}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⚠ እስካሁን ምንም የጸደቀ የዕጣ ቁጥር የለዎትም። ከታች ቁጥር መርጠው ይግዙ!"
        )
    
    tickets_list = ", ".join([f"[{r[0]}]" + (" (½ ግማሽ)" if r[1] == 'HALF' else " (✅ ሙሉ)") for r in rows])
    return (
        f"👤 የእኔ ቁጥሮች\n"
        f"📅 የጨዋታው መጀመሪያ ቀን፦ {game_date}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎉 የያዟቸው የዕጣ ቁጥሮች፦\n👉 {tickets_list}\n\n"
        f"🔢 የተያዙ ቁጥሮች ብዛት፦ {len(rows)}\n\n"
        f"መልካም ዕድል! 🤞"
    )

def get_main_keyboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT number, status, pay_type FROM tickets ORDER BY number ASC')
    rows = cursor.fetchall()
    conn.close()

    keyboard = []
    row = []
    for num, status, pay_type in rows:
        if status == 'TAKEN':
            btn_text = f"½ {num}" if pay_type == 'HALF' else f"✅ {num}"
        else:
            btn_text = f"⏳ {num}" if str(num) in TEMP_LOCKS and (time.time() - TEMP_LOCKS[str(num)][1] < LOCK_DURATION) else f"{num}"
        
        row.append(InlineKeyboardButton(btn_text, callback_data=f"click_num_{num}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
        
    keyboard.append([
        InlineKeyboardButton("📜 ደንብና መመሪያ", callback_data="show_rules"),
        InlineKeyboardButton("📊 የጨዋታ ሁኔታ", callback_data="show_dashboard"),
        InlineKeyboardButton("👤 የእኔ ቁጥሮች", callback_data="my_tickets")
    ])
    return InlineKeyboardMarkup(keyboard)

# /start ሲባል ህጉና መመሪያው አብሮ ይወጣል
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        f"🎯 **እንኳን ወደ ዕጣ ጨዋታ ቦት በሰላም መጡ!**\n\n"
        f"{get_disclaimer_text()}\n\n"
        f"👇 **ከታች ካሉት ክፍት ቁጥሮች ውስጥ የሚፈልጉትን መርጠው ይጫወቱ፦**"
    )
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def reset_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ ይህንን ማድረግ የሚችለው አድሚኑ ብቻ ነው!")
        return

    today_eth = get_current_ethiopian_date()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE tickets SET user_id=NULL, name=NULL, status="EMPTY", pay_type="FULL", date_registered=NULL')
    cursor.execute('UPDATE game_settings SET value=? WHERE key="start_date"', (today_eth,))
    conn.commit()
    conn.close()
    
    TEMP_LOCKS.clear()

    await update.message.reply_text(
        f"🔄 **አዲስ የዕጣ ዙር በትክክል ተጀምሯል!**\n\n"
        f"• 100ዉም ቁጥሮች ነፃ (ክፍት) ተደርገዋል።\n"
        f"• የጨዋታው መጀመሪያ ቀን ወደ **{today_eth}** ታድሷል።",
        parse_mode="Markdown"
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = query.from_user

    try:
        if data == "show_rules":
            await query.answer()
            rules_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("👈 ወደ ቁጥሮች ተመለስ", callback_data="back_to_numbers")]])
            await query.edit_message_text(get_disclaimer_text(), reply_markup=rules_keyboard, parse_mode="Markdown")

        elif data == "show_dashboard":
            await query.answer()
            dash_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 አድስ (Refresh)", callback_data="show_dashboard")],
                [InlineKeyboardButton("👈 ወደ ቁጥሮች ተመለስ", callback_data="back_to_numbers")]
            ])
            await query.edit_message_text(get_dashboard_data(), reply_markup=dash_keyboard)

        elif data == "my_tickets":
            await query.answer()
            my_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 አድስ (Refresh)", callback_data="my_tickets")],
                [InlineKeyboardButton("👈 ወደ ቁጥሮች ተመለስ", callback_data="back_to_numbers")]
            ])
            await query.edit_message_text(get_user_tickets(user.id), reply_markup=my_keyboard)

        elif data.startswith("click_num_"):
            num = data.split("_")[2]

            if user.id != ADMIN_ID and is_num_locked_by_other(num, user.id):
                await query.answer("⏳ ይህ ቁጥር በሌላ ተጫዋች ክፍያ እየተፈጸመበት ስለሆነ ለ 1 ደቂቃ በጊዜያዊነት ተይዟል። እባክዎን ትንሽ ቆይተው ይሞክሩ!", show_alert=True)
                return

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT status, name, pay_type FROM tickets WHERE number=?', (num,))
            row = cursor.fetchone()
            conn.close()

            if user.id == ADMIN_ID:
                await query.answer()
                owner_name = row[1] if row and row[1] else "አልተያዘም"
                pay_st = "በግማሽ (½)" if row and row[2] == 'HALF' else ("በሙሉ (✅)" if row and row[0] == 'TAKEN' else "ክፍት")

                admin_manage_keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ በአካል ያዝ (Full)", callback_data=f"adm_take_FULL_{num}"),
                        InlineKeyboardButton("🌓 በአካል ያዝ (Half)", callback_data=f"adm_take_HALF_{num}")
                    ],
                    [InlineKeyboardButton("🔓 ነፃ አድርግ (Free)", callback_data=f"adm_free_{num}")],
                    [InlineKeyboardButton("⬅️ ተመለስ", callback_data="back_to_numbers")]
                ])

                await query.edit_message_text(
                    f"👑 **የአድሚን መቆጣጠሪያ - ቁጥር [{num}]**\n\n"
                    f"👤 የአሁኑ ባለቤት(ዎች)፦ **{owner_name}**\n"
                    f"💳 ሁኔታ፦ **{pay_st}**\n\n"
                    f"ምን ማድረግ ይፈልጋሉ?",
                    reply_markup=admin_manage_keyboard,
                    parse_mode="Markdown"
                )
                return

            if row and row[0] == 'TAKEN' and row[2] == 'FULL':
                owner_name = row[1] if row[1] else "ሌላ ተጫዋች"
                await query.answer(f"⚠️ ቁጥር [{num}] በ {owner_name} ሙሉ በሙሉ ተይዟል!", show_alert=True)
                return

            if row and row[0] == 'TAKEN' and row[2] == 'HALF':
                await query.answer()
                context.user_data['selected_num'] = num
                context.user_data['selected_pay_type'] = "HALF"
                TEMP_LOCKS[str(num)] = (user.id, time.time())

                pay_keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📱 Telebirr", callback_data=f"pay_telebirr_{num}_HALF")],
                    [InlineKeyboardButton("🏦 CBE Bank (ንግድ ባንክ)", callback_data=f"pay_cbe_{num}_HALF")],
                    [InlineKeyboardButton("⬅️ ተመለስ", callback_data="back_to_numbers")]
                ])

                await query.edit_message_text(
                    f"📌 **ቁጥር [{num}] በመጀመሪያው ተጫዋች በግማሽ (50%) ተይዟል!**\n\n"
                    f"⏱️ **ይህ ቁጥር ለ 1 ደቂቃ ያህል በጊዜያዊነት ተይዞልዎታል።**\n\n"
                    f"💡 **መመሪያ፦** የቀረውን 50% ክፍያ በመክፈል የዚህን ቁጥር ሁለተኛ አጋማሽ መውሰድ ይችላሉ።\n\n"
                    f"እባክዎን ክፍያ መፈጸም የሚፈልጉበትን መንገድ ይምረጡ፦",
                    reply_markup=pay_keyboard,
                    parse_mode="Markdown"
                )
            else:
                await query.answer()
                select_type_keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ በሙሉ ዋጋ መግዛት", callback_data=f"user_select_FULL_{num}"),
                        InlineKeyboardButton("½ በግማሽ ዋጋ መግዛት", callback_data=f"user_select_HALF_{num}")
                    ],
                    [InlineKeyboardButton("⬅️ ተመለስ", callback_data="back_to_numbers")]
                ])
                await query.edit_message_text(
                    f"📌 **ቁጥር [{num}] መርጠዋል!**\n\n"
                    f"እባክዎን መግዛት የሚፈልጉበትን የክፍያ አይነት ይምረጡ፦\n\n"
                    f"• **በሙሉ ዋጋ** ➔ ሙሉውን የዕጣ ዋጋ ይክፈሉ\n"
                    f"• **በግማሽ ዋጋ** ➔ የዕጣውን ግማሽ (50%) ብቻ ይክፈሉ",
                    reply_markup=select_type_keyboard,
                    parse_mode="Markdown"
                )

        elif data.startswith("user_select_"):
            parts = data.split("_")
            p_type = parts[2]
            num = parts[3]
            
            context.user_data['selected_num'] = num
            context.user_data['selected_pay_type'] = p_type
            TEMP_LOCKS[str(num)] = (user.id, time.time())

            await query.answer()
            pay_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📱 Telebirr", callback_data=f"pay_telebirr_{num}_{p_type}")],
                [InlineKeyboardButton("🏦 CBE Bank (ንግድ ባንክ)", callback_data=f"pay_cbe_{num}_{p_type}")],
                [InlineKeyboardButton("⬅️ ተመለስ", callback_data="back_to_numbers")]
            ])

            if p_type == "HALF":
                msg_text = (
                    f"📌 **ቁጥር [{num}] (½ በግማሽ ዋጋ) መርጠዋል!**\n\n"
                    f"⏱️ **ይህ ቁጥር ለ 1 ደቂቃ ያህል በጊዜያዊነት ተይዞልዎታል።**\n\n"
                    f"💡 **መመሪያ፦** ይህንን ቁጥር በግማሽ ዋጋ ስለያዙ እባክዎን የሙሉውን እጣ **ግማሽ (50%) ብቻ** ይክፈሉ!\n\n"
                    f"ክፍያ መፈጸም የሚፈልጉበትን መንገድ ይምረጡ፦"
                )
            else:
                msg_text = (
                    f"📌 **ቁጥር [{num}] (✅ በሙሉ ዋጋ) መርጠዋል!**\n\n"
                    f"⏱️ **ይህ ቁጥር ለ 1 ደቂቃ ያህል በጊዜያዊነት ተይዞልዎታል።**\n\n"
                    f"💡 **መመሪያ፦** እባክዎን የሙሉውን እጣ ክፍያ ይፈጽሙ!\n\n"
                    f"ክፍያ መፈጸም የሚፈልጉበትን መንገድ ይምረጡ፦"
                )

            await query.edit_message_text(msg_text, reply_markup=pay_keyboard, parse_mode="Markdown")

        elif data.startswith("adm_take_"):
            parts = data.split("_")
            p_type = parts[2]
            num = int(parts[3])
            today_eth = get_current_ethiopian_date()

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE tickets SET user_id=?, name=?, status="TAKEN", pay_type=?, date_registered=? WHERE number=?', (ADMIN_ID, "አድሚን (በአካል)", p_type, today_eth, num))
            conn.commit()
            conn.close()

            TEMP_LOCKS.pop(str(num), None)
            lbl = "በሙሉ ክፍያ" if p_type == "FULL" else "በግማሽ ክፍያ"
            await query.answer(f"✅ ቁጥር [{num}] {lbl} በአካል ተይዟል!", show_alert=True)
            await query.edit_message_text("ከታች ካሉት ቁጥሮች ውስጥ የሚፈልጉትን ይምረጡ፦", reply_markup=get_main_keyboard())

            if check_game_completion():
                await notify_all_players_completion(context)

        elif data.startswith("adm_free_"):
            num = int(data.split("_")[2])
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE tickets SET user_id=NULL, name=NULL, status="EMPTY", pay_type="FULL", date_registered=NULL WHERE number=?', (num,))
            conn.commit()
            conn.close()

            TEMP_LOCKS.pop(str(num), None)
            await query.answer(f"🔓 ቁጥር [{num}] ነፃ ተደርጓል (ተለቋል)!", show_alert=True)
            await query.edit_message_text("ከታች ካሉት ቁጥሮች ውስጥ የሚፈልጉትን ይምረጡ፦", reply_markup=get_main_keyboard())

        elif data.startswith("pay_telebirr_"):
            await query.answer()
            parts = data.split("_")
            num = parts[2]
            p_type = parts[3]

            type_info = "የሂሳቡን ግማሽ (50%) ብቻ" if p_type == "HALF" else "ሙሉውን ክፍያ"
            await query.edit_message_text(
                f"📱 **በ Telebirr ለመክፈል፦**\n\n"
                f"👉 የቴሌብር ቁጥር፦ `{TELEBIRR_NO}`\n\n"
                f"⏱️ **ይህ ቁጥር ለ 1 ደቂቃ ተይዞልዎታል።**\n"
                f"💡 **የመረጡት ክፍያ መጠን፦** {type_info} ይክፈሉ።\n\n"
                f"ክፍያውን ፈጽመው ሲጨርሱ የክፍያ ማረጋገጫ Screenshot (ፎቶ) ወይም የትራንዛክሽን SMS እዚህ ይላኩ!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ተመለስ", callback_data="back_to_numbers")]]),
                parse_mode="Markdown"
            )

        elif data.startswith("pay_cbe_"):
            await query.answer()
            parts = data.split("_")
            num = parts[2]
            p_type = parts[3]

            type_info = "የሂሳቡን ግማሽ (50%) ብቻ" if p_type == "HALF" else "ሙሉውን ክፍያ"
            await query.edit_message_text(
                f"🏦 **በ ንግድ ባንክ (CBE) ለመክፈል፦**\n\n"
                f"👉 ሂሳብ ቁጥር፦ `{CBE_ACCOUNT}`\n"
                f"👉 የባንክ ስም፦ {CBE_NAME}\n\n"
                f"⏱️ **ይህ ቁጥር ለ 1 ደቂቃ ተይዞልዎታል።**\n"
                f"💡 **የመረጡት ክፍያ መጠን፦** {type_info} ይክፈሉ።\n\n"
                f"ክፍያውን ፈጽመው ሲጨርሱ የክፍያ ማረጋገጫ Screenshot (ፎቶ) ወይም የትራንዛክሽን SMS እዚህ ይላኩ!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ተመለስ", callback_data="back_to_numbers")]]),
                parse_mode="Markdown"
            )

        elif data == "back_to_numbers":
            await query.answer()
            await query.edit_message_text("ከታች ካሉት ቁጥሮች ውስጥ የሚፈልጉትን ይምረጡ፦", reply_markup=get_main_keyboard())

        elif data.startswith("appfull_") or data.startswith("apphalf_") or data.startswith("reject_"):
            if user.id != ADMIN_ID:
                await query.answer("⚠️ ይህንን ማድረግ የሚችለው አድሚኑ ብቻ ነው!", show_alert=True)
                return

            await query.answer()
            parts = data.split("_")
            action = parts[0]
            num = int(parts[1])
            target_user_id = int(parts[2])
            today_eth = get_current_ethiopian_date()

            conn = get_db_connection()
            cursor = conn.cursor()

            if action in ["appfull", "apphalf"]:
                cursor.execute('SELECT status, pay_type, user_id, name FROM tickets WHERE number=?', (num,))
                row = cursor.fetchone()

                if row and row[0] == 'TAKEN' and row[1] == 'FULL':
                    conn.close()
                    await query.answer("⚠️ ይህ ቁጥር አስቀድሞ ሙሉ በሙሉ ተይዟል!", show_alert=True)
                    return

                try:
                    chat_member = await context.bot.get_chat(target_user_id)
                    new_name = chat_member.first_name
                except Exception:
                    new_name = "ተጫዋች"

                if row and row[0] == 'TAKEN' and row[1] == 'HALF':
                    combined_users = f"{row[2]},{target_user_id}"
                    combined_names = f"{row[3]} እና {new_name}"
                    final_pay_type = "FULL"
                else:
                    combined_users = str(target_user_id)
                    combined_names = new_name
                    final_pay_type = "FULL" if action == "appfull" else "HALF"

                cursor.execute('UPDATE tickets SET user_id=?, name=?, status="TAKEN", pay_type=?, date_registered=? WHERE number=?', (combined_users, combined_names, final_pay_type, today_eth, num))
                conn.commit()
                conn.close()

                TEMP_LOCKS.pop(str(num), None)

                type_str = "ሙሉ ክፍያ" if final_pay_type == "FULL" else "ግማሽ ክፍያ"
                status_text = f"\n\n✅ ሁኔታ፦ ጸድቋል ({type_str} - Approved on {today_eth})"
                
                if query.message.caption:
                    await query.edit_message_caption(caption=query.message.caption + status_text, reply_markup=None)
                else:
                    await query.edit_message_text(text=query.message.text + status_text, reply_markup=None)

                pay_msg = "ሙሉ ክፍያ (✅)" if final_pay_type == "FULL" else "ግማሽ ክፍያ (½)"
                await context.bot.send_message(chat_id=target_user_id, text=f"🎉 እንኳን ደስ አለዎት!\n\nቁጥር [{num}] በስምዎ በ {pay_msg} በትክክል ተይዟል።\n📅 የተመዘገበበት ቀን፦ {today_eth}\n\nየያዟቸውን ቁጥሮች ለማየት በቦቱ \"👤 የእኔ ቁጥሮች\" የሚለውን በተን ይጫኑ።\n\nመልካም ዕድል! 🤞")

                if check_game_completion():
                    await notify_all_players_completion(context)

            elif action == "reject":
                conn.close()
                TEMP_LOCKS.pop(str(num), None)
                status_text = f"\n\n❌ ሁኔታ፦ ውድቅ ተደርጓል (Rejected by Admin)"
                if query.message.caption:
                    await query.edit_message_caption(caption=query.message.caption + status_text, reply_markup=None)
                else:
                    await query.edit_message_text(text=query.message.text + status_text, reply_markup=None)

                await context.bot.send_message(chat_id=target_user_id, text=f"⚠️ የላኩት ክፍያ ስላልተረጋገጠ ቁጥር [{num}] አልተያዘም። እባክዎን ትክክለኛ የክፍያ መረጃ ወይም Screenshot ይላኩ።")

    except Exception as e:
        logger.error(f"Error handling callback: {e}")
        traceback.print_exc()

async def handle_media_or_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    selected_num = context.user_data.get('selected_num')
    selected_pay_type = context.user_data.get('selected_pay_type', 'FULL')
    today_eth = get_current_ethiopian_date()

    if not selected_num:
        await update.message.reply_text("እባክዎን መጀመሪያ ከቁጥሮቹ ውስጥ አንዱን ይምረጡ። ለመጀመር /start ይበሉ።")
        return

    await update.message.reply_text("📥 የክፍያ መረጃዎ ደርሶናል! አድሚን ክፍያውን አረጋግጦ ቁጥርዎን እስከሚያጸድቅ በትንሹ ይጠብቁ።")

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ ሙሉ ክፍያ", callback_data=f"appfull_{selected_num}_{user.id}"),
            InlineKeyboardButton("½ ግማሽ ክፍያ", callback_data=f"apphalf_{selected_num}_{user.id}")
        ],
        [
            InlineKeyboardButton("❌ ሰርዝ", callback_data=f"reject_{selected_num}_{user.id}")
        ]
    ])

    user_choice_str = "½ ግማሽ ክፍያ (50%)" if selected_pay_type == "HALF" else "✅ ሙሉ ክፍያ (100%)"
    username_str = user.username if user.username else 'የለውም'

    admin_text = (
        "🔔 **አዲስ የዕጣ ጥያቄ!**\n"
        f"📅 ቀን፦ {today_eth}\n\n"
        f"👤 ተጫዋች፦ {user.first_name} (@{username_str})\n"
        f"🆔 ID፦ `{user.id}`\n"
        f"🔢 የመረጠው ቁጥር፦ **{selected_num}**\n"
        f"💳 **የመረጠው ክፍያ ዓይነት፦ {user_choice_str}**\n"
    )

    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_id, caption=admin_text + "\n📸 የተላከ የክፍያ Screenshot", reply_markup=keyboard, parse_mode="Markdown")
    elif update.message.text:
        admin_text += f"\n📝 የላከው SMS/መረጃ:\n{update.message.text}"
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, reply_markup=keyboard, parse_mode="Markdown")
        
    context.user_data.pop('selected_num', None)
    context.user_data.pop('selected_pay_type', None)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('reset', reset_game))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle_media_or_text))
    
    print("🤖 ቦቱ በትክክል መስራት ጀምሯል...")
    app.run_polling(drop_pending_updates=True)