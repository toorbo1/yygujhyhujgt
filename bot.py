import os
import logging
import asyncio
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from telegram.constants import ParseMode
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Импорт менеджеров базы данных
from database import (
    Database, UserManager, AdminManager, CategoryManager,
    TaskManager, TrackingManager, PendingManager, StatsManager
)

# ==================== НАСТРОЙКИ ====================
TOKEN = os.environ.get('BOT_TOKEN')
MAIN_ADMIN_ID = int(os.environ.get('MAIN_ADMIN_ID', '8358009538'))
TASK_NOTIFICATION_GROUP = os.environ.get('TASK_NOTIFICATION_GROUP', '@wedferfwewf')
REPORT_GROUP = os.environ.get('REPORT_GROUP', '@ertghpjoterg')
BOT_USERNAME = os.environ.get('BOT_USERNAME', 'TrafficWorkeee_bot')

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
CATEGORY_NAME, CATEGORY_PARENT = range(2)
TASK_TITLE, TASK_DESC, TASK_TYPE, TARGET, REWARD, REQUIREMENTS, TASK_CATEGORY = range(7)

# ==================== ОБЩИЕ КОМАНДЫ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await UserManager.get_or_create(user.id, user.username or "", user.first_name)

    # Обработка реферальной ссылки (tracking)
    args = context.args
    if args and args[0]:
        link_id = args[0]
        link = await TrackingManager.get_link(link_id)
        if link:
            await TrackingManager.increment_clicks(link_id)
            await update.message.reply_text(
                f"✅ Переход по ссылке засчитан!\n"
                f"Задание: {link['task_id']}\n"
                f"Пригласивший: {link['user_id']}"
            )
        else:
            await update.message.reply_text("❌ Ссылка недействительна.")
        return

    welcome_text = (
        "🚀 Приветствуем, будущий трафер!\n\n"
        "Переходи по ссылке — мы покажем и научим, как действительно зарабатывать на трафике.\n\n"
        "❗️ Мы работаем ТОЛЬКО с белым трафиком — честно, стабильно и без рисков.\n\n"
        "Вступая в нашу команду, ты получаешь:\n"
        "✅ готового бота для работы\n"
        "✅ подробный и понятный мануал\n"
        "✅ поддержку кураторов\n"
        "✅ работу бок о бок с профессионалами\n"
        "✅ практику, опыт и рост с первого дня\n\n"
        "Если хочешь развиваться и зарабатывать — тебе точно к нам 👇"
    )
    keyboard = [
        [InlineKeyboardButton("📋 Доступные задания", callback_data="tasks")],
        [InlineKeyboardButton("👤 Профиль", callback_data="profile"),
         InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    if update.message:
        await update.message.reply_text(
            welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.callback_query.message.reply_text(
            welcome_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "❓ <b>Помощь по боту</b>\n\n"
        "🔹 <b>/start</b> — главное меню\n"
        "🔹 <b>/tasks</b> — список заданий\n"
        "🔹 <b>/profile</b> — твой профиль и статистика\n"
        "🔹 <b>/my_tasks</b> — взятые задания\n\n"
        "📌 <b>Как работать?</b>\n"
        "1. Выбери задание из списка\n"
        "2. Нажми «Взять» — бот создаст твою личную ссылку\n"
        "3. Администратор выдаст рабочую ссылку\n"
        "4. Приводи людей по своей ссылке и зарабатывай\n\n"
        "По всем вопросам: @support"
    )
    if update.message:
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
    else:
        await update.callback_query.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await UserManager.get(user_id)
    if not user:
        if update.message:
            await update.message.reply_text("❌ Профиль не найден. Введите /start для регистрации.")
        else:
            await update.callback_query.message.reply_text("❌ Профиль не найден. Введите /start для регистрации.")
        return
    stats = await UserManager.get_stats(user_id)
    joined_date = user['joined_date'].strftime('%d.%m.%Y') if user['joined_date'] else 'неизвестно'
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"ID: {user_id}\n"
        f"Имя: {user['first_name']}\n"
        f"Username: @{user['username'] if user['username'] else 'нет'}\n"
        f"Дата регистрации: {joined_date}\n\n"
        f"📊 <b>Статистика</b>\n"
        f"✅ Выполнено заданий: {stats['completed_count']}\n"
        f"⚡ Активных заданий: {stats['active_count']}\n"
        f"💰 Заработано: {stats['total_earned']} ₽\n"
        f"⭐ Рейтинг: {stats['rating']}"
    )
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    else:
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.HTML)

async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать доступные задания с фильтром по категориям"""
    categories = await CategoryManager.get_children(None)
    keyboard = []
    for cat in categories:
        keyboard.append([InlineKeyboardButton(cat['name'], callback_data=f"cat_{cat['id']}")])
    keyboard.append([InlineKeyboardButton("📋 Все задания", callback_data="all_tasks")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_main")])

    if update.message:
        await update.message.reply_text(
            "📁 Выберите категорию задания:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.callback_query.message.reply_text(
            "📁 Выберите категорию задания:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks_list = await TaskManager.get_user_tasks(user_id)
    if not tasks_list:
        if update.message:
            await update.message.reply_text("📭 У вас пока нет взятых заданий.")
        else:
            await update.callback_query.message.reply_text("📭 У вас пока нет взятых заданий.")
        return

    text = "📋 <b>Ваши задания</b>\n\n"
    for task in tasks_list:
        status_emoji = "✅" if task.get('completed', False) else "⏳"
        text += f"{status_emoji} <b>{task['title']}</b>\n"
        text += f"ID: <code>{task['task_id']}</code>\n"
        text += f"Статус: {'Выполнено' if task.get('completed', False) else 'В работе'}\n"
        if task.get('earned'):
            text += f"Заработано: {task['earned']} ₽\n"
        text += "\n"
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    else:
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.HTML)

# ==================== КОМАНДЫ АДМИНИСТРАТОРОВ ====================
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_main_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только главный админ может добавлять администраторов.")
        return
    try:
        user_id = int(context.args[0])
        username = context.args[1] if len(context.args) > 1 else ""
        await AdminManager.add_admin(user_id, username, update.effective_user.id)
        await update.message.reply_text(f"✅ Пользователь {user_id} теперь администратор.")
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /add_admin <user_id> [username]")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_main_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только главный админ может удалять администраторов.")
        return
    try:
        user_id = int(context.args[0])
        success = await AdminManager.remove_admin(user_id)
        if success:
            await update.message.reply_text(f"✅ Администратор {user_id} удалён.")
        else:
            await update.message.reply_text("❌ Нельзя удалить главного админа.")
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /remove_admin <user_id>")

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    admins = await AdminManager.get_all_admins()
    text = "👑 <b>Список администраторов</b>\n\n"
    for admin in admins:
        main = " (главный)" if admin['user_id'] == MAIN_ADMIN_ID else ""
        text += f"• {admin['user_id']} - @{admin['username'] or 'нет'}{main}\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# --- Управление категориями ---
async def categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    keyboard = [
        [InlineKeyboardButton("➕ Создать категорию", callback_data="admin_add_category")],
        [InlineKeyboardButton("📋 Список категорий", callback_data="admin_list_categories")],
        [InlineKeyboardButton("🗑 Удалить категорию", callback_data="admin_del_category")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
    ]
    await update.message.reply_text(
        "📁 <b>Управление категориями</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def add_category_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Введите название новой категории:\n\n"
        "(или отправьте /cancel для отмены)"
    )
    return CATEGORY_NAME

async def add_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Создание категории отменено.")
        context.user_data.clear()
        return ConversationHandler.END
        
    context.user_data['category_name'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("📁 Корневая категория", callback_data="cat_parent_none")],
        [InlineKeyboardButton("🔽 Подкатегория", callback_data="cat_parent_select")],
        [InlineKeyboardButton("🔙 Отмена", callback_data="cancel_category")]
    ]
    await update.message.reply_text(
        "Выберите тип категории:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CATEGORY_PARENT

async def add_category_parent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cat_parent_none":
        parent_id = None
        name = context.user_data.get('category_name', 'Без названия')
        await CategoryManager.create(name, parent_id, update.effective_user.id)
        await query.edit_message_text(f"✅ Категория «{name}» создана!")
        context.user_data.clear()
        return ConversationHandler.END
        
    elif query.data == "cat_parent_select":
        cats = await CategoryManager.get_children(None)
        if not cats:
            await query.edit_message_text("❌ Нет корневых категорий. Сначала создайте корневую.")
            context.user_data.clear()
            return ConversationHandler.END
            
        keyboard = []
        for cat in cats:
            keyboard.append([InlineKeyboardButton(cat['name'], callback_data=f"cat_parent_{cat['id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Отмена", callback_data="cancel_category")])
        
        await query.edit_message_text(
            "Выберите родительскую категорию:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CATEGORY_PARENT
        
    elif query.data.startswith("cat_parent_"):
        parent_id = int(query.data.split('_')[-1])
        name = context.user_data.get('category_name', 'Без названия')
        await CategoryManager.create(name, parent_id, update.effective_user.id)
        await query.edit_message_text(f"✅ Подкатегория «{name}» создана!")
        context.user_data.clear()
        return ConversationHandler.END
        
    elif query.data == "cancel_category":
        await query.edit_message_text("❌ Создание категории отменено.")
        context.user_data.clear()
        return ConversationHandler.END
        
    return ConversationHandler.END

# --- Создание задания ---
async def create_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return ConversationHandler.END
    await update.message.reply_text(
        "Введите название задания:\n\n"
        "(или отправьте /cancel для отмены)"
    )
    return TASK_TITLE

async def create_task_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Создание задания отменено.")
        context.user_data.clear()
        return ConversationHandler.END
        
    context.user_data['task_title'] = update.message.text
    await update.message.reply_text(
        "Введите описание задания:\n\n"
        "(или отправьте /cancel для отмены)"
    )
    return TASK_DESC

async def create_task_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Создание задания отменено.")
        context.user_data.clear()
        return ConversationHandler.END
        
    context.user_data['task_desc'] = update.message.text
    await update.message.reply_text(
        "Выберите тип цели:\n"
        "channel - канал\n"
        "post - пост\n"
        "link - ссылка\n\n"
        "(или отправьте /cancel для отмены)"
    )
    return TASK_TYPE

async def create_task_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Создание задания отменено.")
        context.user_data.clear()
        return ConversationHandler.END
        
    t = update.message.text.lower()
    if t not in ['channel', 'post', 'link']:
        await update.message.reply_text("Пожалуйста, введите channel, post или link.")
        return TASK_TYPE
    context.user_data['task_type'] = t
    await update.message.reply_text(
        "Введите цель (username канала, ссылку на пост и т.д.):\n\n"
        "(или отправьте /cancel для отмены)"
    )
    return TARGET

async def create_task_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Создание задания отменено.")
        context.user_data.clear()
        return ConversationHandler.END
        
    context.user_data['target'] = update.message.text
    await update.message.reply_text(
        "Введите награду за выполнение (число):\n\n"
        "(или отправьте /cancel для отмены)"
    )
    return REWARD

async def create_task_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Создание задания отменено.")
        context.user_data.clear()
        return ConversationHandler.END
        
    try:
        reward = float(update.message.text)
        context.user_data['reward'] = reward
    except ValueError:
        await update.message.reply_text("Введите число (например, 100.50):")
        return REWARD
    await update.message.reply_text(
        "Введите требования к выполнению (или отправьте 'нет'):\n\n"
        "(или отправьте /cancel для отмены)"
    )
    return REQUIREMENTS

async def create_task_requirements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Создание задания отменено.")
        context.user_data.clear()
        return ConversationHandler.END
        
    req = update.message.text
    context.user_data['requirements'] = req if req.lower() != 'нет' else ""
    cats = await CategoryManager.get_all()
    if not cats:
        context.user_data['category_id'] = None
        await create_task_finish(update, context)
        context.user_data.clear()
        return ConversationHandler.END
    
    keyboard = []
    for cat in cats:
        prefix = "  " * (1 if cat['parent_id'] else 0)
        keyboard.append([InlineKeyboardButton(f"{prefix}{cat['name']}", callback_data=f"task_cat_{cat['id']}")])
    keyboard.append([InlineKeyboardButton("⏭ Без категории", callback_data="task_cat_none")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="task_cat_cancel")])
    
    await update.message.reply_text(
        "Выберите категорию задания:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TASK_CATEGORY

async def create_task_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "task_cat_cancel":
        await query.edit_message_text("❌ Создание задания отменено.")
        context.user_data.clear()
        return ConversationHandler.END
        
    if data == "task_cat_none":
        context.user_data['category_id'] = None
    else:
        cat_id = int(data.split('_')[-1])
        context.user_data['category_id'] = cat_id
    
    await create_task_finish(query, context)
    context.user_data.clear()
    return ConversationHandler.END

async def create_task_finish(update, context):
    title = context.user_data.get('task_title', '')
    desc = context.user_data.get('task_desc', '')
    task_type = context.user_data.get('task_type', '')
    target = context.user_data.get('target', '')
    reward = context.user_data.get('reward', 0)
    req = context.user_data.get('requirements', '')
    cat_id = context.user_data.get('category_id')

    task_id = await TaskManager.create(
        title, desc, task_type, target, reward,
        update.effective_user.id, cat_id, req
    )
    text = f"✅ Задание создано!\nID: <code>{task_id}</code>"
    if isinstance(update, Update):
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    else:
        await update.edit_message_text(text, parse_mode=ParseMode.HTML)

# --- Выдача рабочей ссылки админом ---
async def give_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    try:
        task_id = context.args[0]
        work_link = context.args[1]
    except IndexError:
        await update.message.reply_text("Использование: /give_link <task_id> <ссылка>")
        return
    
    pending = await PendingManager.get(task_id)
    if not pending:
        await update.message.reply_text("❌ Задание не найдено в ожидающих или уже обработано.")
        return
    
    await TaskManager.set_work_link(task_id, work_link)
    await PendingManager.mark_processed(task_id)
    
    try:
        await context.bot.send_message(
            pending['user_id'],
            f"🔗 Администратор выдал рабочую ссылку для задания <b>{pending['task_title']}</b>:\n{work_link}\n\n"
            f"Используйте свою персональную ссылку для приглашений: {pending['tracking_link']}",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение пользователю {pending['user_id']}: {e}")
    
    await update.message.reply_text(f"✅ Ссылка выдана для задания {task_id}.")

async def pending_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    pendings = await TaskManager.get_pending_links()
    if not pendings:
        await update.message.reply_text("📭 Нет ожидающих ссылок.")
        return
    text = "⏳ <b>Ожидают ссылку:</b>\n\n"
    for p in pendings:
        text += f"🔸 <b>{p['task_title']}</b>\n"
        text += f"ID: <code>{p['task_id']}</code>\n"
        text += f"Пользователь: @{p['username'] or p['user_id']}\n"
        text += f"Ссылка для отслеживания: {p['tracking_link']}\n"
        text += f"Ожидает с {p['message_sent'].strftime('%d.%m %H:%M')}\n\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return
    stats = await StatsManager.get_global()
    text = (
        "📊 <b>Общая статистика</b>\n\n"
        f"👤 Пользователей: {stats['total_users']}\n"
        f"📋 Всего заданий: {stats['total_tasks']}\n"
        f"✅ Выполнено: {stats['completed_tasks']}\n"
        f"💰 Выплачено: {stats['total_payout']} ₽\n"
        f"⏳ Ожидают ссылку: {stats['pending_links']}\n"
        f"⚡ В работе: {stats['active_tasks']}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ==================== ОБРАБОТЧИКИ ДЕЙСТВИЙ ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Сохраняем информацию о чате для последующего использования
    context.user_data['chat_id'] = update.effective_chat.id
    context.user_data['message_id'] = query.message.message_id

    if data == "back_main":
        # Создаем новый Update объект для start
        await start(update, context)
        return
    elif data == "profile":
        await profile(update, context)
        return
    elif data == "help":
        await help_command(update, context)
        return
    elif data == "tasks":
        await tasks(update, context)
        return
    elif data == "all_tasks":
        await show_tasks(update, context, category_id=None)
        return
    elif data.startswith("cat_"):
        cat_id = int(data.split('_')[1])
        await show_tasks(update, context, category_id=cat_id)
        return
    elif data.startswith("take_"):
        task_id = data.split('_')[1]
        await take_task(update, context, task_id)
        return
    elif data == "admin_list_categories":
        await list_categories(update, context)
        return
    elif data == "admin_del_category":
        await delete_category_prompt(update, context)
        return
    elif data.startswith("delcat_"):
        cat_id = int(data.split('_')[1])
        await delete_category(update, context, cat_id)
        return
    elif data == "admin_back":
        await start(update, context)
        return

async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: Optional[int]):
    query = update.callback_query
    tasks_list = await TaskManager.get_available(category_id)
    
    if not tasks_list:
        await query.edit_message_text(
            "📭 В этой категории пока нет доступных заданий."
        )
        return
    
    # Отправляем каждое задание отдельным сообщением
    for task in tasks_list:
        text = (
            f"<b>{task['title']}</b>\n"
            f"{task['description']}\n\n"
            f"💰 Награда: {task['reward']} ₽\n"
            f"🎯 Цель: {task['target']}\n"
            f"📌 Требования: {task['requirements'] or 'нет'}"
        )
        keyboard = [[InlineKeyboardButton("✅ Взять задание", callback_data=f"take_{task['task_id']}")]]
        await query.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # Удаляем сообщение с выбором категории
    await query.message.delete()

async def take_task(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str):
    query = update.callback_query
    user_id = update.effective_user.id
    
    user = await UserManager.get(user_id)
    if not user:
        await query.edit_message_text(
            "❌ Сначала зарегистрируйтесь через /start"
        )
        return
    
    task = await TaskManager.get_by_id(task_id)
    if not task or not task['available']:
        await query.edit_message_text(
            "❌ Это задание уже недоступно."
        )
        return

    success = await TaskManager.assign(task_id, user_id)
    if not success:
        await query.edit_message_text(
            "❌ Не удалось взять задание. Попробуйте позже."
        )
        return

    tracking_link = await TrackingManager.generate_link(user_id, task_id)
    await PendingManager.save(
        task_id, user_id,
        user.get('username', ''),
        task['title'],
        tracking_link
    )

    # Отправка в группу админов
    group_chat = TASK_NOTIFICATION_GROUP
    admin_msg = (
        f"🆕 <b>Пользователь взял задание!</b>\n\n"
        f"👤 Пользователь: @{user.get('username', '')} (ID: {user_id})\n"
        f"📋 Задание: {task['title']}\n"
        f"🆔 ID задания: <code>{task_id}</code>\n"
        f"🔗 Отслеживающая ссылка: {tracking_link}\n\n"
        f"Для выдачи рабочей ссылки используйте:\n"
        f"<code>/give_link {task_id} ссылка</code>"
    )
    try:
        await context.bot.send_message(group_chat, admin_msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение в группу {group_chat}: {e}")

    await query.edit_message_text(
        f"✅ Вы взяли задание «{task['title']}»!\n\n"
        f"🔗 Ваша персональная ссылка для приглашений:\n<code>{tracking_link}</code>\n\n"
        f"⏳ Ожидайте, пока администратор выдаст рабочую ссылку. Обычно это занимает несколько минут.\n"
        f"Вы получите уведомление, когда ссылка будет готова.",
        parse_mode=ParseMode.HTML
    )

# ==================== АДМИН: УПРАВЛЕНИЕ КАТЕГОРИЯМИ ====================
async def list_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cats = await CategoryManager.get_all()
    if not cats:
        await query.edit_message_text("📭 Категории отсутствуют.")
        return
    text = "📁 <b>Все категории:</b>\n"
    for cat in cats:
        indent = "  " * (2 if cat['parent_id'] else 0)
        text += f"{indent}• {cat['name']} (ID: {cat['id']})\n"
    await query.edit_message_text(text, parse_mode=ParseMode.HTML)

async def delete_category_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cats = await CategoryManager.get_all()
    if not cats:
        await query.edit_message_text("📭 Нет категорий для удаления.")
        return
    keyboard = []
    for cat in cats:
        keyboard.append([InlineKeyboardButton(cat['name'], callback_data=f"delcat_{cat['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Отмена", callback_data="admin_back")])
    await query.edit_message_text(
        "Выберите категорию для удаления:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_category(update: Update, context: ContextTypes.DEFAULT_TYPE, cat_id: int):
    query = update.callback_query
    success = await CategoryManager.delete(cat_id)
    if success:
        await query.edit_message_text(f"✅ Категория удалена.")
    else:
        await query.edit_message_text("❌ Нельзя удалить категорию, у которой есть подкатегории.")

# ==================== ОТМЕНА ====================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Операция отменена.")
    context.user_data.clear()
    return ConversationHandler.END

# ==================== ОШИБКИ ====================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")

# ==================== ЗАПУСК ====================
async def post_init(application: Application):
    await Database.init_pool()
    logger.info("Бот запущен и готов к работе!")

async def shutdown(application: Application):
    await Database.close_pool()
    logger.info("Пул БД закрыт.")

def main():
    if not TOKEN:
        logger.error("BOT_TOKEN не задан!")
        return

    application = Application.builder().token(TOKEN).post_init(post_init).build()
    application.post_shutdown = shutdown

    # ---- Обычные команды ----
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("tasks", tasks))
    application.add_handler(CommandHandler("my_tasks", my_tasks))

    # ---- Админ команды ----
    application.add_handler(CommandHandler("add_admin", add_admin))
    application.add_handler(CommandHandler("remove_admin", remove_admin))
    application.add_handler(CommandHandler("admins", list_admins))
    application.add_handler(CommandHandler("categories", categories))
    application.add_handler(CommandHandler("give_link", give_link_command))
    application.add_handler(CommandHandler("pending", pending_list))
    application.add_handler(CommandHandler("stats", stats_command))

    # ---- Создание задания (Conversation) ----
    conv_create_task = ConversationHandler(
        entry_points=[CommandHandler("create_task", create_task_start)],
        states={
            TASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_title)],
            TASK_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_desc)],
            TASK_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_type)],
            TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_target)],
            REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_reward)],
            REQUIREMENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_requirements)],
            TASK_CATEGORY: [CallbackQueryHandler(create_task_category, pattern="^task_cat_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conv_create_task)

    # ---- Создание категории (Conversation) ----
    conv_add_category = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_category_start, pattern="^admin_add_category$")],
        states={
            CATEGORY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_category_name)],
            CATEGORY_PARENT: [CallbackQueryHandler(add_category_parent, pattern="^(cat_parent_none|cat_parent_\\d+|cat_parent_select|cancel_category)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conv_add_category)

    # ---- Callback обработчик ----
    # Важно: добавляем его ПОСЛЕ ConversationHandler'ов
    application.add_handler(CallbackQueryHandler(button_handler))

    # ---- Ошибки ----
    application.add_error_handler(error_handler)

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()