"""
Telegram Bot for FB OTP Automation
Receives numbers file and triggers GitHub Actions
"""

import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Configuration
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
ALLOWED_CHAT_ID = int(os.environ.get('CHAT_ID', '664193835'))

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
# Server Configuration (Supports multiple servers via Env Vars)
# Server Configuration (Supports multiple servers via Env Vars)
SERVERS = {
    "server1": {
        "name": "Server 1 (Main)",
        "repo": os.environ.get('GITHUB_REPO', 'egygo2004/fb-otp'),
        "token": os.environ.get('GITHUB_TOKEN', ''),
        "branch": os.environ.get('GITHUB_BRANCH', 'master')
    }
}

# Check for additional servers in Env Vars (SERVER_2_REPO, SERVER_2_TOKEN, etc.)
for i in range(2, 6): # Support up to 5 servers
    repo_var = f"SERVER_{i}_REPO"
    token_var = f"SERVER_{i}_TOKEN"
    name_var = f"SERVER_{i}_NAME"
    branch_var = f"SERVER_{i}_BRANCH"
    
    if os.environ.get(repo_var) and os.environ.get(token_var):
        SERVERS[f"server{i}"] = {
            "name": os.environ.get(name_var, f"Server {i}"),
            "repo": os.environ.get(repo_var),
            "token": os.environ.get(token_var),
            "branch": os.environ.get(branch_var, 'master')
        }

# ... (omitted code) ...



def get_server_keyboard():
    """Return keyboard for server selection"""
    keyboard = []
    row = []
    for key, data in SERVERS.items():
        row.append(InlineKeyboardButton(f"🖥️ {data['name']}", callback_data=f"select_{key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel_selection")])
    return InlineKeyboardMarkup(keyboard)

def get_main_keyboard():
    """Return main menu keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("🔄 تقدم العملية", callback_data="progress"),
            InlineKeyboardButton("📊 حالة العمليات", callback_data="status")
        ],
        [
            InlineKeyboardButton("🛑 إيقاف الكل", callback_data="cancel"),
            InlineKeyboardButton("❓ مساعدة", callback_data="help")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def post_init(application: Application):
    """Set up bot commands menu"""
    await application.bot.set_my_commands([
        BotCommand("start", "القائمة الرئيسية"),
        BotCommand("status", "حالة العمليات"),
        BotCommand("cancel", "إيقاف الكل"),
        BotCommand("help", "المساعدة")
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        await update.message.reply_text("❌ غير مصرح لك باستخدام هذا البوت")
        return
    
    # Persistent Keyboard (Bottom Buttons)
    reply_keyboard = [
        ["/start", "/status"],
        ["/cancel", "/help"]
    ]
    markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "🤖 مرحباً بك في بوت FB OTP\n\n"
        "📱 لإرسال الأرقام:\n"
        "• أرسل ملف .txt يحتوي على الأرقام\n"
        "• أو اكتب الأرقام مباشرة\n\n"
        "⬇️ اختر من القائمة:",
        reply_markup=markup
    )
    # Also show inline keyboard
    await update.message.reply_text("التحكم السريع:", reply_markup=get_main_keyboard())


async def show_progress(query):
    """Show progress of current running workflow"""
    try:
        headers = {
            "Authorization": f"Bearer {SERVERS['server1']['token']}", # Default to main server for checking
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Check for running workflows
        running_found = False
        for status in ["in_progress", "queued", "waiting"]:
            url = f"https://api.github.com/repos/{SERVERS['server1']['repo']}/actions/runs?status={status}&per_page=1"
            response = requests.get(url, headers=headers)
            runs = response.json().get('workflow_runs', [])
            
            if runs:
                run = runs[0]
                running_found = True
                
                # Get workflow start time
                created = run['created_at'][:16].replace('T', ' ')
                run_id = run['id']
                
                # Try to get jobs info for progress
                jobs_url = f"https://api.github.com/repos/{SERVERS['server1']['repo']}/actions/runs/{run_id}/jobs"
                jobs_response = requests.get(jobs_url, headers=headers)
                jobs_data = jobs_response.json().get('jobs', [])
                
                # Build progress message
                if status == "queued":
                    status_text = "📥 في قائمة الانتظار"
                    progress_bar = "⬜⬜⬜⬜⬜⬜⬜⬜⬜⬜ 0%"
                elif status == "waiting":
                    status_text = "⏳ منتظر"
                    progress_bar = "🟨⬜⬜⬜⬜⬜⬜⬜⬜⬜ 10%"
                else:
                    status_text = "🔄 قيد التنفيذ"
                    # Estimate progress based on steps
                    if jobs_data:
                        job = jobs_data[0]
                        steps = job.get('steps', [])
                        completed = sum(1 for s in steps if s.get('status') == 'completed')
                        total = len(steps) if steps else 1
                        percent = int((completed / total) * 100)
                        filled = percent // 10
                        progress_bar = "🟩" * filled + "⬜" * (10 - filled) + f" {percent}%"
                    else:
                        progress_bar = "🟩🟩🟩⬜⬜⬜⬜⬜⬜⬜ ~30%"
                
                msg = f"""🔄 تقدم العملية الحالية

{status_text}
📅 بدأت: {created}
🆔 ID: {run_id}

{progress_bar}

اضغط 🔄 للتحديث"""
                
                await query.edit_message_text(msg, reply_markup=get_main_keyboard())
                return
        
        if not running_found:
            await query.edit_message_text(
                "📭 لا توجد عمليات جارية حالياً\n\n"
                "أرسل أرقام لبدء عملية جديدة!",
                reply_markup=get_main_keyboard()
            )
            
    except Exception as e:
        await query.edit_message_text(f"❌ خطأ: {e}", reply_markup=get_main_keyboard())


async def show_status(query):
    """Show GitHub Actions status"""
    try:
        url = f"https://api.github.com/repos/{SERVERS['server1']['repo']}/actions/runs?per_page=5"
        headers = {
            "Authorization": f"Bearer {SERVERS['server1']['token']}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        response = requests.get(url, headers=headers)
        runs = response.json().get('workflow_runs', [])
        
        if not runs:
            await query.edit_message_text("📭 لا توجد عمليات سابقة", reply_markup=get_main_keyboard())
            return
        
        status_msg = "📊 آخر 5 عمليات:\n\n"
        for run in runs[:5]:
            status_emoji = "✅" if run['conclusion'] == 'success' else "❌" if run['conclusion'] == 'failure' else "⏳"
            status_msg += f"{status_emoji} {run['created_at'][:16].replace('T', ' ')} - {run['status']}\n"
        
        await query.edit_message_text(status_msg, reply_markup=get_main_keyboard())
    except Exception as e:
        await query.edit_message_text(f"❌ خطأ: {e}", reply_markup=get_main_keyboard())


async def cancel_all_workflows(query):
    """Cancel all running and queued workflows"""
    try:
        headers = {
            "Authorization": f"Bearer {SERVERS['server1']['token']}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        all_runs = []
        
        # Get workflows with different statuses
        for status in ["in_progress", "queued", "waiting"]:
            url = f"https://api.github.com/repos/{SERVERS['server1']['repo']}/actions/runs?status={status}"
            response = requests.get(url, headers=headers)
            runs = response.json().get('workflow_runs', [])
            all_runs.extend(runs)
        
        if not all_runs:
            await query.edit_message_text("📭 لا توجد عمليات جارية أو منتظرة للإيقاف", reply_markup=get_main_keyboard())
            return
        
        cancelled = 0
        for run in all_runs:
            cancel_url = f"https://api.github.com/repos/{SERVERS['server1']['repo']}/actions/runs/{run['id']}/cancel"
            cancel_response = requests.post(cancel_url, headers=headers)
            if cancel_response.status_code == 202:
                cancelled += 1
        
        await query.edit_message_text(
            f"🛑 تم إيقاف {cancelled} عمليات من أصل {len(all_runs)}",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        await query.edit_message_text(f"❌ خطأ: {e}", reply_markup=get_main_keyboard())


async def show_help(query):
    """Show help message"""
    help_text = """❓ المساعدة

📱 لإرسال الأرقام:
• أرسل ملف .txt يحتوي على الأرقام
• أو اكتب الأرقام مباشرة (كل رقم في سطر)

📊 حالة العمليات:
يعرض آخر 5 عمليات

🛑 إيقاف الكل:
يوقف جميع العمليات الجارية

📋 الأوامر:
/start - القائمة الرئيسية
/status - حالة العمليات
/cancel - إيقاف الكل"""
    
    await query.edit_message_text(help_text, reply_markup=get_main_keyboard())


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    await show_status(update.message)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command"""
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    await cancel_all_workflows(update.message)

# Existing handlers...

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("select_"):
        await handle_server_selection(query, context, data.split("_")[1])
    elif data == "cancel_selection":
        if 'pending_numbers' in context.user_data:
            del context.user_data['pending_numbers']
        await query.edit_message_text("❌ تم إلغاء العملية", reply_markup=get_main_keyboard())
    elif data == "progress":
        await show_progress(query)
    elif data == "status":
        await show_status(query)
    elif data == "cancel":
        await cancel_all_workflows(query)
    elif data == "help":
        await show_help(query)


async def handle_server_selection(query, context, server_key):
    """Execute dispatch using the selected server"""
    if 'pending_numbers' not in context.user_data:
        await query.edit_message_text("❌ حدث خطأ: لا توجد أرقام محفوظة. أرسل الملف مرة أخرى.", reply_markup=get_main_keyboard())
        return

    server = SERVERS.get(server_key)
    if not server:
        await query.edit_message_text("❌ هذا السيرفر غير موجود", reply_markup=get_main_keyboard())
        return
        
    numbers = context.user_data['pending_numbers']
    # Clear data
    del context.user_data['pending_numbers']
    
    await query.edit_message_text(
        f"✅ تم اختيار: {server['name']}\n"
        f"⚙️ جاري معالجة {len(numbers)} رقم...\n"
        f"🚀 الإرسال بنظام الدفعات (5 أرقام)..."
    )
    
    # Process batches using the selected server credentials
    batch_size = 5
    total_batches = (len(numbers) + batch_size - 1) // batch_size
    
    success_count = 0
    for i in range(0, len(numbers), batch_size):
        batch = numbers[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        
        # Trigger with specific server creds
        if trigger_github_workflow(batch, server['repo'], server['token'], server.get('branch', 'master')):
            success_count += 1
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"✅ {server['name']} | دفعة {batch_num}/{total_batches} ({len(batch)} أرقام)"
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"❌ {server['name']} | فشل دفعة {batch_num}"
            )
            
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"🏁 انتهى الإرسال لـ {server['name']}!\n({success_count}/{total_batches} ناجحة)",
        reply_markup=get_main_keyboard()
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle received document - Step 1: Store and Ask for Server"""
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    
    document = update.message.document
    if not document.file_name.endswith('.txt'):
        await update.message.reply_text("❌ يرجى إرسال ملف .txt فقط")
        return
    
    file = await context.bot.get_file(document.file_id)
    file_content = await file.download_as_bytearray()
    numbers_text = file_content.decode('utf-8')
    
    numbers = [line.strip() for line in numbers_text.split('\n') if line.strip() and not line.startswith('#')]
    
    if not numbers:
        await update.message.reply_text("❌ الملف فارغ")
        return
    
    # Store numbers in context
    context.user_data['pending_numbers'] = numbers
    
    await update.message.reply_text(
        f"✅ تم استلام {len(numbers)} رقم\n"
        f"📡 الرجاء اختيار السيرفر للتنفيذ:",
        reply_markup=get_server_keyboard()
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text - Step 1: Store and Ask for Server"""
    if update.effective_chat.id != ALLOWED_CHAT_ID:
        return
    
    text = update.message.text
    if text.startswith('/'): return
    
    numbers = [line.strip() for line in text.split('\n') if line.strip()]
    if not numbers: return
    
    # Store numbers in context
    context.user_data['pending_numbers'] = numbers
    
    await update.message.reply_text(
        f"✅ تم استلام {len(numbers)} رقم\n"
        f"📡 الرجاء اختيار السيرفر للتنفيذ:",
        reply_markup=get_server_keyboard()
    )


def trigger_github_workflow(numbers: list, repo: str, token: str, branch: str = 'master') -> bool:
    """Trigger GitHub Actions workflow with dynamic credentials"""
    try:
        url = f"https://api.github.com/repos/{repo}/actions/workflows/fb_otp.yml/dispatches"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        data = {
            "ref": branch,
            "inputs": {
                "numbers": "\n".join(numbers)
            }
        }
        
        response = requests.post(url, headers=headers, json=data)
        return response.status_code == 204
    except Exception as e:
        logger.error(f"Error triggering workflow: {e}")
        return False


def main():
    """Start the bot"""
    logger.info("Starting Telegram Bot...")
    
    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("cancel", cancel))
    
    # Button callback handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    logger.info("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
