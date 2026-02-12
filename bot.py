import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота из переменных окружения
TOKEN = os.environ.get('BOT_TOKEN')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    await update.message.reply_text(
        f'Привет, {user.first_name}! 👋\n'
        'Я бот, работающий на Railway!'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    await update.message.reply_text(
        'Доступные команды:\n'
        '/start - Приветствие\n'
        '/help - Справка'
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Эхо-обработчик текстовых сообщений"""
    await update.message.reply_text(f'Вы написали: {update.message.text}')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")

def main():
    """Главная функция"""
    if not TOKEN:
        logger.error("Токен бота не найден! Установите BOT_TOKEN в переменных окружения.")
        logger.error("Создайте файл .env с переменной BOT_TOKEN=ваш_токен")
        return

    try:
        # Создаем приложение
        application = Application.builder().token(TOKEN).build()

        # Регистрируем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
        application.add_error_handler(error_handler)

        # Запускаем бота
        logger.info("Бот запущен и готов к работе!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except AttributeError as e:
        logger.error(f"Ошибка совместимости: {e}")
        logger.error("Попробуйте установить python-telegram-bot версии 20.3:")
        logger.error("pip uninstall python-telegram-bot")
        logger.error("pip install python-telegram-bot==20.3")
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {e}")

if __name__ == '__main__':
    main()