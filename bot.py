# bot.py
import os
import logging
import asyncio
import urllib.parse
from typing import Optional, List, Dict, Any
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from telegram.constants import ParseMode
from dotenv import load_dotenv
from telegram.error import BadRequest
load_dotenv()

from database import (
    Database, UserManager, AdminManager, CategoryManager,
    TaskManager, TrackingManager, PendingManager, StatsManager
)

WELCOME_VIDEO_PATH = os.path.join(os.path.dirname(__file__), "video.mp4")

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
TASK_TITLE, TASK_DESC, TASK_TYPE, TARGET, REWARD, REQUIREMENTS, TASK_CATEGORY = range(7, 14)
ADD_ADMIN_ID, ADD_ADMIN_USERNAME = range(14, 16)
BROADCAST_TEXT = 50  # новое состояние для рассылки

# ==================== ОБЩИЕ КОМАНДЫ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await UserManager.get_or_create(user.id, user.username or "", user.first_name)

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
    "🚀 Зарабатывай на белом трафике!\n\n"
    "🔥 Наш бот — это твой личный кабинет с ежедневными заданиями по привлечению трафика в Telegram-каналы 📲 Никакой серой зоны, ботов и накруток — только живые люди и честные деньги 💎\n\n"
    "Как это работает? 👇\n"
    "✅ Выбрал задание\n"
    "✅ Привел целевой трафик\n"
    "✅ Получил оплату 💰\n\n"
    "Всё прозрачно и автоматизировано: бот фиксирует результат и начисляет средства на твой баланс 📊 Ты сам решаешь, сколько зарабатывать — хоть на кофе ☕, хоть на новый ноутбук 💻\n\n"
    "Почему мы? ⚡️\n"
    "✨ Стабильные выплаты\n"
    "✨ Понятные условия\n"
    "✨ Поддержка 24/7\n"
    "✨ Реальные перспективы для профи\n\n"
    "Владельцы каналов готовы платить за качество, а мы даем тебе этот поток заказов 🎯\n\n"
    "Готов лить и зарабатывать? 🚀 Заходи, выбирай задания и стартуй уже сегодня! 👉\n\n"
    "Канал | переходник в котором есть мануал, сообщество и поддержка кураторов  по работе: https://t.me/Trafficork"
)

    keyboard = [
        [InlineKeyboardButton("📋 Доступные задания", callback_data="user_tasks")],
        [InlineKeyboardButton("👤 Профиль", callback_data="user_profile"),
         InlineKeyboardButton("❓ Помощь", callback_data="user_help")]
    ]

    is_admin = await AdminManager.is_admin(user.id)
    if is_admin:
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])

    try:
        with open(WELCOME_VIDEO_PATH, 'rb') as video_file:
            if update.message:
                await update.message.reply_animation(
                    animation=InputFile(video_file, filename='video.mp4'),
                    caption=welcome_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.HTML
                )
            else:
                await update.callback_query.message.reply_animation(
                    animation=InputFile(video_file, filename='video.mp4'),
                    caption=welcome_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.HTML
                )
    except Exception as e:
        logger.error(f"Ошибка при отправке видео: {e}")
        if update.message:
            await update.message.reply_text(
                welcome_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
        else:
            await update.callback_query.message.reply_text(
                welcome_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
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
        "Если есть проблема или баг то по всем вопросам: @V2SHOP123"
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
        f"Дата регистрации: {joined_date}\n"
        f"Администратор: {'✅ Да' if user.get('is_admin') else '❌ Нет'}\n\n"
        f"📊 <b>Статистика</b>\n"
        f"✅ Выполнено заданий: {stats['completed_count']}\n"
        f"⚡ Активных заданий: {stats['active_count']}\n"
    )
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    else:
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.HTML)

async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    chat_id = update.effective_chat.id
    tasks_list = await TaskManager.get_user_tasks(user_id)
    if not tasks_list:
        await context.bot.send_message(chat_id, "📭 У вас пока нет взятых заданий.")
        return

    for task in tasks_list:
        status_emoji = "✅" if task.get('completed', False) else "⏳"
        text = (
            f"{status_emoji} <b>{task['title']}</b>\n"
            f"ID: <code>{task['task_id']}</code>\n"
            f"Статус: {'Выполнено' if task.get('completed', False) else 'В работе'}\n"
        )
        if task.get('earned'):
            text += f"Заработано: {task['earned']} ₽\n"
        
        keyboard = []
        if not task.get('completed', False):
            support_msg = f"я сделал задание: {task['title']} (ID: {task['task_id']})"
            encoded_msg = urllib.parse.quote(support_msg)
            url = f"https://t.me/V2SHOP123?text={encoded_msg}"
            keyboard.append([InlineKeyboardButton("✅ Сделал задание", url=url)])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

# ==================== АДМИН-ПАНЕЛЬ ====================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"Попытка открыть админ-панель пользователем {user_id}")
    
    is_admin = await AdminManager.is_admin(user_id)
    logger.info(f"Результат проверки is_admin: {is_admin}")
    
    if not is_admin:
        if update.callback_query:
            await update.callback_query.answer("⛔ У вас нет прав администратора!", show_alert=True)
        return

    query = update.callback_query
    await query.answer()

    is_main = await AdminManager.is_main_admin(user_id)
    logger.info(f"Результат проверки is_main_admin: {is_main}")

    keyboard = [
        [InlineKeyboardButton("📋 Управление заданиями", callback_data="admin_tasks_menu")],
        [InlineKeyboardButton("📁 Управление категориями", callback_data="admin_categories_menu")],
        [InlineKeyboardButton("⏳ Ожидают ссылку", callback_data="admin_pending")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
    ]

    if is_main:
        keyboard.append([InlineKeyboardButton("👥 Управление админами", callback_data="admin_manage_admins")])

    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="back_main")])

    text = "👑 <b>АДМИН-ПАНЕЛЬ</b>\n\nВыберите действие:"

    await query.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def check_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса администратора (только для отладки)"""
    user_id = update.effective_user.id
    
    is_admin = await AdminManager.is_admin(user_id)
    is_main = await AdminManager.is_main_admin(user_id)
    
    async with Database._pool.acquire() as conn:
        user = await conn.fetchrow('SELECT user_id, is_admin FROM users WHERE user_id = $1', user_id)
        user_exists = user is not None
        db_is_admin = user['is_admin'] if user else None
    
    text = (
        f"🔍 <b>Проверка статуса администратора</b>\n\n"
        f"👤 <b>Ваш ID:</b> <code>{user_id}</code>\n"
        f"👑 <b>Главный админ ID:</b> <code>{AdminManager.MAIN_ADMIN_ID}</code>\n"
        f"📊 <b>Совпадает с главным:</b> {'✅ Да' if is_main else '❌ Нет'}\n\n"
        f"📋 <b>Результаты проверки:</b>\n"
        f"• AdminManager.is_admin: {'✅ Да' if is_admin else '❌ Нет'}\n"
        f"• Пользователь в БД: {'✅ Да' if user_exists else '❌ Нет'}\n"
        f"• is_admin в БД: {db_is_admin if db_is_admin is not None else 'None'}\n\n"
        f"<b>Если вы должны быть администратором, но проверка не проходит:</b>\n"
        f"1. Проверьте правильность ID в .env файле\n"
        f"2. Убедитесь, что вы зарегистрированы (/start)\n"
        f"3. Попробуйте добавить себя через /add_admin {user_id}"
    )
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ==================== УПРАВЛЕНИЕ АДМИНАМИ ====================
async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_main_admin(update.effective_user.id):
        await update.callback_query.answer("⛔ Только главный админ может управлять админами!", show_alert=True)
        return

    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("➕ Добавить администратора", callback_data="admin_add_admin_start")],
        [InlineKeyboardButton("🗑 Удалить администратора", callback_data="admin_remove_admin_list")],
        [InlineKeyboardButton("📋 Список администраторов", callback_data="admin_list_admins")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]

    await query.edit_message_text(
        "👥 <b>Управление администраторами</b>\n\n"
        "Здесь вы можете добавлять или удалять администраторов бота.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_main_admin(update.effective_user.id):
        await update.callback_query.answer("⛔ Только главный админ может добавлять админов!", show_alert=True)
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "👤 <b>Добавление администратора</b>\n\n"
        "Введите ID пользователя Telegram:\n"
        "(например: 123456789)\n\n"
        "Или отправьте /cancel для отмены.",
        parse_mode=ParseMode.HTML
    )
    return ADD_ADMIN_ID

async def add_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Операция отменена.")
        context.user_data.clear()
        return ConversationHandler.END

    try:
        user_id = int(update.message.text)
        context.user_data['new_admin_id'] = user_id

        await update.message.reply_text(
            f"✅ ID {user_id} принят.\n\n"
            f"Введите username пользователя (можно отправить '-' если нет):"
        )
        return ADD_ADMIN_USERNAME
    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите корректный числовой ID:")
        return ADD_ADMIN_ID

async def add_admin_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Операция отменена.")
        context.user_data.clear()
        return ConversationHandler.END

    username = update.message.text
    if username == '-':
        username = ""

    user_id = context.user_data.get('new_admin_id')

    try:
        await AdminManager.add_admin(user_id, username, update.effective_user.id)
        await update.message.reply_text(
            f"✅ Пользователь {user_id} успешно назначен администратором!"
        )

        try:
            await context.bot.send_message(
                user_id,
                f"🎉 Поздравляем! Вы назначены администратором бота.\n"
                f"Теперь вам доступна админ-панель.\n"
                f"Напишите /start и нажмите кнопку 'Админ-панель' для управления."
            )
        except:
            pass

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при добавлении администратора: {e}")

    context.user_data.clear()
    return ConversationHandler.END

async def remove_admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_main_admin(update.effective_user.id):
        await update.callback_query.answer("⛔ Только главный админ может удалять админов!", show_alert=True)
        return

    query = update.callback_query
    await query.answer()

    admins = await AdminManager.get_all_admins()
    keyboard = []

    for admin in admins:
        if admin['user_id'] != MAIN_ADMIN_ID:
            username = f" @{admin['username']}" if admin['username'] else ""
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ {admin['user_id']}{username}",
                    callback_data=f"remove_admin_{admin['user_id']}"
                )
            ])

    if not keyboard:
        keyboard.append([InlineKeyboardButton("📭 Нет администраторов для удаления", callback_data="admin_manage_admins")])
    else:
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_manage_admins")])

    await query.edit_message_text(
        "🗑 <b>Удаление администратора</b>\n\n"
        "Выберите администратора для удаления:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def remove_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_main_admin(update.effective_user.id):
        await update.callback_query.answer("⛔ Только главный админ может удалять админов!", show_alert=True)
        return

    query = update.callback_query
    await query.answer()

    user_id = int(query.data.split('_')[2])

    success = await AdminManager.remove_admin(user_id)
    if success:
        await query.edit_message_text(
            f"✅ Администратор {user_id} успешно удален.",
            parse_mode=ParseMode.HTML
        )

        try:
            await context.bot.send_message(
                user_id,
                f"⚠️ Ваши права администратора были отозваны."
            )
        except:
            pass
    else:
        await query.edit_message_text(
            f"❌ Не удалось удалить администратора.",
            parse_mode=ParseMode.HTML
        )

async def list_admins_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    admins = await AdminManager.get_all_admins()
    text = "👑 <b>Список администраторов</b>\n\n"

    for admin in admins:
        main = " (👑 Главный)" if admin['user_id'] == MAIN_ADMIN_ID else ""
        username = f"@{admin['username']}" if admin['username'] else "нет username"
        text += f"• <b>{admin['user_id']}</b> - {username}{main}\n"

    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_manage_admins")]]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== УПРАВЛЕНИЕ КАТЕГОРИЯМИ ====================
async def categories_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_admin(update.effective_user.id):
        if update.callback_query:
            await update.callback_query.answer("⛔ У вас нет прав администратора!", show_alert=True)
        return

    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("➕ Создать категорию", callback_data="admin_add_category")],
        [InlineKeyboardButton("📋 Список категорий", callback_data="admin_list_categories")],
        [InlineKeyboardButton("🗑 Удалить категорию", callback_data="admin_del_category")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]

    await query.edit_message_text(
        "📁 <b>Управление категориями</b>\n\n"
        "Категории помогают структурировать задания.\n"
        "Можно создавать корневые категории и подкатегории.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def add_category_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 Введите название новой категории:\n\n"
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
        await query.edit_message_text(f"✅ Категория «{name}» успешно создана!")
        context.user_data.clear()
        return ConversationHandler.END

    elif query.data == "cat_parent_select":
        cats = await CategoryManager.get_children(None)
        if not cats:
            await query.edit_message_text(
                "❌ Нет корневых категорий. Сначала создайте корневую категорию.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="admin_categories_menu")
                ]])
            )
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
        await query.edit_message_text(f"✅ Подкатегория «{name}» успешно создана!")
        context.user_data.clear()
        return ConversationHandler.END

    elif query.data == "cancel_category":
        await query.edit_message_text("❌ Создание категории отменено.")
        context.user_data.clear()
        return ConversationHandler.END

    return ConversationHandler.END

async def list_categories_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cats = await CategoryManager.get_all()

    if not cats:
        await query.edit_message_text(
            "📭 Категории отсутствуют.\n\nСоздайте первую категорию через 'Создать категорию'.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="admin_categories_menu")
            ]])
        )
        return

    text = "📁 <b>Все категории:</b>\n\n"
    for cat in cats:
        indent = "  " * (2 if cat['parent_id'] else 0)
        parent_info = ""
        if cat['parent_id']:
            parent = await CategoryManager.get_by_id(cat['parent_id'])
            if parent:
                parent_info = f" (в: {parent['name']})"
        text += f"{indent}• <b>{cat['name']}</b> (ID: {cat['id']}){parent_info}\n"

    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_categories_menu")]]
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_category_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cats = await CategoryManager.get_all()

    if not cats:
        await query.edit_message_text(
            "📭 Нет категорий для удаления.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="admin_categories_menu")
            ]])
        )
        return

    keyboard = []
    for cat in cats:
        keyboard.append([InlineKeyboardButton(f"🗑 {cat['name']}", callback_data=f"delcat_{cat['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Отмена", callback_data="admin_categories_menu")])

    await query.edit_message_text(
        "🗑 <b>Удаление категории</b>\n\n"
        "Выберите категорию для удаления:\n"
        "<i>Внимание! Категории с подкатегориями нельзя удалить.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    cat_id = int(query.data.split('_')[1])
    success = await CategoryManager.delete(cat_id)

    if success:
        await query.edit_message_text(
            "✅ Категория успешно удалена.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 К категориям", callback_data="admin_categories_menu")
            ]])
        )
    else:
        await query.edit_message_text(
            "❌ Нельзя удалить категорию, у которой есть подкатегории.\n\n"
            "Сначала удалите все подкатегории.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 К категориям", callback_data="admin_categories_menu")
            ]])
        )

# ==================== УПРАВЛЕНИЕ ЗАДАНИЯМИ ====================
async def tasks_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_admin(update.effective_user.id):
        if update.callback_query:
            await update.callback_query.answer("⛔ У вас нет прав администратора!", show_alert=True)
        return

    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("➕ Создать задание", callback_data="admin_create_task")],
        [InlineKeyboardButton("⏳ Ожидают ссылку", callback_data="admin_pending")],
        [InlineKeyboardButton("📋 Все задания", callback_data="admin_all_tasks")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]

    await query.edit_message_text(
        "📋 <b>Управление заданиями</b>\n\n"
        "Создавайте новые задания и управляйте существующими.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def create_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not await AdminManager.is_admin(user_id):
        if update.message:
            await update.message.reply_text("⛔ У вас нет прав администратора.")
        else:
            await update.callback_query.answer("⛔ У вас нет прав администратора!", show_alert=True)
        return ConversationHandler.END

    context.user_data.clear()

    text = (
        "📝 <b>Создание нового задания</b>\n\n"
        "Введите <b>название</b> задания:\n\n"
        "(или отправьте /cancel для отмены)"
    )

    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    else:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)

    return TASK_TITLE

async def create_task_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Создание задания отменено.")
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data['task_title'] = update.message.text

    await update.message.reply_text(
        "📝 Введите <b>описание</b> задания:\n\n"
        "(или отправьте /cancel для отмены)",
        parse_mode=ParseMode.HTML
    )
    return TASK_DESC

async def create_task_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Создание задания отменено.")
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data['task_desc'] = update.message.text

    keyboard = [
        [InlineKeyboardButton("📢 Канал", callback_data="task_type_channel")],
        [InlineKeyboardButton("📎 Пост", callback_data="task_type_post")],
        [InlineKeyboardButton("🔗 Ссылка", callback_data="task_type_link")]
    ]

    await update.message.reply_text(
        "🎯 <b>Выберите тип цели задания:</b>\n\n"
        "• <b>Канал</b> - для подписки на канал\n"
        "• <b>Пост</b> - для репоста/комментария\n"
        "• <b>Ссылка</b> - для перехода по ссылке\n\n"
        "Нажмите на кнопку ниже:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TASK_TYPE

async def create_task_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    task_type = query.data.split('_')[2]
    context.user_data['task_type'] = task_type

    type_names = {
        'channel': '📢 Канал',
        'post': '📎 Пост',
        'link': '🔗 Ссылка'
    }

    await query.edit_message_text(
        f"✅ Выбран тип: <b>{type_names[task_type]}</b>\n\n"
        f"🔗 Введите <b>цель</b> задания:\n\n"
        f"• <b>Для канала:</b> @username или ссылка на канал\n"
        f"• <b>Для поста:</b> ссылка на пост\n"
        f"• <b>Для ссылки:</b> URL\n\n"
        f"<i>Примеры:</i>\n"
        f"• @example_channel\n"
        f"• https://t.me/example/123\n"
        f"• https://example.com\n\n"
        f"(или отправьте /cancel для отмены)",
        parse_mode=ParseMode.HTML
    )
    return TARGET

async def create_task_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Создание задания отменено.")
        context.user_data.clear()
        return ConversationHandler.END

    if 'task_type' not in context.user_data:
        await update.message.reply_text(
            "❌ Ошибка: не выбран тип задания. Начните создание заново.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("➕ Создать задание", callback_data="admin_create_task")
            ]])
        )
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data['target'] = update.message.text

    await update.message.reply_text(
        "💰 Введите <b>награду</b> за выполнение (в рублях):\n\n"
        "Например: 100 или 150.50\n\n"
        "(или отправьте /cancel для отмены)",
        parse_mode=ParseMode.HTML
    )
    return REWARD

async def create_task_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Создание задания отменено.")
        context.user_data.clear()
        return ConversationHandler.END

    try:
        reward = float(update.message.text)
        if reward <= 0:
            await update.message.reply_text("❌ Награда должна быть положительным числом:")
            return REWARD
        context.user_data['reward'] = reward
    except ValueError:
        await update.message.reply_text("❌ Введите число (например, 100.50):")
        return REWARD

    await update.message.reply_text(
        "📌 Введите <b>требования</b> к выполнению:\n\n"
        "Например: подписаться на канал, сделать репост и т.д.\n"
        "Или отправьте 'нет', если требований нет\n\n"
        "(или отправьте /cancel для отмены)",
        parse_mode=ParseMode.HTML
    )
    return REQUIREMENTS

async def create_task_requirements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.text == '/cancel':
            await update.message.reply_text("❌ Создание задания отменено.")
            context.user_data.clear()
            return ConversationHandler.END

        req = update.message.text
        context.user_data['requirements'] = req if req.lower() != 'нет' else ""

        logger.info(f"Требования сохранены: {context.user_data['requirements']}")
        logger.info(f"user_data после требований: {context.user_data}")

        required_fields = ['task_title', 'task_desc', 'task_type', 'target', 'reward']
        missing = [f for f in required_fields if f not in context.user_data]
        if missing:
            logger.error(f"Отсутствуют поля: {missing}")
            await update.message.reply_text(
                f"❌ Ошибка: отсутствуют данные ({', '.join(missing)}). Начните создание заново."
            )
            context.user_data.clear()
            return ConversationHandler.END

        cats = await CategoryManager.get_all()
        logger.info(f"Получено категорий: {len(cats)}")

        if not cats:
            context.user_data['category_id'] = None
            await create_task_finish(update, context)
            context.user_data.clear()
            return ConversationHandler.END

        keyboard = []
        for cat in cats:
            prefix = "  " * (1 if cat['parent_id'] else 0)
            button_text = f"{prefix}{cat['name']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"task_cat_{cat['id']}")])

        keyboard.append([InlineKeyboardButton("⏭ Без категории", callback_data="task_cat_none")])
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="task_cat_cancel")])

        await update.message.reply_text(
            "📁 Выберите <b>категорию</b> задания:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return TASK_CATEGORY

    except Exception as e:
        logger.error(f"❌ Ошибка в create_task_requirements: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await update.message.reply_text(
            f"❌ Произошла ошибка: {str(e)[:200]}\nПопробуйте снова."
        )
        context.user_data.clear()
        return ConversationHandler.END

async def create_task_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()

        logger.info(f"Выбрана категория: {query.data}")
        logger.info(f"user_data перед выбором категории: {context.user_data}")

        if query.data == "task_cat_cancel":
            await query.edit_message_text("❌ Создание задания отменено.")
            context.user_data.clear()
            return ConversationHandler.END

        if query.data == "task_cat_none":
            context.user_data['category_id'] = None
            logger.info("Категория: None")
        else:
            cat_id = int(query.data.split('_')[-1])
            context.user_data['category_id'] = cat_id
            logger.info(f"Категория ID: {cat_id}")

        await create_task_finish(query, context)
        context.user_data.clear()
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"❌ Ошибка в create_task_category_callback: {e}")
        import traceback
        logger.error(traceback.format_exc())
        await query.edit_message_text(
            f"❌ Ошибка: {str(e)[:200]}"
        )
        context.user_data.clear()
        return ConversationHandler.END

async def create_task_finish(update, context):
    try:
        logger.info(f"Начало create_task_finish с user_data: {context.user_data}")

        title = context.user_data.get('task_title')
        desc = context.user_data.get('task_desc')
        task_type = context.user_data.get('task_type')
        target = context.user_data.get('target')
        reward = context.user_data.get('reward')
        req = context.user_data.get('requirements', '')
        cat_id = context.user_data.get('category_id')

        if not all([title, desc, task_type, target, reward]):
            missing = []
            if not title: missing.append("название")
            if not desc: missing.append("описание")
            if not task_type: missing.append("тип")
            if not target: missing.append("цель")
            if not reward: missing.append("награда")
            error_msg = f"❌ Отсутствуют: {', '.join(missing)}"
            logger.error(error_msg)
            if isinstance(update, Update):
                await update.message.reply_text(error_msg)
            else:
                await update.edit_message_text(error_msg)
            return

        if isinstance(update, Update):
            created_by = update.effective_user.id
        else:
            created_by = update.from_user.id
        
        task_id = await TaskManager.create(
                    title, desc, task_type, target, float(reward),
                    created_by, cat_id, req
                )

        logger.info(f"✅ Задание {task_id} создано")

        type_names = {
            'channel': '📢 Канал',
            'post': '📎 Пост',
            'link': '🔗 Ссылка'
        }

        text = (
            f"✅ <b>Задание успешно создано!</b>\n\n"
            f"📋 <b>Название:</b> {title}\n"
            f"📝 <b>Описание:</b> {desc[:100]}{'...' if len(desc) > 100 else ''}\n"
            f"🎯 <b>Тип:</b> {type_names.get(task_type, task_type)}\n"
            f"🔗 <b>Цель:</b> {target}\n"
            f"💰 <b>Награда:</b> {reward} ₽\n"
            f"📌 <b>Требования:</b> {req or 'нет'}\n"
            f"🆔 <b>ID задания:</b> <code>{task_id}</code>\n\n"
            f"Задание доступно для пользователей."
        )

        if isinstance(update, Update):
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        else:
            await update.edit_message_text(text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"❌ Ошибка в create_task_finish: {e}")
        import traceback
        logger.error(traceback.format_exc())
        error_text = f"❌ Ошибка при создании задания: {str(e)[:200]}"
        if isinstance(update, Update):
            await update.message.reply_text(error_text)
        else:
            await update.edit_message_text(error_text)

# ==================== ВЫДАЧА ССЫЛОК ====================
async def give_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ У вас нет прав администратора.")
        return

    try:
        task_id = context.args[0]
        work_link = ' '.join(context.args[1:])
    except IndexError:
        await update.message.reply_text(
            "❌ Использование: /give_link <task_id> <ссылка>\n\n"
            "Пример: /give_link abc12345 https://t.me/example"
        )
        return

    pending = await PendingManager.get(task_id)
    if not pending:
        await update.message.reply_text(
            f"❌ Задание {task_id} не найдено в ожидающих или уже обработано."
        )
        return

    await TaskManager.set_work_link(task_id, work_link)
    await PendingManager.mark_processed(task_id)

    try:
        await context.bot.send_message(
            pending['user_id'],
            f"🔗 <b>Вам выдана рабочая ссылка!</b>\n\n"
            f"📋 <b>Задание:</b> {pending['task_title']}\n"
            f"🔗 <b>Рабочая ссылка:</b>\n{work_link}\n\n"
            f"После выполнения задания впишите команду /my_tasks чтобы подтвердить выполнение задания\n\n"
            f"Удачи в работе! 🚀",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение пользователю {pending['user_id']}: {e}")

    await update.message.reply_text(
        f"✅ Ссылка выдана для задания {task_id}.\n"
        f"Пользователь @{pending['username'] or pending['user_id']} получил уведомление."
    )

    try:
        await context.bot.send_message(
            TASK_NOTIFICATION_GROUP,
            f"✅ <b>Администратор выдал ссылку</b>\n\n"
            f"📋 <b>Задание:</b> {pending['task_title']}\n"
            f"🆔 <b>ID:</b> <code>{task_id}</code>\n"
            f"👤 <b>Пользователь:</b> @{pending['username'] or pending['user_id']}\n"
            f"👨‍💼 <b>Администратор:</b> @{update.effective_user.username or update.effective_user.id}",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Не удалось отправить подтверждение в группу: {e}")

async def pending_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_admin(update.effective_user.id):
        await update.callback_query.answer("⛔ У вас нет прав администратора!", show_alert=True)
        return

    query = update.callback_query
    await query.answer()

    pendings = await TaskManager.get_pending_links()

    if not pendings:
        await query.edit_message_text(
            "📭 Нет заданий, ожидающих ссылку.\n\n"
            "Все ссылки выданы вовремя!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")
            ]])
        )
        return

    text = "⏳ <b>Ожидают ссылку:</b>\n\n"
    for p in pendings[:5]:
        text += f"🔸 <b>{p['task_title']}</b>\n"
        text += f"🆔 ID: <code>{p['task_id']}</code>\n"
        text += f"👤 Пользователь: @{p['username'] or p['user_id']}\n"
        text += f"💰 Награда: {p['reward']} ₽\n"
        text += f"⏰ Ожидает: {p['message_sent'].strftime('%d.%m.%Y %H:%M')}\n"
        text += f"🔗 {p['tracking_link']}\n\n"

    if len(pendings) > 5:
        text += f"<i>... и еще {len(pendings) - 5} заданий</i>\n\n"

    text += "Используйте команду:\n"
    text += "<code>/give_link ID_задания ссылка</code>"

    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_pending")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_tasks_menu")]
    ]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_admin(update.effective_user.id):
        await update.callback_query.answer("⛔ У вас нет прав администратора!", show_alert=True)
        return

    query = update.callback_query
    await query.answer()

    stats = await StatsManager.get_global()

    text = (
        "📊 <b>ОБЩАЯ СТАТИСТИКА</b>\n\n"
        f"👤 <b>Пользователи:</b>\n"
        f"  • Всего: {stats['total_users']}\n\n"
        f"📋 <b>Задания:</b>\n"
        f"  • Всего создано: {stats['total_tasks']}\n"
        f"  • Выполнено: {stats['completed_tasks']}\n"
        f"  • В работе: {stats['active_tasks']}\n"
        f"  • Ожидают ссылку: {stats['pending_links']}\n\n"
        f"💰 <b>Финансы:</b>\n"
        f"  • Всего выплачено: {stats['total_payout']} ₽"
    )

    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
    ]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== ПОЛЬЗОВАТЕЛЬСКИЕ ДЕЙСТВИЯ ====================
async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: Optional[int]):
    query = update.callback_query
    logger.info(f"Запрос заданий для категории: {category_id}")

    tasks_list = await TaskManager.get_available(category_id)
    logger.info(f"Получено заданий из БД: {len(tasks_list)}")

    if not tasks_list:
        async with Database._pool.acquire() as conn:
            all_tasks = await conn.fetch('SELECT task_id, title, available, active, taken_by FROM tasks WHERE category_id = $1 OR ($1 IS NULL AND category_id IS NULL)', category_id)
            logger.info(f"Всего заданий в категории {category_id}: {len(all_tasks)}")
            for t in all_tasks:
                logger.info(f"Задание в БД: {dict(t)}")

        await query.edit_message_text(
            "📭 В этой категории пока нет доступных заданий.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 К категориям", callback_data="user_tasks")
            ]])
        )
        return

    await query.edit_message_text(
        f"📋 <b>Доступные задания:</b>\n\n"
        f"Найдено заданий: {len(tasks_list)}\n"
        f"Выберите задание из списка ниже:",
        parse_mode=ParseMode.HTML
    )

    for task in tasks_list:
        text = (
            f"<b>{task['title']}</b>\n"
            f"{task['description']}\n\n"
            f"💰 <b>Награда:</b> {task['reward']} ₽\n"
            f"🎯 <b>Цель:</b> {task['target']}\n"
            f"📌 <b>Требования:</b> {task['requirements'] or 'нет'}"
        )
        keyboard = [[InlineKeyboardButton("✅ Взять задание", callback_data=f"take_{task['task_id']}")]]
        await query.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def take_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    task_id = query.data.split('_')[1]
    user_id = update.effective_user.id

    user = await UserManager.get(user_id)
    if not user:
        await query.edit_message_text(
            "❌ Сначала зарегистрируйтесь через /start",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")
            ]])
        )
        return

    task = await TaskManager.get_by_id(task_id)
    if not task or not task['available']:
        await query.edit_message_text(
            "❌ Это задание уже недоступно.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Другие задания", callback_data="user_tasks")
            ]])
        )
        return

    success = await TaskManager.assign(task_id, user_id)
    if not success:
        await query.edit_message_text(
            "❌ Не удалось взять задание. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 Попробовать снова", callback_data=f"take_{task_id}")
            ]])
        )
        return

    tracking_link = await TrackingManager.generate_link(user_id, task_id)
    await PendingManager.save(
        task_id, user_id,
        user.get('username', ''),
        task['title'],
        tracking_link
    )

    group_chat = TASK_NOTIFICATION_GROUP
    admin_msg = (
        f"🆕 <b>НОВОЕ ЗАДАНИЕ ВЗЯТО!</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Пользователь:</b>\n"
        f"  • ID: <code>{user_id}</code>\n"
        f"  • Username: @{user.get('username', 'нет')}\n"
        f"  • Имя: {user.get('first_name', 'не указано')}\n\n"
        f"📋 <b>Задание:</b>\n"
        f"  • Название: {task['title']}\n"
        f"  • ID: <code>{task_id}</code>\n"
        f"  • Награда: {task['reward']} ₽\n\n"
        f"🔗 <b>Отслеживающая ссылка:</b>\n"
        f"{tracking_link}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚠️ <b>ТРЕБУЕТСЯ ВЫДАТЬ РАБОЧУЮ ССЫЛКУ!</b>\n\n"
        f"📌 <b>Команда для выдачи:</b>\n"
        f"<code>/give_link {task_id} ССЫЛКА_СЮДА</code>"
    )

    try:
        await context.bot.send_message(group_chat, admin_msg, parse_mode=ParseMode.HTML)
        logger.info(f"✅ Уведомление отправлено в группу {group_chat} для задания {task_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в группу {group_chat}: {e}")

    await query.edit_message_text(
        f"✅ <b>Вы взяли задание!</b>\n\n"
        f"📋 <b>Задание:</b> {task['title']}\n"
        f"💰 <b>Награда:</b> {task['reward']} ₽\n\n"
        
        f"⏳ <b>Что дальше?</b>\n"
        f"1️⃣ Ожидайте, администратор выдаст рабочую ссылку\n"
        f"2️⃣ Вы получите уведомление, когда ссылка будет готова\n"
        f"3️⃣ Используйте свою ссылку для приглашений\n\n"
        f"Обычно ожидание занимает несколько минут.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Мои задания", callback_data="user_my_tasks")
        ]])
    )

# ==================== ДИАГНОСТИЧЕСКАЯ КОМАНДА ====================
async def check_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только для администраторов!")
        return

    async with Database._pool.acquire() as conn:
        all_tasks = await conn.fetch('''
            SELECT task_id, title, available, active, taken_by, category_id, created_date 
            FROM tasks 
            ORDER BY created_date DESC 
            LIMIT 20
        ''')

        text = "📋 <b>Все последние задания:</b>\n\n"
        for task in all_tasks:
            status = "✅ Доступно" if task['available'] and task['active'] and not task['taken_by'] else "❌ Недоступно"
            text += f"• <b>{task['title']}</b>\n"
            text += f"  ID: {task['task_id']}\n"
            text += f"  Статус: {status}\n"
            text += f"  available: {task['available']}, active: {task['active']}, taken_by: {task['taken_by']}\n"
            text += f"  category: {task['category_id']}\n"
            text += f"  создано: {task['created_date'].strftime('%d.%m.%Y %H:%M')}\n\n"

        available = await TaskManager.get_available()
        text += f"\n<b>Доступных заданий сейчас:</b> {len(available)}\n"

        if available:
            text += "\n<b>Список доступных:</b>\n"
            for task in available:
                text += f"  • {task['title']} (ID: {task['task_id']})\n"

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ==================== КОМАНДЫ ДЛЯ ГЛАВНОГО АДМИНА ====================

async def users_count_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_main_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только главный админ может использовать эту команду.")
        return
    async with Database._pool.acquire() as conn:
        count = await conn.fetchval('SELECT COUNT(*) FROM users')
    await update.message.reply_text(f"👥 Всего пользователей в боте: {count}")

async def user_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_main_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только главный админ может использовать эту команду.")
        return
    try:
        user_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Использование: /user_info <user_id>")
        return

    user = await UserManager.get(user_id)
    if not user:
        await update.message.reply_text(f"❌ Пользователь с ID {user_id} не найден.")
        return

    stats = await UserManager.get_stats(user_id)
    joined_date = user['joined_date'].strftime('%d.%m.%Y %H:%M') if user['joined_date'] else 'неизвестно'
    text = (
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📝 Имя: {user['first_name']}\n"
        f"📧 Username: @{user['username'] if user['username'] else 'нет'}\n"
        f"📅 Дата регистрации: {joined_date}\n"
        f"👑 Администратор: {'✅ Да' if user.get('is_admin') else '❌ Нет'}\n\n"
        f"📊 <b>Статистика</b>\n"
        f"✅ Выполнено заданий: {stats['completed_count']}\n"
        f"⚡ Активных заданий: {stats['active_count']}\n"
        f"💰 Всего заработано: {stats['total_earned']} ₽\n"
        f"⭐ Рейтинг: {stats['rating']}"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def users_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_main_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только главный админ может использовать эту команду.")
        return
    async with Database._pool.acquire() as conn:
        rows = await conn.fetch('SELECT user_id, username, first_name FROM users ORDER BY joined_date DESC LIMIT 50')
    if not rows:
        await update.message.reply_text("📭 Нет пользователей.")
        return
    text = "📋 <b>Последние 50 пользователей:</b>\n\n"
    for row in rows:
        username = f"@{row['username']}" if row['username'] else "нет username"
        text += f"• <code>{row['user_id']}</code> — {row['first_name']} ({username})\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ==================== РАССЫЛКА ====================

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_main_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только главный админ может делать рассылку.")
        return ConversationHandler.END
    await update.message.reply_text(
        "📢 <b>Рассылка сообщения</b>\n\n"
        "Введите текст для рассылки всем пользователям (можно использовать HTML).\n"
        "Или отправьте /cancel для отмены.",
        parse_mode=ParseMode.HTML
    )
    return BROADCAST_TEXT

async def broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Рассылка отменена.")
        return ConversationHandler.END

    text = update.message.text
    await update.message.reply_text("⏳ Начинаю рассылку... Это может занять некоторое время.")

    user_ids = await UserManager.get_all_user_ids()
    success = 0
    failed = 0

    for uid in user_ids:
        try:
            await context.bot.send_message(uid, text, parse_mode=ParseMode.HTML)
            success += 1
            await asyncio.sleep(0.05)  # задержка, чтобы избежать flood
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение пользователю {uid}: {e}")
            failed += 1

    await update.message.reply_text(
        f"✅ Рассылка завершена!\n"
        f"📊 Успешно: {success}\n"
        f"❌ Не удалось: {failed}"
    )
    return ConversationHandler.END

# ==================== ГЛАВНЫЙ ОБРАБОТЧИК КНОПОК ====================
async def main_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    logger.info(f"Нажата кнопка: {data}")

    # Пользовательские кнопки
    if data == "back_main":
        await start(update, context)
    elif data == "user_profile":
        await profile(update, context)
    elif data == "user_help":
        await help_command(update, context)
    elif data == "user_tasks":
        await tasks(update, context)
    elif data == "user_my_tasks":
        await my_tasks(update, context)
    elif data == "all_tasks":
        await show_tasks(update, context, category_id=None)
    elif data.startswith("cat_"):
        cat_id = int(data.split('_')[1])
        await show_tasks(update, context, category_id=cat_id)
    elif data.startswith("take_"):
        await take_task_callback(update, context)
    # Админские кнопки
    elif data.startswith("admin_"):
        if not await AdminManager.is_admin(update.effective_user.id):
            await query.answer("⛔ У вас нет прав администратора!", show_alert=True)
            return
        
        if data == "admin_panel":
            await admin_panel(update, context)
        elif data == "admin_tasks_menu":
            await tasks_menu(update, context)
        elif data == "admin_categories_menu":
            await categories_menu(update, context)
        elif data == "admin_pending":
            await pending_list_callback(update, context)
        elif data == "admin_stats":
            await stats_callback(update, context)
        elif data == "admin_manage_admins":
            await manage_admins(update, context)
        elif data == "admin_list_admins":
            await list_admins_callback(update, context)
        elif data == "admin_remove_admin_list":
            await remove_admin_list(update, context)
        elif data.startswith("remove_admin_"):
            await remove_admin_callback(update, context)
        elif data == "admin_list_categories":
            await list_categories_callback(update, context)
        elif data == "admin_del_category":
            await delete_category_prompt(update, context)
        elif data.startswith("delcat_"):
            await delete_category_callback(update, context)
        elif data == "admin_create_task":
            await create_task_start(update, context)

# ==================== КОМАНДЫ ====================
async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_main_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только главный админ может добавлять администраторов.")
        return
    try:
        user_id = int(context.args[0])
        username = context.args[1] if len(context.args) > 1 else ""
        await AdminManager.add_admin(user_id, username, update.effective_user.id)
        await update.message.reply_text(f"✅ Пользователь {user_id} теперь администратор.")
        try:
            await context.bot.send_message(user_id, f"🎉 Поздравляем! Вы назначены администратором бота.")
        except:
            pass
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /add_admin <user_id> [username]")

async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_main_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только главный админ может удалять администраторов.")
        return
    try:
        user_id = int(context.args[0])
        success = await AdminManager.remove_admin(user_id)
        if success:
            await update.message.reply_text(f"✅ Администратор {user_id} удалён.")
            try:
                await context.bot.send_message(user_id, f"⚠️ Ваши права администратора были отозваны.")
            except:
                pass
        else:
            await update.message.reply_text("❌ Нельзя удалить главного админа.")
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /remove_admin <user_id>")

# ==================== ОТМЕНА ====================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Операция отменена.")
    context.user_data.clear()
    return ConversationHandler.END

# ==================== ОШИБКИ ====================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Игнорируем ошибку "Message is not modified" (повторное нажатие на одну кнопку)
    if isinstance(context.error, BadRequest) and "Message is not modified" in str(context.error):
        logger.info(f"Ignored 'Message is not modified' error: {context.error}")
        return

    logger.error(f"❌ Произошла ошибка: {context.error}")
    import traceback
    tb = traceback.format_exception(None, context.error, context.error.__traceback__)
    logger.error(f"Traceback: {''.join(tb)}")

    if update:
        if update.effective_user:
            logger.error(f"Пользователь: {update.effective_user.id} (@{update.effective_user.username})")
        if update.callback_query:
            logger.error(f"Callback data: {update.callback_query.data}")
        if update.message:
            logger.error(f"Message text: {update.message.text}")

    # Пользователю не отправляем сообщение об ошибке, чтобы не показывать "внутренняя ошибка"

# ==================== ЗАПУСК ====================
async def post_init(application: Application):
    await Database.init_pool()
    logger.info("✅ Бот запущен и готов к работе!")
    logger.info(f"👑 Главный администратор: {MAIN_ADMIN_ID}")
    logger.info(f"📢 Группа уведомлений: {TASK_NOTIFICATION_GROUP}")

async def shutdown(application: Application):
    await Database.close_pool()
    logger.info("✅ Пул БД закрыт.")

def main():
    if not TOKEN:
        logger.error("❌ BOT_TOKEN не задан!")
        return

    application = Application.builder().token(TOKEN).post_init(post_init).build()
    application.post_shutdown = shutdown

    # Пользовательские команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("tasks", tasks))
    application.add_handler(CommandHandler("my_tasks", my_tasks))

    # Админские команды
    application.add_handler(CommandHandler("add_admin", add_admin_command))
    application.add_handler(CommandHandler("remove_admin", remove_admin_command))
    application.add_handler(CommandHandler("give_link", give_link_command))
    application.add_handler(CommandHandler("check_tasks", check_tasks_command))

    # Команды для главного админа
    application.add_handler(CommandHandler("users_count", users_count_command))
    application.add_handler(CommandHandler("user_info", user_info_command))
    application.add_handler(CommandHandler("users_list", users_list_command))

    # Рассылка (только для главного админа)
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={
            BROADCAST_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="broadcast_conv"
    )
    application.add_handler(broadcast_conv)

    # ConversationHandler для добавления админа
    conv_add_admin = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_admin_start, pattern="^admin_add_admin_start$")],
        states={
            ADD_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_id)],
            ADD_ADMIN_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_username)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="add_admin_conv"
    )
    application.add_handler(conv_add_admin)

    # ConversationHandler для добавления категории
    conv_add_category = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_category_start, pattern="^admin_add_category$")],
        states={
            CATEGORY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_category_name)],
            CATEGORY_PARENT: [CallbackQueryHandler(add_category_parent, pattern="^(cat_parent_none|cat_parent_\\d+|cat_parent_select|cancel_category)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="add_category_conv"
    )
    application.add_handler(conv_add_category)

    # ConversationHandler для создания задания
    conv_create_task = ConversationHandler(
        entry_points=[
            CommandHandler("create_task", create_task_start),
            CallbackQueryHandler(create_task_start, pattern="^admin_create_task$")
        ],
        states={
            TASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_title)],
            TASK_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_desc)],
            TASK_TYPE: [CallbackQueryHandler(create_task_type_callback, pattern="^task_type_")],
            TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_target)],
            REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_reward)],
            REQUIREMENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, create_task_requirements)],
            TASK_CATEGORY: [CallbackQueryHandler(create_task_category_callback, pattern="^task_cat_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="create_task_conv"
    )
    application.add_handler(conv_create_task)

    # Главный обработчик кнопок
    application.add_handler(CallbackQueryHandler(main_button_handler))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)

    logger.info("🚀 Запуск бота...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()