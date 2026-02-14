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
    TaskManager, TrackingManager, PendingManager, StatsManager,
    CompletionManager, PaymentAwaitingManager
)

WELCOME_VIDEO_PATH = os.path.join(os.path.dirname(__file__), "video.mp4")

# ==================== НАСТРОЙКИ ====================
TOKEN = os.environ.get('BOT_TOKEN')
MAIN_ADMIN_ID = int(os.environ.get('MAIN_ADMIN_ID', '8358009538'))
GROUP_ID = int(os.environ.get('GROUP_ID', '-1003768763215'))  # ID группы с префиксом -100
BOT_USERNAME = os.environ.get('BOT_USERNAME', 'TrafficWorkeee_bot')

# ID тем (топиков) в группе - замените на свои значения
TOPIC_LINKS = 25      # для сообщений "ждут ссылку"
TOPIC_QUESTIONS = 27  # для вопросов пользователей
TOPIC_COMPLETED = 29  # для подтверждения выполненных заданий
REPORT_TOPIC = 45     # для отчётов по выплатам

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
CATEGORY_NAME, CATEGORY_PARENT = range(2)
TASK_TITLE, TASK_DESC, TASK_TYPE, TARGET, REWARD, REQUIREMENTS, TASK_CATEGORY = range(7, 14)
ADD_ADMIN_ID, ADD_ADMIN_USERNAME = range(14, 16)
BROADCAST_TEXT = 50
ASK_QUESTION = 51
REMOVE_TASK_USER_ID, REMOVE_TASK_TASK_ID = range(52, 54)
DELETE_TASK_ID = 55  # новое состояние для удаления задания

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
    "Канал | переходник в котором есть мануал, сообщество и поддержка кураторов по работе: https://t.me/Trafficork"
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
    )
    keyboard = [[InlineKeyboardButton("📝 Задать вопрос", callback_data="ask_question")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.callback_query.message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

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
    tasks_list = await TaskManager.get_user_tasks(user_id, status='active')
    if not tasks_list:
        await context.bot.send_message(chat_id, "📭 У вас пока нет взятых заданий.")
        return

    for task in tasks_list:
        status_emoji = "✅" if task.get('completed', False) else "⏳"
        reward = task.get('reward', 0)
        text = (
            f"{status_emoji} <b>{task['title']}</b>\n"
            f"ID: <code>{task['task_id']}</code>\n"
            f"💰 Награда: {reward} ₽\n"
            f"Статус: {'Выполнено' if task.get('completed', False) else 'В работе'}\n"
        )
        if task.get('earned'):
            text += f"Заработано: {task['earned']} ₽\n"
        
        keyboard = []
        if not task.get('completed', False):
            keyboard.append([InlineKeyboardButton("✅ Я выполнил задание", callback_data=f"complete_{task['task_id']}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

# ==================== ОБРАБОТЧИК ВОПРОСОВ ====================
async def ask_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало диалога вопроса"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📝 <b>Задать вопрос</b>\n\n"
        "Напишите ваш вопрос. Администратор ответит вам в личные сообщения.\n"
        "Отправьте /cancel для отмены.",
        parse_mode=ParseMode.HTML
    )
    return ASK_QUESTION

async def ask_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение текста вопроса и отправка в тему 'вопросы' с кнопкой ответа"""
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Вопрос отменён.")
        return ConversationHandler.END

    question = update.message.text
    user = update.effective_user
    user_id = user.id
    username = user.username or "нет username"
    first_name = user.first_name

    text = (
        f"❓ <b>Новый вопрос</b>\n\n"
        f"👤 <b>Пользователь:</b>\n"
        f"  • ID: <code>{user_id}</code>\n"
        f"  • Username: @{username}\n"
        f"  • Имя: {first_name}\n\n"
        f"📝 <b>Вопрос:</b>\n{question}"
    )

    keyboard = [[InlineKeyboardButton("📝 Ответить пользователю", callback_data=f"answer_user_{user_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        # Отправляем в тему вопросов
        sent_message = await context.bot.send_message(
            chat_id=GROUP_ID,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            message_thread_id=TOPIC_QUESTIONS
        )
        
        # Сохраняем ID сообщения и темы для возможного ответа
        context.user_data['last_question_message_id'] = sent_message.message_id
        context.user_data['last_question_thread_id'] = TOPIC_QUESTIONS
        
        await update.message.reply_text("✅ Ваш вопрос отправлен администратору. Ожидайте ответа в личные сообщения.")
        logger.info(f"✅ Вопрос от пользователя {user_id} отправлен в тему {TOPIC_QUESTIONS}, message_id: {sent_message.message_id}")
    except Exception as e:
        logger.error(f"Ошибка отправки вопроса в тему: {e}")
        await update.message.reply_text("❌ Не удалось отправить вопрос. Попробуйте позже.")

    return ConversationHandler.END

async def answer_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия на кнопку 'Ответить пользователю'"""
    query = update.callback_query
    await query.answer()
    
    if not await AdminManager.is_admin(update.effective_user.id):
        await query.edit_message_text("⛔ У вас нет прав администратора.")
        return ConversationHandler.END

    try:
        user_id = int(query.data.split('_')[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Неверный формат данных.")
        return ConversationHandler.END

    context.user_data['reply_to_user'] = user_id
    
    # Сохраняем информацию о том, откуда пришел запрос (ID сообщения и темы)
    context.user_data['reply_message_id'] = query.message.message_id
    context.user_data['reply_thread_id'] = query.message.message_thread_id
    
    await query.edit_message_text(
        f"📝 <b>Ответ пользователю {user_id}</b>\n\n"
        f"Напишите ваш ответ. Он будет отправлен пользователю в личные сообщения.\n"
        f"Отправьте /cancel для отмены.",
        parse_mode=ParseMode.HTML
    )
    
    return ASK_QUESTION

async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ответа администратора пользователю"""
    if 'reply_to_user' not in context.user_data:
        return ConversationHandler.END

    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Ответ отменён.")
        context.user_data.clear()
        return ConversationHandler.END

    user_id = context.user_data['reply_to_user']
    reply_text = update.message.text
    admin = update.effective_user

    try:
        # Отправляем ответ пользователю
        await context.bot.send_message(
            user_id,
            f"📝 <b>Ответ от администратора</b>\n\n{reply_text}",
            parse_mode=ParseMode.HTML
        )
        
        await update.message.reply_text(
            f"✅ Ответ отправлен пользователю {user_id}."
        )
        
        # Отправляем подтверждение в группу - ВАЖНО: проверяем, что сообщение пришло из темы
        thread_id = update.message.message_thread_id if update.message else None
        
        # Если сообщение пришло из темы, отправляем ответ в ту же тему
        if thread_id:
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=(
                    f"✅ <b>Администратор ответил на вопрос</b>\n\n"
                    f"👤 Пользователь: {user_id}\n"
                    f"👨‍💼 Администратор: @{admin.username or admin.id}\n"
                    f"📝 Ответ: {reply_text}"
                ),
                parse_mode=ParseMode.HTML,
                message_thread_id=thread_id  # Используем ID темы, из которой пришел ответ
            )
        else:
            # Если нет thread_id, отправляем в общий чат
            await context.bot.send_message(
                chat_id=GROUP_ID,
                text=(
                    f"✅ <b>Администратор ответил на вопрос</b>\n\n"
                    f"👤 Пользователь: {user_id}\n"
                    f"👨‍💼 Администратор: @{admin.username or admin.id}\n"
                    f"📝 Ответ: {reply_text}"
                ),
                parse_mode=ParseMode.HTML
            )
        
    except Exception as e:
        logger.error(f"Не удалось отправить ответ пользователю {user_id}: {e}")
        await update.message.reply_text(
            f"❌ Не удалось отправить ответ пользователю {user_id}. "
            f"Возможно, пользователь заблокировал бота."
        )

    context.user_data.clear()
    return ConversationHandler.END

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
        keyboard.append([InlineKeyboardButton("🗑 Удаление заданий у пользователей", callback_data="admin_remove_user_task_start")])
    
    # Добавляем кнопку удаления задания для всех админов
    keyboard.append([InlineKeyboardButton("❌ Удалить задание", callback_data="admin_delete_task_start")])

    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="back_main")])

    text = "👑 <b>АДМИН-ПАНЕЛЬ</b>\n\nВыберите действие:"

    await query.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def check_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_categories_menu")]])
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_categories_menu")]])
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_categories_menu")]])
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 К категориям", callback_data="admin_categories_menu")]])
        )
    else:
        await query.edit_message_text(
            "❌ Нельзя удалить категорию, у которой есть подкатегории.\n\n"
            "Сначала удалите все подкатегории.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 К категориям", callback_data="admin_categories_menu")]])
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Создать задание", callback_data="admin_create_task")]])
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

async def complete_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    task_id = query.data.split('_')[1]

    task = await TaskManager.get_by_id(task_id)
    if not task:
        await query.edit_message_text("❌ Задание не найдено.")
        return

    async with Database._pool.acquire() as conn:
        ut = await conn.fetchrow('SELECT * FROM user_tasks WHERE user_id = $1 AND task_id = $2', user_id, task_id)
        if not ut:
            await query.edit_message_text("❌ Это задание не было вами взято.")
            return
        if ut['status'] == 'completed':
            await query.edit_message_text("✅ Это задание уже выполнено и подтверждено.")
            return
        if ut['status'] == 'awaiting_payment':
            await query.edit_message_text("⏳ Задание ожидает подтверждения оплаты.")
            return

    request_id = await CompletionManager.create_request(task_id, user_id)

    user = await UserManager.get(user_id)
    text = (
        f"🔔 <b>Запрос на подтверждение выполнения</b>\n\n"
        f"👤 Пользователь: @{user['username'] or 'нет'} (ID: {user_id})\n"
        f"📋 Задание: {task['title']}\n"
        f"🆔 ID задания: <code>{task_id}</code>\n"
        f"💰 Награда: {task['reward']} ₽\n\n"
        f"Подтвердите или отклоните выполнение:"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{request_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{request_id}")
        ]
    ]
    try:
        sent_message = await context.bot.send_message(
            chat_id=GROUP_ID,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
            message_thread_id=TOPIC_COMPLETED
        )
        logger.info(f"✅ Запрос на подтверждение отправлен в тему {TOPIC_COMPLETED}, message_id: {sent_message.message_id}")
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление в тему 'сделанные задания': {e}")
        await query.edit_message_text("⚠️ Не удалось отправить запрос администратору. Попробуйте позже.")
        return

    await query.edit_message_text(
        f"✅ Запрос на подтверждение отправлен администратору.\n"
        f"Ожидайте, после проверки вы получите уведомление."
    )

async def approve_request_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info(f"✅ approve_request_callback вызван с data: {query.data}")
    await query.answer()
    
    admin_id = update.effective_user.id
    logger.info(f"Администратор {admin_id} нажал 'Подтвердить'")

    if not await AdminManager.is_admin(admin_id):
        await query.edit_message_text("⛔ У вас нет прав администратора.")
        return

    try:
        request_id = int(query.data.split('_')[1])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Неверный формат запроса.")
        return

    # Получаем информацию о запросе
    req = await CompletionManager.get_request(request_id)
    if not req:
        await query.edit_message_text("❌ Запрос не найден.")
        return
    
    if req['status'] != 'pending':
        await query.edit_message_text("❌ Запрос уже обработан.")
        return

    # Получаем информацию о задании
    task = await TaskManager.get_by_id(req['task_id'])
    if not task:
        await query.edit_message_text("❌ Задание не найдено.")
        return

    # Подтверждаем запрос через CompletionManager
    success = await CompletionManager.approve_request(request_id, admin_id)
    
    if not success:
        await query.edit_message_text("❌ Не удалось подтвердить запрос.")
        return

    # Добавляем запись в payment_awaiting
    await PaymentAwaitingManager.add(req['user_id'], req['task_id'], request_id)

    # Отправляем пользователю сообщение с запросом данных карты
    try:
        await context.bot.send_message(
            req['user_id'],
            "✅ <b>Ваше задание было одобрено!</b>\n\n"
            "Пришлите данные вашей карты для пополнения.\n"
            "Вы можете прислать текст или фото карты.\n\n"
            "<i>После отправки данных задание будет завершено, и награда поступит на ваш счёт.</i>\n\n"
            "Пример отправки:\nКарта: 0000 0000 0000 0000 \nИмя: Алексей \nБанк: Т-банк",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"✅ Запрос на данные карты отправлен пользователю {req['user_id']}")
    except Exception as e:
        logger.error(f"Не удалось отправить запрос данных карты пользователю {req['user_id']}: {e}")

    await query.edit_message_text(f"✅ Запрос #{request_id} одобрен. Пользователю отправлен запрос на предоставление данных карты.")

async def reject_request_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info(f"❌ reject_request_callback вызван с data: {query.data}")
    await query.answer()
    
    admin_id = update.effective_user.id
    logger.info(f"Администратор {admin_id} нажал 'Отклонить'")

    if not await AdminManager.is_admin(admin_id):
        await query.edit_message_text("⛔ У вас нет прав администратора.")
        return

    try:
        request_id = int(query.data.split('_')[1])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Неверный формат запроса.")
        return

    # Получаем информацию о запросе
    req = await CompletionManager.get_request(request_id)
    if not req:
        await query.edit_message_text("❌ Запрос не найден.")
        return
    
    if req['status'] != 'pending':
        await query.edit_message_text("❌ Запрос уже обработан.")
        return

    # Получаем информацию о задании
    task = await TaskManager.get_by_id(req['task_id'])

    # Отклоняем запрос
    success = await CompletionManager.reject_request(request_id, admin_id)
    
    if success:
        # Создаем клавиатуру с кнопкой "Задать вопрос"
        keyboard = [[InlineKeyboardButton("📝 Задать вопрос", callback_data="ask_question")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        task_title = task['title'] if task else "задания"
        
        try:
            await context.bot.send_message(
                req['user_id'],
                f"❌ <b>Заявка на выполнение задания была отклонена</b>\n\n"
                f"К сожалению, ваше выполнение задания «{task_title}» не прошло проверку.\n"
                f"Напишите, чтобы узнать подробности!",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            logger.info(f"✅ Уведомление об отклонении отправлено пользователю {req['user_id']}")
        except Exception as e:
            logger.error(f"Не удалось уведомить пользователя {req['user_id']}: {e}")

        await query.edit_message_text(f"❌ Запрос #{request_id} отклонён. Пользователь уведомлён.")
    else:
        await query.edit_message_text("❌ Не удалось отклонить запрос.")

async def pending_completions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await AdminManager.is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Только для администраторов.")
        return

    requests = await CompletionManager.get_pending_requests()
    if not requests:
        await update.message.reply_text("📭 Нет ожидающих запросов на подтверждение.")
        return

    text = "⏳ <b>Ожидают подтверждения:</b>\n\n"
    for r in requests:
        text += f"🔸 <b>{r['task_title']}</b>\n"
        text += f"   👤 @{r['username']} (ID: {r['user_id']})\n"
        text += f"   💰 {r['reward']} ₽\n"
        text += f"   🕒 {r['request_date'].strftime('%d.%m.%Y %H:%M')}\n"
        text += f"   🔹 ID запроса: {r['id']}\n\n"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

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
            f"После выполнения задания нажмите /my_tasks чтобы подтвердить выполнение задания\n\n"
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
            chat_id=GROUP_ID,
            text=(
                f"✅ <b>Администратор выдал ссылку</b>\n\n"
                f"📋 <b>Задание:</b> {pending['task_title']}\n"
                f"🆔 <b>ID:</b> <code>{task_id}</code>\n"
                f"👤 <b>Пользователь:</b> @{pending['username'] or pending['user_id']}\n"
                f"👨‍💼 <b>Администратор:</b> @{update.effective_user.username or update.effective_user.id}"
            ),
            parse_mode=ParseMode.HTML,
            message_thread_id=TOPIC_LINKS
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]])
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

# ==================== УДАЛЕНИЕ ЗАДАНИЙ У ПОЛЬЗОВАТЕЛЕЙ ====================
async def remove_user_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса удаления задания у пользователя"""
    if not await AdminManager.is_main_admin(update.effective_user.id):
        await update.callback_query.answer("⛔ Только главный админ может использовать эту функцию!", show_alert=True)
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🗑 <b>Удаление задания у пользователя</b>\n\n"
        "Введите ID пользователя:\n"
        "(например: 123456789)\n\n"
        "Или отправьте /cancel для отмены.",
        parse_mode=ParseMode.HTML
    )
    return REMOVE_TASK_USER_ID

async def remove_user_task_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение ID пользователя"""
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Операция отменена.")
        context.user_data.clear()
        return ConversationHandler.END

    try:
        user_id = int(update.message.text)
        context.user_data['remove_task_user_id'] = user_id
        
        user = await UserManager.get(user_id)
        if not user:
            await update.message.reply_text(
                f"❌ Пользователь с ID {user_id} не найден в базе.\n"
                f"Введите другой ID или /cancel для отмены:"
            )
            return REMOVE_TASK_USER_ID

        tasks = await TaskManager.get_user_tasks(user_id, status='active')
        
        if not tasks:
            await update.message.reply_text(
                f"📭 У пользователя {user_id} нет активных заданий.\n"
                f"Введите другой ID или /cancel для отмены:"
            )
            return REMOVE_TASK_USER_ID

        text = f"👤 <b>Пользователь:</b> {user_id} (@{user['username'] or 'нет'})\n\n"
        text += "📋 <b>Активные задания:</b>\n"
        
        for i, task in enumerate(tasks, 1):
            text += f"{i}. <b>{task['title']}</b> (ID: <code>{task['task_id']}</code>)\n"
            text += f"   💰 Награда: {task['reward']} ₽\n"
            taken_date = task.get('taken_date')
            if taken_date:
                text += f"   📅 Взято: {taken_date.strftime('%d.%m.%Y')}\n"
            text += "\n"

        text += "Введите ID задания для удаления:\n"
        text += "Или отправьте /cancel для отмены."

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return REMOVE_TASK_TASK_ID

    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите корректный числовой ID:")
        return REMOVE_TASK_USER_ID

async def remove_user_task_task_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение ID задания и его удаление"""
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Операция отменена.")
        context.user_data.clear()
        return ConversationHandler.END

    task_id = update.message.text.strip()
    user_id = context.user_data.get('remove_task_user_id')

    if not user_id:
        await update.message.reply_text("❌ Ошибка: ID пользователя не найден. Начните заново.")
        context.user_data.clear()
        return ConversationHandler.END

    async with Database._pool.acquire() as conn:
        task = await conn.fetchrow(
            'SELECT * FROM user_tasks WHERE user_id = $1 AND task_id = $2 AND status = $3',
            user_id, task_id, 'active'
        )
        
        if not task:
            await update.message.reply_text(
                f"❌ Задание {task_id} не найдено у пользователя {user_id} или уже завершено.\n"
                f"Введите другой ID или /cancel для отмены:"
            )
            return REMOVE_TASK_TASK_ID

        task_info = await TaskManager.get_by_id(task_id)

    async with Database.transaction() as conn:
        await conn.execute(
            'DELETE FROM user_tasks WHERE user_id = $1 AND task_id = $2',
            user_id, task_id
        )
        
        await conn.execute(
            'UPDATE tasks SET taken_by = NULL, available = TRUE, active = TRUE WHERE task_id = $1',
            task_id
        )
        
        await conn.execute(
            'DELETE FROM pending_links WHERE task_id = $1',
            task_id
        )

    try:
        await context.bot.send_message(
            user_id,
            f"⚠️ <b>Задание удалено администратором</b>\n\n"
            f"📋 Задание: {task_info['title']}\n"
            f"🆔 ID: {task_id}\n\n"
            f"Задание было удалено из вашего списка. "
            f"Если у вас есть вопросы, воспользуйтесь командой /help.",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"✅ Уведомление об удалении отправлено пользователю {user_id}")
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")

    await update.message.reply_text(
        f"✅ Задание {task_id} успешно удалено у пользователя {user_id}.\n"
        f"Пользователь уведомлён."
    )

    context.user_data.clear()
    return ConversationHandler.END

# ==================== УДАЛЕНИЕ ЗАДАНИЯ (ДЛЯ ВСЕХ АДМИНОВ) ====================
async def delete_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса удаления задания (полное удаление из БД)"""
    if not await AdminManager.is_admin(update.effective_user.id):
        await update.callback_query.answer("⛔ У вас нет прав администратора!", show_alert=True)
        return ConversationHandler.END

    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "❌ <b>Удаление задания</b>\n\n"
        "Введите ID задания, которое нужно полностью удалить из системы:\n"
        "(например: 8ff025ef)\n\n"
        "Или отправьте /cancel для отмены.",
        parse_mode=ParseMode.HTML
    )
    return DELETE_TASK_ID

async def delete_task_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение ID задания и его удаление"""
    if update.message.text == '/cancel':
        await update.message.reply_text("❌ Операция отменена.")
        context.user_data.clear()
        return ConversationHandler.END

    task_id = update.message.text.strip()
    admin_id = update.effective_user.id

    # Проверяем существование задания
    task = await TaskManager.get_by_id(task_id)
    if not task:
        await update.message.reply_text(
            f"❌ Задание с ID {task_id} не найдено.\n"
            f"Введите другой ID или /cancel для отмены:"
        )
        return DELETE_TASK_ID

    # Подтверждение удаления
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_delete_{task_id}"),
            InlineKeyboardButton("❌ Нет, отмена", callback_data="cancel_delete")
        ]
    ]
    await update.message.reply_text(
        f"⚠️ <b>Вы действительно хотите полностью удалить задание?</b>\n\n"
        f"📋 Название: {task['title']}\n"
        f"🆔 ID: {task_id}\n"
        f"💰 Награда: {task['reward']} ₽\n\n"
        f"Все связанные данные (взятия, запросы, ссылки) будут безвозвратно удалены.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END  # Выходим из диалога, дальше обработаем callback

async def confirm_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления задания"""
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_delete":
        await query.edit_message_text("❌ Удаление отменено.")
        return

    # data = "confirm_delete_TASK_ID"
    task_id = query.data.split('_')[2]
    admin_id = update.effective_user.id

    success = await TaskManager.delete_task(task_id, admin_id)
    if success:
        await query.edit_message_text(f"✅ Задание {task_id} успешно удалено.")
    else:
        await query.edit_message_text(f"❌ Не удалось удалить задание {task_id}.")

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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 К категориям", callback_data="user_tasks")]])
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главное меню", callback_data="back_main")]])
        )
        return

    task = await TaskManager.get_by_id(task_id)
    if not task or not task['available']:
        await query.edit_message_text(
            "❌ Это задание уже недоступно.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 Другие задания", callback_data="user_tasks")]])
        )
        return

    success = await TaskManager.assign(task_id, user_id)
    if not success:
        await query.edit_message_text(
            "❌ Не удалось взять задание. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Попробовать снова", callback_data=f"take_{task_id}")]])
        )
        return

    tracking_link = await TrackingManager.generate_link(user_id, task_id)
    await PendingManager.save(
        task_id, user_id,
        user.get('username', ''),
        task['title'],
        tracking_link
    )

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
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text=admin_msg,
            parse_mode=ParseMode.HTML,
            message_thread_id=TOPIC_LINKS
        )
        logger.info(f"✅ Уведомление отправлено в тему 'ссылки' (ID: {TOPIC_LINKS}) для задания {task_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в тему 'ссылки': {e}")

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
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 Мои задания", callback_data="user_my_tasks")]])
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
            await asyncio.sleep(0.05)
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
    data = query.data
    
    if data.startswith(('approve_', 'reject_', 'complete_', 'answer_user_', 'confirm_delete_')):
        logger.info(f"Пропускаем через main_button_handler: {data}")
        return  # Пусть обрабатывается более конкретными обработчиками
    
    await query.answer()
    logger.info(f"Главный обработчик: нажата кнопка {data}")

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
    elif data == "ask_question":
        await ask_question_start(update, context)
    elif data == "all_tasks":
        await show_tasks(update, context, category_id=None)
    elif data.startswith("cat_"):
        cat_id = int(data.split('_')[1])
        await show_tasks(update, context, category_id=cat_id)
    elif data.startswith("take_"):
        await take_task_callback(update, context)
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
        elif data == "admin_remove_user_task_start":
            await remove_user_task_start(update, context)
        elif data == "admin_delete_task_start":
            await delete_task_start(update, context)

async def handle_payment_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Перехватывает сообщения (текст или фото) от пользователей, ожидающих отправки данных карты."""
    user_id = update.effective_user.id
    logger.info(f"Получено сообщение от пользователя {user_id} в ожидании данных карты")
    
    awaiting = await PaymentAwaitingManager.get_by_user(user_id)
    if not awaiting:
        logger.info(f"Пользователь {user_id} не в ожидании данных карты, игнорируем")
        return

    task_id = awaiting['task_id']
    request_id = awaiting['request_id']
    
    logger.info(f"Пользователь {user_id} ожидает отправки данных для задания {task_id}, запрос {request_id}")

    task = await TaskManager.get_by_id(task_id)
    if not task:
        logger.error(f"Задание {task_id} не найдено")
        await update.message.reply_text("❌ Ошибка: задание не найдено. Обратитесь в поддержку.")
        return

    try:
        logger.info(f"Попытка пересылки сообщения {update.message.message_id} в группу {GROUP_ID}, топик {REPORT_TOPIC}")
        
        forwarded = await context.bot.forward_message(
            chat_id=GROUP_ID,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
            message_thread_id=REPORT_TOPIC
        )
        logger.info(f"✅ Сообщение переслано, ID пересланного: {forwarded.message_id}")
        
        info_text = (
            f"📌 <b>Данные карты для задания</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Пользователь:</b>\n"
            f"  • ID: <code>{user_id}</code>\n"
            f"  • Username: @{update.effective_user.username or 'нет'}\n"
            f"  • Имя: {update.effective_user.first_name}\n\n"
            f"📋 <b>Задание:</b>\n"
            f"  • Название: {task['title']}\n"
            f"  • ID: <code>{task_id}</code>\n"
            f"  • Награда: {task['reward']} ₽\n"
            f"  • Запрос ID: {request_id}\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )
        
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text=info_text,
            parse_mode=ParseMode.HTML,
            message_thread_id=REPORT_TOPIC
        )
        logger.info("✅ Информация о задании отправлена в группу отчётов")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при пересылке в группу отчётов: {e}")
        logger.exception("Полный стек ошибки:")
        
        # Отправка администраторам в ЛС как запасной вариант
        admins = await AdminManager.get_all_admins()
        sent = False
        for admin in admins:
            try:
                await context.bot.forward_message(
                    chat_id=admin['user_id'],
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id
                )
                await context.bot.send_message(
                    admin['user_id'],
                    f"⚠️ <b>Данные карты от пользователя</b> (группа отчётов недоступна)\n"
                    f"👤 User ID: {user_id}\n"
                    f"📋 Задание: {task['title']} ({task_id})\n"
                    f"💰 Награда: {task['reward']} ₽",
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"✅ Данные отправлены администратору {admin['user_id']}")
                sent = True
                break
            except Exception as e2:
                logger.error(f"Не удалось отправить администратору {admin['user_id']}: {e2}")
        
        if not sent:
            await update.message.reply_text(
                "❌ Не удалось отправить данные в группу отчётов. "
                "Пожалуйста, обратитесь в поддержку."
            )
            return

    # ЗАВЕРШАЕМ ЗАДАНИЕ ПОСЛЕ ПОЛУЧЕНИЯ ДАННЫХ КАРТЫ
    logger.info(f"Попытка завершения задания {task_id} для пользователя {user_id}")
    
    # Используем транзакцию для завершения задания
    async with Database.transaction() as conn:
        # Проверяем, не завершено ли уже задание
        task_check = await conn.fetchrow(
            'SELECT completed FROM tasks WHERE task_id = $1',
            task_id
        )
        
        if task_check and task_check['completed']:
            logger.info(f"Задание {task_id} уже завершено")
            await update.message.reply_text(
                "✅ Задание уже было завершено ранее. Спасибо!"
            )
            await PaymentAwaitingManager.mark_completed(awaiting['id'])
            return
        
        # Завершаем задание
        await conn.execute('''
            UPDATE tasks 
            SET completed = TRUE, 
                completed_date = NOW(), 
                active = FALSE,
                proof = $2
            WHERE task_id = $1
        ''', task_id, "payment_data_sent")
        
        # Обновляем user_tasks
        await conn.execute('''
            UPDATE user_tasks 
            SET status = 'completed', 
                completed_date = NOW(), 
                earned = $2
            WHERE user_id = $3 AND task_id = $1
        ''', task_id, task['reward'], user_id)
        
        # Обновляем пользователя
        await conn.execute('''
            UPDATE users 
            SET total_earned = total_earned + $2, 
                completed_tasks = completed_tasks + 1 
            WHERE user_id = $1
        ''', user_id, task['reward'])
        
        # Обновляем статистику
        await conn.execute('''
            INSERT INTO stats (date, tasks_completed, total_payout) 
            VALUES (CURRENT_DATE, 1, $1)
            ON CONFLICT (date) DO UPDATE SET 
                tasks_completed = stats.tasks_completed + 1,
                total_payout = stats.total_payout + $1
        ''', task['reward'])
    
    logger.info(f"✅ Задание {task_id} успешно завершено для пользователя {user_id}")

    # Отмечаем запись в payment_awaiting как выполненную
    await PaymentAwaitingManager.mark_completed(awaiting['id'])

    await update.message.reply_text(
        "✅ Спасибо! Ваши данные получены. Задание успешно завершено, награда зачислена.\n"
        "Вы можете проверить свой профиль командой /profile."
    )
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

async def check_bot_permissions(application: Application):
    """Проверяет права бота в группе"""
    try:
        chat = await application.bot.get_chat(GROUP_ID)
        logger.info(f"✅ Группа найдена: {chat.title} (ID: {chat.id})")
        
        bot_member = await chat.get_member(application.bot.id)
        logger.info(f"🤖 Статус бота в группе: {bot_member.status}")
        
        if bot_member.status not in ['administrator', 'creator']:
            logger.warning("⚠️ Бот не является администратором группы! Некоторые функции могут не работать.")
        else:
            logger.info("✅ Бот является администратором группы")
            
        # Проверяем доступ к темам
        try:
            # Пробуем отправить тестовое сообщение в тему
            await application.bot.send_message(
                chat_id=GROUP_ID,
                text="✅ Бот успешно подключен к группе и темам!",
                message_thread_id=TOPIC_COMPLETED
            )
            logger.info("✅ Бот имеет доступ к темам")
        except Exception as e:
            logger.error(f"❌ Бот не имеет доступа к темам: {e}")
            
    except Exception as e:
        logger.error(f"❌ Не удалось получить информацию о группе: {e}")

async def post_init(application: Application):
    await Database.init_pool()
    await check_bot_permissions(application)  # Добавьте эту строку
    logger.info("✅ Бот запущен и готов к работе!")
    logger.info(f"👑 Главный администратор: {MAIN_ADMIN_ID}")
    logger.info(f"📢 Группа ID: {GROUP_ID}")
    logger.info(f"📌 Темы: ссылки={TOPIC_LINKS}, вопросы={TOPIC_QUESTIONS}, выполненные={TOPIC_COMPLETED}, отчёты={REPORT_TOPIC}")

async def shutdown(application: Application):
    await Database.close_pool()
    logger.info("✅ Пул БД закрыт.")

def main():
    if not TOKEN:
        logger.error("❌ BOT_TOKEN не задан!")
        return

    application = Application.builder().token(TOKEN).post_init(post_init).build()
    application.post_shutdown = shutdown

    # ========== 1. СНАЧАЛА САМЫЕ КОНКРЕТНЫЕ ОБРАБОТЧИКИ ==========
    # Обработчики для кнопок подтверждения/отклонения (самые приоритетные)
    application.add_handler(CallbackQueryHandler(approve_request_callback, pattern="^approve_\\d+$"))
    application.add_handler(CallbackQueryHandler(reject_request_callback, pattern="^reject_\\d+$"))
    
    # Обработчик для кнопки "Я выполнил задание"
    application.add_handler(CallbackQueryHandler(complete_task_callback, pattern="^complete_[a-zA-Z0-9]+$"))
    
    # Обработчик для ответа пользователю
    application.add_handler(CallbackQueryHandler(answer_user_callback, pattern="^answer_user_\\d+$"))

    # Обработчик подтверждения удаления задания
    application.add_handler(CallbackQueryHandler(confirm_delete_callback, pattern="^(confirm_delete_|cancel_delete)$"))

    # ========== 2. ПОТОМ ДИАЛОГИ ==========
    
    # Диалог для вопросов от пользователей
    ask_question_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_question_start, pattern="^ask_question$")],
        states={
            ASK_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_question_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="ask_question_conv",
        allow_reentry=True,
        persistent=False
    )
    application.add_handler(ask_question_conv)

    # Диалог для ответов администратора
    admin_reply_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(answer_user_callback, pattern="^answer_user_\\d+$")],
        states={
            ASK_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_reply)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="admin_reply_conv",
        allow_reentry=True,
        persistent=False
    )
    application.add_handler(admin_reply_conv)

    # Диалог рассылки
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={
            BROADCAST_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="broadcast_conv",
        persistent=False
    )
    application.add_handler(broadcast_conv)

    # Диалог удаления задания у пользователя
    remove_task_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(remove_user_task_start, pattern="^admin_remove_user_task_start$")],
        states={
            REMOVE_TASK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_user_task_user_id)],
            REMOVE_TASK_TASK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_user_task_task_id)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="remove_task_conv",
        persistent=False
    )
    application.add_handler(remove_task_conv)

    # Диалог удаления задания (полное удаление)
    delete_task_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(delete_task_start, pattern="^admin_delete_task_start$")],
        states={
            DELETE_TASK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_task_id_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="delete_task_conv",
        persistent=False
    )
    application.add_handler(delete_task_conv)

    # Диалог добавления администратора
    conv_add_admin = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_admin_start, pattern="^admin_add_admin_start$")],
        states={
            ADD_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_id)],
            ADD_ADMIN_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_username)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="add_admin_conv",
        persistent=False
    )
    application.add_handler(conv_add_admin)

    # Диалог добавления категории
    conv_add_category = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_category_start, pattern="^admin_add_category$")],
        states={
            CATEGORY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_category_name)],
            CATEGORY_PARENT: [CallbackQueryHandler(add_category_parent, pattern="^(cat_parent_none|cat_parent_\\d+|cat_parent_select|cancel_category)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="add_category_conv",
        persistent=False
    )
    application.add_handler(conv_add_category)

    # Диалог создания задания
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
        name="create_task_conv",
        persistent=False
    )
    application.add_handler(conv_create_task)

    # ========== 3. ПОТОМ КОМАНДЫ ==========
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("tasks", tasks))
    application.add_handler(CommandHandler("my_tasks", my_tasks))
    application.add_handler(CommandHandler("add_admin", add_admin_command))
    application.add_handler(CommandHandler("remove_admin", remove_admin_command))
    application.add_handler(CommandHandler("give_link", give_link_command))
    application.add_handler(CommandHandler("check_tasks", check_tasks_command))
    application.add_handler(CommandHandler("pending_completions", pending_completions_command))
    application.add_handler(CommandHandler("users_count", users_count_command))
    application.add_handler(CommandHandler("user_info", user_info_command))
    application.add_handler(CommandHandler("users_list", users_list_command))
    application.add_handler(CommandHandler("check_admin", check_admin_command))

    # ========== 4. ПОТОМ ОБЩИЙ ОБРАБОТЧИК КНОПОК (САМЫЙ НИЗКИЙ ПРИОРИТЕТ) ==========
    application.add_handler(CallbackQueryHandler(main_button_handler))

    # ========== 5. ПОТОМ ОБРАБОТЧИКИ СООБЩЕНИЙ ==========
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_payment_data))
    application.add_handler(MessageHandler(filters.PHOTO, handle_payment_data))

    # ========== 6. ОБРАБОТЧИК ОШИБОК ==========
    application.add_error_handler(error_handler)

    logger.info("🚀 Запуск бота...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()