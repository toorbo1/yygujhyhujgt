import os
import logging
import asyncio
import json
import hashlib
import secrets
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from contextlib import asynccontextmanager
from enum import Enum
from string import Template

import asyncpg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters,
    ConversationHandler
)
from telegram.constants import ParseMode
from dotenv import load_dotenv

# ==================== ЗАГРУЗКА КОНФИГУРАЦИИ ====================
load_dotenv()

TOKEN = os.environ.get('BOT_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/bot_db')
MAIN_ADMIN_ID = int(os.environ.get('MAIN_ADMIN_ID', '8358009538'))
TASK_NOTIFICATION_GROUP = os.environ.get('TASK_NOTIFICATION_GROUP', '@wedferfwewf')
REPORT_GROUP = os.environ.get('REPORT_GROUP', '@ertghpjoterg')
BOT_USERNAME = os.environ.get('BOT_USERNAME', 'TrafficWorkeee_bot')

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== КОНСТАНТЫ И ENUM ====================

class TaskType(str, Enum):
    SUBSCRIBE = "subscribe"
    LIKE = "like"
    COMMENT = "comment"
    REPOST = "repost"
    VISIT = "visit"
    CHANNEL_SUBSCRIBE = "channel_subscribe"
    BOT_START = "bot_start"
    POST_LIKE = "post_like"
    GROUP_JOIN = "group_join"

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    MAIN_ADMIN = "main_admin"

class TaskStatus(str, Enum):
    AVAILABLE = "available"
    TAKEN = "taken"
    COMPLETED = "completed"
    PENDING = "pending"
    CANCELLED = "cancelled"
    VERIFYING = "verifying"

class ConversationState:
    """Состояния для ConversationHandler"""
    # Админские состояния
    ADMIN_ADD_USER_ID = 1
    ADMIN_REMOVE_USER_ID = 2
    ADMIN_CREATE_CATEGORY = 3
    ADMIN_CREATE_SUBCATEGORY = 4
    ADMIN_CREATE_TASK_TITLE = 5
    ADMIN_CREATE_TASK_DESC = 6
    ADMIN_CREATE_TASK_TYPE = 7
    ADMIN_CREATE_TASK_TARGET = 8
    ADMIN_CREATE_TASK_REWARD = 9
    ADMIN_CREATE_TASK_REQUIREMENTS = 10
    ADMIN_CREATE_TASK_CATEGORY = 11
    ADMIN_CREATE_TASK_SUBCATEGORY = 12
    ADMIN_CREATE_TASK_DEADLINE = 13
    ADMIN_EDIT_TASK = 14
    ADMIN_SET_WORK_LINK = 15
    
    # Пользовательские состояния
    USER_PROOF = 20
    USER_FEEDBACK = 21

# ==================== БАЗА ДАННЫХ ====================

class Database:
    """Менеджер подключения к PostgreSQL"""
    _pool = None
    
    @classmethod
    async def init_db(cls):
        """Инициализация пула подключений и создание таблиц"""
        try:
            cls._pool = await asyncpg.create_pool(DATABASE_URL)
            logger.info("✅ Подключение к PostgreSQL установлено")
            await cls.create_tables()
            return cls._pool
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
            raise
    
    @classmethod
    async def create_tables(cls):
        """Создание всех таблиц"""
        async with cls._pool.acquire() as conn:
            # Таблица пользователей
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    joined_date TIMESTAMP DEFAULT NOW(),
                    is_admin BOOLEAN DEFAULT FALSE,
                    added_by BIGINT,
                    permissions JSONB DEFAULT '["view_tasks"]',
                    total_earned DECIMAL(10,2) DEFAULT 0,
                    tasks_completed INTEGER DEFAULT 0,
                    rating INTEGER DEFAULT 0,
                    referral_count INTEGER DEFAULT 0,
                    last_active TIMESTAMP DEFAULT NOW(),
                    blocked BOOLEAN DEFAULT FALSE,
                    language TEXT DEFAULT 'ru',
                    notifications_enabled BOOLEAN DEFAULT TRUE,
                    wallet_address TEXT,
                    FOREIGN KEY (added_by) REFERENCES users(user_id) ON DELETE SET NULL
                )
            ''')
            
            # Таблица категорий
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    icon TEXT,
                    created_by BIGINT,
                    created_date TIMESTAMP DEFAULT NOW(),
                    is_active BOOLEAN DEFAULT TRUE,
                    sort_order INTEGER DEFAULT 0,
                    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL
                )
            ''')
            
            # Таблица подкатегорий
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS subcategories (
                    id SERIAL PRIMARY KEY,
                    category_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    icon TEXT,
                    created_by BIGINT,
                    created_date TIMESTAMP DEFAULT NOW(),
                    is_active BOOLEAN DEFAULT TRUE,
                    sort_order INTEGER DEFAULT 0,
                    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE,
                    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL,
                    UNIQUE(category_id, name)
                )
            ''')
            
            # Таблица заданий
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    task_type TEXT NOT NULL,
                    target TEXT NOT NULL,
                    target_count INTEGER DEFAULT 1,
                    current_count INTEGER DEFAULT 0,
                    reward DECIMAL(10,2) NOT NULL,
                    requirements TEXT,
                    created_by BIGINT,
                    created_date TIMESTAMP DEFAULT NOW(),
                    active BOOLEAN DEFAULT TRUE,
                    available BOOLEAN DEFAULT TRUE,
                    taken_by BIGINT,
                    assigned_date TIMESTAMP,
                    work_link TEXT,
                    completed BOOLEAN DEFAULT FALSE,
                    completed_date TIMESTAMP,
                    proof TEXT,
                    deadline TIMESTAMP,
                    category_id INTEGER,
                    subcategory_id INTEGER,
                    max_workers INTEGER DEFAULT 1,
                    current_workers INTEGER DEFAULT 0,
                    image_url TEXT,
                    link_template TEXT,
                    verification_type TEXT DEFAULT 'manual',
                    FOREIGN KEY (taken_by) REFERENCES users(user_id) ON DELETE SET NULL,
                    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL,
                    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
                    FOREIGN KEY (subcategory_id) REFERENCES subcategories(id) ON DELETE SET NULL
                )
            ''')
            
            # Таблица заданий, взятых пользователями
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_tasks (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    task_id TEXT NOT NULL,
                    status TEXT DEFAULT 'taken',
                    taken_date TIMESTAMP DEFAULT NOW(),
                    completed_date TIMESTAMP,
                    earned DECIMAL(10,2),
                    proof TEXT,
                    admin_approved BOOLEAN DEFAULT FALSE,
                    approved_by BIGINT,
                    approved_date TIMESTAMP,
                    rejection_reason TEXT,
                    tracking_link_id TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE,
                    FOREIGN KEY (approved_by) REFERENCES users(user_id) ON DELETE SET NULL,
                    UNIQUE(user_id, task_id)
                )
            ''')
            
            # Таблица отслеживающих ссылок
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tracking_links (
                    link_id TEXT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    task_id TEXT NOT NULL,
                    created TIMESTAMP DEFAULT NOW(),
                    clicks INTEGER DEFAULT 0,
                    conversions INTEGER DEFAULT 0,
                    active BOOLEAN DEFAULT TRUE,
                    work_link TEXT,
                    target TEXT,
                    target_count INTEGER DEFAULT 1,
                    completed_count INTEGER DEFAULT 0,
                    unique_users JSONB DEFAULT '[]',
                    last_click TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
            ''')
            
            # Таблица ожидающих ссылок (для админов)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS pending_links (
                    id SERIAL PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    user_id BIGINT NOT NULL,
                    username TEXT,
                    task_title TEXT,
                    message_sent TIMESTAMP DEFAULT NOW(),
                    processed BOOLEAN DEFAULT FALSE,
                    processed_by BIGINT,
                    processed_date TIMESTAMP,
                    admin_message_id INTEGER,
                    group_chat_id TEXT,
                    tracking_link TEXT,
                    work_link TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE,
                    FOREIGN KEY (processed_by) REFERENCES users(user_id) ON DELETE SET NULL
                )
            ''')
            
            # Таблица для статистики
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS stats (
                    id SERIAL PRIMARY KEY,
                    date DATE DEFAULT CURRENT_DATE,
                    new_users INTEGER DEFAULT 0,
                    tasks_completed INTEGER DEFAULT 0,
                    total_payout DECIMAL(10,2) DEFAULT 0,
                    clicks INTEGER DEFAULT 0,
                    active_users INTEGER DEFAULT 0,
                    tasks_created INTEGER DEFAULT 0,
                    UNIQUE(date)
                )
            ''')
            
            # Таблица для рефералов
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS referrals (
                    id SERIAL PRIMARY KEY,
                    referrer_id BIGINT NOT NULL,
                    referred_id BIGINT NOT NULL UNIQUE,
                    date TIMESTAMP DEFAULT NOW(),
                    reward_given BOOLEAN DEFAULT FALSE,
                    reward_amount DECIMAL(10,2) DEFAULT 0,
                    FOREIGN KEY (referrer_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (referred_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            ''')
            
            # Таблица для отчетов
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    task_id TEXT,
                    report_type TEXT NOT NULL,
                    description TEXT,
                    screenshot TEXT,
                    status TEXT DEFAULT 'pending',
                    created_date TIMESTAMP DEFAULT NOW(),
                    resolved_by BIGINT,
                    resolved_date TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE SET NULL,
                    FOREIGN KEY (resolved_by) REFERENCES users(user_id) ON DELETE SET NULL
                )
            ''')
            
            # Таблица для баланса и выводов
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS withdrawals (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    wallet_address TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_date TIMESTAMP DEFAULT NOW(),
                    processed_date TIMESTAMP,
                    processed_by BIGINT,
                    tx_hash TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (processed_by) REFERENCES users(user_id) ON DELETE SET NULL
                )
            ''')
            
            # Индексы для ускорения запросов
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_admin ON users(is_admin)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_available ON tasks(available, active)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_taken_by ON tasks(taken_by)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_user_tasks_user ON user_tasks(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_user_tasks_status ON user_tasks(status)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_tracking_links_active ON tracking_links(active)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_pending_links_processed ON pending_links(processed)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_subcategory ON tasks(subcategory_id)')
            
            logger.info("✅ Таблицы созданы/проверены")
    
    @classmethod
    async def close_pool(cls):
        """Закрытие пула подключений"""
        if cls._pool:
            await cls._pool.close()
            logger.info("✅ Подключение к PostgreSQL закрыто")
    
    @classmethod
    @asynccontextmanager
    async def transaction(cls):
        """Контекстный менеджер для транзакций"""
        async with cls._pool.acquire() as conn:
            async with conn.transaction():
                yield conn

# ==================== МЕНЕДЖЕРЫ БАЗЫ ДАННЫХ ====================

class UserManager:
    """Менеджер для работы с пользователями"""
    
    @staticmethod
    async def get_or_create(user_id: int, username: str = "", first_name: str = "", last_name: str = "") -> Dict:
        """Получить или создать пользователя"""
        async with Database._pool.acquire() as conn:
            user = await conn.fetchrow(
                'SELECT * FROM users WHERE user_id = $1',
                user_id
            )
            
            if not user:
                await conn.execute(
                    '''
                    INSERT INTO users (user_id, username, first_name, last_name, joined_date, last_active)
                    VALUES ($1, $2, $3, $4, NOW(), NOW())
                    ''',
                    user_id, username[:32], first_name[:64], last_name[:64]
                )
                user = await conn.fetchrow(
                    'SELECT * FROM users WHERE user_id = $1',
                    user_id
                )
                
                # Обновляем статистику
                await conn.execute(
                    '''
                    INSERT INTO stats (date, new_users)
                    VALUES (CURRENT_DATE, 1)
                    ON CONFLICT (date) DO UPDATE
                    SET new_users = stats.new_users + 1
                    '''
                )
            
            return dict(user)
    
    @staticmethod
    async def get(user_id: int) -> Optional[Dict]:
        """Получить пользователя по ID"""
        async with Database._pool.acquire() as conn:
            user = await conn.fetchrow(
                'SELECT * FROM users WHERE user_id = $1',
                user_id
            )
            return dict(user) if user else None
    
    @staticmethod
    async def update(user_id: int, **kwargs) -> bool:
        """Обновить данные пользователя"""
        async with Database._pool.acquire() as conn:
            set_clause = ', '.join(f"{key} = ${i+2}" for i, key in enumerate(kwargs.keys()))
            query = f'UPDATE users SET {set_clause}, last_active = NOW() WHERE user_id = $1'
            await conn.execute(query, user_id, *kwargs.values())
            return True
    
    @staticmethod
    async def get_stats(user_id: int) -> Dict:
        """Получение статистики пользователя"""
        async with Database._pool.acquire() as conn:
            # Завершенные задания
            completed = await conn.fetchval(
                '''
                SELECT COUNT(*) FROM user_tasks 
                WHERE user_id = $1 AND status = 'completed' AND admin_approved = TRUE
                ''',
                user_id
            ) or 0
            
            # Активные задания
            active = await conn.fetchval(
                '''
                SELECT COUNT(*) FROM user_tasks 
                WHERE user_id = $1 AND status = 'taken'
                ''',
                user_id
            ) or 0
            
            # Задания на проверке
            verifying = await conn.fetchval(
                '''
                SELECT COUNT(*) FROM user_tasks 
                WHERE user_id = $1 AND status = 'verifying'
                ''',
                user_id
            ) or 0
            
            # Общий заработок
            total_earned = await conn.fetchval(
                '''
                SELECT COALESCE(SUM(earned), 0) FROM user_tasks 
                WHERE user_id = $1 AND status = 'completed' AND admin_approved = TRUE
                ''',
                user_id
            ) or 0
            
            # Количество рефералов
            referrals = await conn.fetchval(
                'SELECT COUNT(*) FROM referrals WHERE referrer_id = $1',
                user_id
            ) or 0
            
            # Рейтинг
            rating = await conn.fetchval(
                '''
                SELECT rating FROM users WHERE user_id = $1
                ''',
                user_id
            ) or 0
            
            return {
                "completed_count": completed,
                "active_count": active,
                "verifying_count": verifying,
                "total_earned": float(total_earned),
                "referrals": referrals,
                "rating": rating
            }

class AdminManager:
    """Менеджер для работы с администраторами"""
    
    @staticmethod
    async def is_admin(user_id: int) -> bool:
        """Проверка, является ли пользователь админом"""
        if user_id == MAIN_ADMIN_ID:
            return True
        
        async with Database._pool.acquire() as conn:
            user = await conn.fetchval(
                'SELECT is_admin FROM users WHERE user_id = $1',
                user_id
            )
            return bool(user)
    
    @staticmethod
    async def is_main_admin(user_id: int) -> bool:
        """Проверка, является ли пользователь главным админом"""
        return user_id == MAIN_ADMIN_ID
    
    @staticmethod
    async def add_admin(user_id: int, added_by: int = None) -> Tuple[bool, str]:
        """Добавление администратора"""
        if user_id == MAIN_ADMIN_ID:
            return False, "Главный админ уже имеет все права"
        
        async with Database._pool.acquire() as conn:
            # Проверяем, существует ли пользователь
            user = await conn.fetchrow(
                'SELECT * FROM users WHERE user_id = $1',
                user_id
            )
            
            if not user:
                return False, "Пользователь не найден в базе"
            
            if user['is_admin']:
                return False, "Пользователь уже является администратором"
            
            await conn.execute(
                '''
                UPDATE users 
                SET is_admin = TRUE, 
                    added_by = $2,
                    permissions = '["manage_tasks", "view_stats", "manage_users", "create_categories"]'::jsonb
                WHERE user_id = $1
                ''',
                user_id, added_by or MAIN_ADMIN_ID
            )
            
            return True, f"✅ Пользователь {user_id} назначен администратором"
    
    @staticmethod
    async def remove_admin(user_id: int) -> Tuple[bool, str]:
        """Удаление администратора"""
        if user_id == MAIN_ADMIN_ID:
            return False, "❌ Нельзя удалить главного администратора"
        
        async with Database._pool.acquire() as conn:
            user = await conn.fetchrow(
                'SELECT * FROM users WHERE user_id = $1',
                user_id
            )
            
            if not user:
                return False, "❌ Пользователь не найден"
            
            if not user['is_admin']:
                return False, "❌ Пользователь не является администратором"
            
            await conn.execute(
                'UPDATE users SET is_admin = FALSE WHERE user_id = $1',
                user_id
            )
            
            return True, f"✅ Права администратора удалены у пользователя {user_id}"
    
    @staticmethod
    async def get_all_admins() -> List[Dict]:
        """Получение списка всех админов"""
        async with Database._pool.acquire() as conn:
            admins = await conn.fetch(
                '''
                SELECT * FROM users 
                WHERE is_admin = TRUE OR user_id = $1
                ORDER BY user_id
                ''',
                MAIN_ADMIN_ID
            )
            return [dict(admin) for admin in admins]
    
    @staticmethod
    async def has_permission(user_id: int, permission: str) -> bool:
        """Проверка наличия разрешения у админа"""
        if user_id == MAIN_ADMIN_ID:
            return True
        
        async with Database._pool.acquire() as conn:
            user = await conn.fetchrow(
                'SELECT permissions FROM users WHERE user_id = $1 AND is_admin = TRUE',
                user_id
            )
            
            if not user:
                return False
            
            permissions = user['permissions']
            return permission in permissions

class CategoryManager:
    """Менеджер для работы с категориями"""
    
    @staticmethod
    async def create_category(name: str, description: str, icon: str, created_by: int) -> Dict:
        """Создание категории"""
        async with Database._pool.acquire() as conn:
            try:
                category_id = await conn.fetchval(
                    '''
                    INSERT INTO categories (name, description, icon, created_by)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    ''',
                    name, description, icon, created_by
                )
                
                return {
                    "id": category_id,
                    "name": name,
                    "description": description,
                    "icon": icon
                }
            except asyncpg.UniqueViolationError:
                return None
    
    @staticmethod
    async def get_all_categories(active_only: bool = True) -> List[Dict]:
        """Получение всех категорий"""
        async with Database._pool.acquire() as conn:
            query = 'SELECT * FROM categories'
            if active_only:
                query += ' WHERE is_active = TRUE'
            query += ' ORDER BY sort_order, name'
            
            categories = await conn.fetch(query)
            return [dict(cat) for cat in categories]
    
    @staticmethod
    async def create_subcategory(category_id: int, name: str, description: str, icon: str, created_by: int) -> Dict:
        """Создание подкатегории"""
        async with Database._pool.acquire() as conn:
            try:
                subcategory_id = await conn.fetchval(
                    '''
                    INSERT INTO subcategories (category_id, name, description, icon, created_by)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                    ''',
                    category_id, name, description, icon, created_by
                )
                
                return {
                    "id": subcategory_id,
                    "category_id": category_id,
                    "name": name,
                    "description": description,
                    "icon": icon
                }
            except asyncpg.UniqueViolationError:
                return None
    
    @staticmethod
    async def get_subcategories(category_id: int, active_only: bool = True) -> List[Dict]:
        """Получение подкатегорий для категории"""
        async with Database._pool.acquire() as conn:
            query = 'SELECT * FROM subcategories WHERE category_id = $1'
            if active_only:
                query += ' AND is_active = TRUE'
            query += ' ORDER BY sort_order, name'
            
            subcategories = await conn.fetch(query, category_id)
            return [dict(sub) for sub in subcategories]

class TaskManager:
    """Менеджер для работы с заданиями"""
    
    @staticmethod
    async def create_task(
        title: str,
        description: str,
        task_type: str,
        target: str,
        reward: float,
        created_by: int,
        requirements: str = "",
        category_id: int = None,
        subcategory_id: int = None,
        target_count: int = 1,
        deadline: datetime = None,
        max_workers: int = 1
    ) -> str:
        """Создание нового задания"""
        task_id = hashlib.md5(f"{title}_{datetime.now()}_{secrets.token_hex(4)}".encode()).hexdigest()[:12]
        
        async with Database._pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO tasks (
                    task_id, title, description, task_type, target, 
                    reward, requirements, created_by, created_date,
                    category_id, subcategory_id, target_count, deadline, max_workers
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), $9, $10, $11, $12, $13)
                ''',
                task_id, title, description, task_type, target,
                reward, requirements, created_by, category_id, subcategory_id,
                target_count, deadline, max_workers
            )
            
            # Обновляем статистику
            await conn.execute(
                '''
                INSERT INTO stats (date, tasks_created)
                VALUES (CURRENT_DATE, 1)
                ON CONFLICT (date) DO UPDATE
                SET tasks_created = stats.tasks_created + 1
                '''
            )
            
        return task_id
    
    @staticmethod
    async def get_available_tasks(user_id: int = None, category_id: int = None) -> List[Dict]:
        """Получение списка доступных заданий"""
        async with Database._pool.acquire() as conn:
            query = '''
                SELECT t.*, c.name as category_name, s.name as subcategory_name,
                       c.icon as category_icon, s.icon as subcategory_icon
                FROM tasks t
                LEFT JOIN categories c ON t.category_id = c.id
                LEFT JOIN subcategories s ON t.subcategory_id = s.id
                WHERE t.available = TRUE 
                  AND t.active = TRUE 
                  AND t.taken_by IS NULL
                  AND t.completed = FALSE
                  AND t.current_workers < t.max_workers
            '''
            params = []
            
            if category_id:
                query += ' AND t.category_id = $1'
                params.append(category_id)
            
            query += ' ORDER BY t.created_date DESC LIMIT 50'
            
            tasks = await conn.fetch(query, *params)
            return [dict(task) for task in tasks]
    
    @staticmethod
    async def get_task(task_id: str) -> Optional[Dict]:
        """Получение задания по ID"""
        async with Database._pool.acquire() as conn:
            task = await conn.fetchrow(
                '''
                SELECT t.*, c.name as category_name, s.name as subcategory_name,
                       c.icon as category_icon, s.icon as subcategory_icon,
                       u.username as creator_username
                FROM tasks t
                LEFT JOIN categories c ON t.category_id = c.id
                LEFT JOIN subcategories s ON t.subcategory_id = s.id
                LEFT JOIN users u ON t.created_by = u.user_id
                WHERE t.task_id = $1
                ''',
                task_id
            )
            return dict(task) if task else None
    
    @staticmethod
    async def take_task(task_id: str, user_id: int) -> Tuple[bool, str, Optional[Dict]]:
        """Взятие задания пользователем"""
        async with Database.transaction() as conn:
            # Проверяем, доступно ли задание
            task = await conn.fetchrow(
                'SELECT * FROM tasks WHERE task_id = $1 FOR UPDATE',
                task_id
            )
            
            if not task:
                return False, "❌ Задание не найдено", None
            
            if not task['available'] or not task['active']:
                return False, "❌ Задание больше не доступно", None
            
            if task['taken_by']:
                return False, "❌ Задание уже взято другим пользователем", None
            
            if task['current_workers'] >= task['max_workers']:
                return False, "❌ Достигнут лимит исполнителей", None
            
            # Проверяем, не брал ли пользователь это задание раньше
            existing = await conn.fetchval(
                'SELECT 1 FROM user_tasks WHERE user_id = $1 AND task_id = $2',
                user_id, task_id
            )
            
            if existing:
                return False, "❌ Вы уже брали это задание", None
            
            # Назначаем задание
            await conn.execute(
                '''
                UPDATE tasks 
                SET taken_by = $2, 
                    available = FALSE, 
                    assigned_date = NOW(),
                    current_workers = current_workers + 1
                WHERE task_id = $1
                ''',
                task_id, user_id
            )
            
            # Добавляем запись в user_tasks
            await conn.execute(
                '''
                INSERT INTO user_tasks (user_id, task_id, status, taken_date)
                VALUES ($1, $2, 'taken', NOW())
                ''',
                user_id, task_id
            )
            
            return True, "✅ Задание успешно взято!", dict(task)
    
    @staticmethod
    async def complete_task(task_id: str, user_id: int, proof: str = "") -> Tuple[bool, str]:
        """Завершение задания и отправка на проверку админу"""
        async with Database.transaction() as conn:
            task = await conn.fetchrow(
                'SELECT * FROM tasks WHERE task_id = $1 AND taken_by = $2 FOR UPDATE',
                task_id, user_id
            )
            
            if not task:
                return False, "❌ Задание не найдено или не принадлежит вам"
            
            if task['completed']:
                return False, "❌ Задание уже выполнено"
            
            # Обновляем задание
            await conn.execute(
                '''
                UPDATE tasks 
                SET completed = FALSE, 
                    proof = $2,
                    active = FALSE
                WHERE task_id = $1
                ''',
                task_id, proof
            )
            
            # Обновляем запись пользователя
            await conn.execute(
                '''
                UPDATE user_tasks 
                SET status = 'verifying', 
                    completed_date = NOW(), 
                    proof = $3
                WHERE user_id = $2 AND task_id = $1
                ''',
                task_id, user_id, proof
            )
            
            # Отправляем уведомление в группу админов
            await TaskManager.notify_admin_about_completion(task_id, user_id, proof)
            
            return True, "✅ Задание отправлено на проверку администратору!"
    
    @staticmethod
    async def notify_admin_about_completion(task_id: str, user_id: int, proof: str):
        """Уведомление админов о завершении задания"""
        task = await TaskManager.get_task(task_id)
        user = await UserManager.get(user_id)
        
        if not task or not user:
            return
        
        notification_text = (
            f"📋 <b>НОВОЕ ВЫПОЛНЕННОЕ ЗАДАНИЕ</b>\n\n"
            f"👤 <b>Пользователь:</b> {user.get('first_name', 'Неизвестно')}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"📱 <b>Username:</b> @{user.get('username', 'Нет')}\n\n"
            f"📌 <b>Задание:</b> {task['title']}\n"
            f"📝 <b>Описание:</b> {task['description'][:100]}...\n"
            f"💰 <b>Награда:</b> {task['reward']} ₽\n"
            f"🆔 <b>Task ID:</b> <code>{task_id}</code>\n\n"
            f"📎 <b>Доказательство:</b>\n{proof}\n\n"
            f"<i>Используйте кнопки ниже для подтверждения или отклонения</i>"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_task_{task_id}_{user_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_task_{task_id}_{user_id}")
            ],
            [InlineKeyboardButton("👤 Профиль пользователя", callback_data=f"admin_user_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            # Отправляем в группу для отчетов
            if REPORT_GROUP:
                context = ContextTypes.DEFAULT_TYPE
                await context.bot.send_message(
                    chat_id=REPORT_GROUP,
                    text=notification_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления в группу: {e}")
    
    @staticmethod
    async def approve_task(task_id: str, user_id: int, admin_id: int) -> Tuple[bool, str]:
        """Подтверждение выполнения задания админом"""
        async with Database.transaction() as conn:
            task = await conn.fetchrow(
                'SELECT * FROM tasks WHERE task_id = $1 FOR UPDATE',
                task_id
            )
            
            if not task:
                return False, "❌ Задание не найдено"
            
            # Обновляем задание
            await conn.execute(
                '''
                UPDATE tasks 
                SET completed = TRUE, 
                    completed_date = NOW()
                WHERE task_id = $1
                ''',
                task_id
            )
            
            # Обновляем запись пользователя
            await conn.execute(
                '''
                UPDATE user_tasks 
                SET status = 'completed', 
                    admin_approved = TRUE,
                    approved_by = $3,
                    approved_date = NOW(),
                    earned = $4
                WHERE user_id = $2 AND task_id = $1
                ''',
                task_id, user_id, admin_id, task['reward']
            )
            
            # Обновляем баланс пользователя
            await conn.execute(
                '''
                UPDATE users 
                SET total_earned = total_earned + $2,
                    tasks_completed = tasks_completed + 1,
                    rating = rating + 10
                WHERE user_id = $1
                ''',
                user_id, task['reward']
            )
            
            # Обновляем статистику
            await conn.execute(
                '''
                INSERT INTO stats (date, tasks_completed, total_payout)
                VALUES (CURRENT_DATE, 1, $1)
                ON CONFLICT (date) DO UPDATE
                SET tasks_completed = stats.tasks_completed + 1,
                    total_payout = stats.total_payout + $1
                ''',
                task['reward']
            )
            
            return True, f"✅ Задание подтверждено! Пользователю начислено {task['reward']} ₽"
    
    @staticmethod
    async def reject_task(task_id: str, user_id: int, admin_id: int, reason: str) -> Tuple[bool, str]:
        """Отклонение выполнения задания"""
        async with Database.transaction() as conn:
            # Обновляем задание
            await conn.execute(
                '''
                UPDATE tasks 
                SET taken_by = NULL,
                    available = TRUE,
                    active = TRUE,
                    current_workers = current_workers - 1
                WHERE task_id = $1
                ''',
                task_id
            )
            
            # Обновляем запись пользователя
            await conn.execute(
                '''
                UPDATE user_tasks 
                SET status = 'cancelled',
                    rejection_reason = $3
                WHERE user_id = $2 AND task_id = $1
                ''',
                task_id, user_id, reason
            )
            
            return True, f"❌ Задание отклонено. Причина: {reason}"

class TrackingLinksManager:
    """Менеджер для работы с отслеживающими ссылками"""
    
    @staticmethod
    async def generate_link(user_id: int, task_id: str, task_title: str) -> str:
        """Генерация уникальной ссылки для отслеживания"""
        token = secrets.token_urlsafe(16)
        link_id = hashlib.md5(f"{user_id}_{task_id}_{token}_{datetime.now()}".encode()).hexdigest()[:16]
        
        async with Database._pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO tracking_links (link_id, user_id, task_id)
                VALUES ($1, $2, $3)
                ''',
                link_id, user_id, task_id
            )
        
        # Формируем ссылку
        return f"https://t.me/{BOT_USERNAME}?start=track_{link_id}"
    
    @staticmethod
    async def get_link(link_id: str) -> Optional[Dict]:
        """Получение информации о ссылке"""
        async with Database._pool.acquire() as conn:
            link = await conn.fetchrow(
                'SELECT * FROM tracking_links WHERE link_id = $1',
                link_id
            )
            return dict(link) if link else None
    
    @staticmethod
    async def increment_clicks(link_id: str, user_id: int = None) -> None:
        """Увеличение счетчика кликов"""
        async with Database._pool.acquire() as conn:
            # Получаем текущий список уникальных пользователей
            link = await conn.fetchrow(
                'SELECT unique_users FROM tracking_links WHERE link_id = $1',
                link_id
            )
            
            unique_users = link['unique_users'] if link else []
            is_unique = user_id and user_id not in unique_users
            
            if is_unique:
                unique_users.append(user_id)
            
            await conn.execute(
                '''
                UPDATE tracking_links 
                SET clicks = clicks + 1,
                    unique_users = $2,
                    last_click = NOW()
                WHERE link_id = $1
                ''',
                link_id, json.dumps(unique_users)
            )
            
            # Обновляем статистику
            await conn.execute(
                '''
                INSERT INTO stats (date, clicks)
                VALUES (CURRENT_DATE, 1)
                ON CONFLICT (date) DO UPDATE
                SET clicks = stats.clicks + 1
                '''
            )
    
    @staticmethod
    async def get_user_stats(user_id: int) -> Dict:
        """Статистика по ссылкам пользователя"""
        async with Database._pool.acquire() as conn:
            stats = await conn.fetchrow(
                '''
                SELECT 
                    COUNT(*) as total_links,
                    COALESCE(SUM(clicks), 0) as total_clicks,
                    COALESCE(SUM(conversions), 0) as total_conversions
                FROM tracking_links
                WHERE user_id = $1
                ''',
                user_id
            )
            
            return dict(stats) if stats else {
                "total_links": 0,
                "total_clicks": 0,
                "total_conversions": 0
            }

class PendingLinksManager:
    """Менеджер для работы с ожидающими ссылками"""
    
    @staticmethod
    async def create_pending(task_id: str, user_id: int, username: str, task_title: str, tracking_link: str) -> int:
        """Создание записи об ожидающей ссылке"""
        async with Database._pool.acquire() as conn:
            pending_id = await conn.fetchval(
                '''
                INSERT INTO pending_links (task_id, user_id, username, task_title, tracking_link)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                ''',
                task_id, user_id, username, task_title, tracking_link
            )
            return pending_id
    
    @staticmethod
    async def get_pending(pending_id: int) -> Optional[Dict]:
        """Получение ожидающей ссылки по ID"""
        async with Database._pool.acquire() as conn:
            pending = await conn.fetchrow(
                'SELECT * FROM pending_links WHERE id = $1 AND processed = FALSE',
                pending_id
            )
            return dict(pending) if pending else None
    
    @staticmethod
    async def get_unprocessed() -> List[Dict]:
        """Получение всех необработанных запросов"""
        async with Database._pool.acquire() as conn:
            pendings = await conn.fetch(
                '''
                SELECT * FROM pending_links 
                WHERE processed = FALSE 
                ORDER BY message_sent ASC
                '''
            )
            return [dict(p) for p in pendings]
    
    @staticmethod
    async def mark_processed(pending_id: int, processed_by: int, work_link: str = None) -> None:
        """Отметить ссылку как обработанную"""
        async with Database._pool.acquire() as conn:
            update_query = '''
                UPDATE pending_links 
                SET processed = TRUE, 
                    processed_by = $2, 
                    processed_date = NOW()
            '''
            params = [pending_id, processed_by]
            
            if work_link:
                update_query += ', work_link = $3'
                params.append(work_link)
            
            update_query += ' WHERE id = $1'
            
            await conn.execute(update_query, *params)

# ==================== КЛАВИАТУРЫ ====================

class Keyboards:
    """Класс для создания клавиатур"""
    
    @staticmethod
    def main_menu(user_is_admin: bool = False) -> InlineKeyboardMarkup:
        """Главное меню"""
        keyboard = [
            [InlineKeyboardButton("📋 Доступные задания", callback_data="available_tasks")],
            [InlineKeyboardButton("📊 Моя статистика", callback_data="my_stats")],
            [InlineKeyboardButton("👤 Профиль", callback_data="profile")],
            [InlineKeyboardButton("💰 Вывод средств", callback_data="withdraw")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        
        if user_is_admin:
            keyboard.append([InlineKeyboardButton("⚙️ Админ панель", callback_data="admin_panel")])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def admin_panel() -> InlineKeyboardMarkup:
        """Админ панель"""
        keyboard = [
            [InlineKeyboardButton("➕ Создать задание", callback_data="admin_create_task")],
            [InlineKeyboardButton("📋 Управление категориями", callback_data="admin_categories")],
            [InlineKeyboardButton("👥 Управление админами", callback_data="admin_manage_admins")],
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("⏳ Ожидающие ссылки", callback_data="admin_pending_links")],
            [InlineKeyboardButton("📝 На проверке", callback_data="admin_verifying_tasks")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def task_types() -> InlineKeyboardMarkup:
        """Типы заданий"""
        keyboard = [
            [InlineKeyboardButton("📢 Подписка на канал", callback_data=f"tasktype_{TaskType.CHANNEL_SUBSCRIBE}")],
            [InlineKeyboardButton("❤️ Лайк поста", callback_data=f"tasktype_{TaskType.LIKE}")],
            [InlineKeyboardButton("💬 Комментарий", callback_data=f"tasktype_{TaskType.COMMENT}")],
            [InlineKeyboardButton("🔄 Репост", callback_data=f"tasktype_{TaskType.REPOST}")],
            [InlineKeyboardButton("🤖 Запуск бота", callback_data=f"tasktype_{TaskType.BOT_START}")],
            [InlineKeyboardButton("👥 Вступление в группу", callback_data=f"tasktype_{TaskType.GROUP_JOIN}")],
            [InlineKeyboardButton("🌐 Посещение сайта", callback_data=f"tasktype_{TaskType.VISIT}")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def task_action(task_id: str, is_available: bool = True) -> InlineKeyboardMarkup:
        """Кнопки действий для задания"""
        keyboard = []
        
        if is_available:
            keyboard.append([InlineKeyboardButton("✅ Взять задание", callback_data=f"take_task_{task_id}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад к списку", callback_data="available_tasks")])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def back_button(callback_data: str = "back_to_main") -> InlineKeyboardMarkup:
        """Кнопка назад"""
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=callback_data)]]
        return InlineKeyboardMarkup(keyboard)

# ==================== ОСНОВНОЙ БОТ ====================

class TrafficBot:
    """Основной класс бота"""
    
    def __init__(self):
        self.application = None
        self.welcome_text = """
<b>🚀 Приветствуем, будущий трафер!</b>

Переходи по ссылке — мы покажем и научим, как действительно зарабатывать на трафике.

<b>❗️ Сразу обозначим:</b>
Мы работаем ТОЛЬКО с белым трафиком — честно, стабильно и без рисков.

<b>🔥 Вступая в нашу команду, ты получаешь:</b>
✅ готового бота для работы
✅ подробный и понятный мануал
✅ поддержку кураторов
✅ работу бок о бок с профессионалами
✅ практику, опыт и рост с первого дня

<i>Если хочешь развиваться и зарабатывать — тебе точно к нам 👇</i>
"""
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        args = context.args
        
        # Сохраняем пользователя
        db_user = await UserManager.get_or_create(
            user.id,
            user.username or "",
            user.first_name or "",
            user.last_name or ""
        )
        
        # Проверяем, не является ли это переходом по трекинговой ссылке
        if args and args[0].startswith("track_"):
            link_id = args[0][6:]  # Убираем "track_"
            await self.handle_tracking_link(update, context, link_id)
            return
        
        # Приветственное сообщение
        is_admin = await AdminManager.is_admin(user.id)
        
        await update.message.reply_text(
            self.welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=Keyboards.main_menu(is_admin)
        )
        
        # Отправляем приветственное сообщение с ссылкой на канал/группу
        if TASK_NOTIFICATION_GROUP:
            try:
                channel_link = TASK_NOTIFICATION_GROUP.replace('@', 'https://t.me/')
                await update.message.reply_text(
                    f"📢 <b>Наш канал с заданиями:</b> {channel_link}\n"
                    f"Подпишись, чтобы не пропустить новые задания!",
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False
                )
            except:
                pass
    
    async def handle_tracking_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE, link_id: str):
        """Обработка перехода по трекинговой ссылке"""
        user = update.effective_user
        
        # Получаем информацию о ссылке
        link = await TrackingLinksManager.get_link(link_id)
        
        if not link:
            await update.message.reply_text("❌ Ссылка недействительна или устарела")
            return
        
        # Сохраняем пользователя, перешедшего по ссылке
        await UserManager.get_or_create(
            user.id,
            user.username or "",
            user.first_name or "",
            user.last_name or ""
        )
        
        # Увеличиваем счетчик кликов
        await TrackingLinksManager.increment_clicks(link_id, user.id)
        
        # Получаем задание
        task = await TaskManager.get_task(link['task_id'])
        
        if task:
            await update.message.reply_text(
                f"✅ <b>Вы перешли по ссылке!</b>\n\n"
                f"📌 <b>Задание:</b> {task['title']}\n"
                f"👤 <b>Пригласил:</b> @{link.get('username', 'Пользователь')}\n\n"
                f"<i>Спасибо за переход! Теперь вы тоже можете зарабатывать с нами.</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=Keyboards.main_menu(False)
            )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
<b>❓ Помощь и часто задаваемые вопросы</b>

<b>📋 Как начать зарабатывать?</b>
1. Нажми "📋 Доступные задания"
2. Выбери интересующее задание
3. Нажми "✅ Взять задание"
4. Выполни требования задания
5. Отправь доказательство выполнения

<b>💰 Как выводятся средства?</b>
Минимальная сумма вывода: 100 ₽
Вывод производится на банковскую карту или криптокошелек

<b>📞 Поддержка</b>
По всем вопросам обращайтесь к @wedferfwewf

<b>⚡️ Полезные команды:</b>
/profile - Ваш профиль
/stats - Статистика
/tasks - Доступные задания
/referrals - Реферальная программа
"""
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
    
    async def profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Просмотр профиля"""
        user = update.effective_user
        stats = await UserManager.get_stats(user.id)
        db_user = await UserManager.get(user.id)
        
        profile_text = f"""
<b>👤 Ваш профиль</b>

<b>ID:</b> <code>{user.id}</code>
<b>Имя:</b> {user.first_name or 'Не указано'}
<b>Username:</b> @{user.username or 'Нет'}

<b>📊 Статистика:</b>
✅ Выполнено заданий: {stats['completed_count']}
📌 Активных заданий: {stats['active_count']}
⏳ На проверке: {stats['verifying_count']}
💰 Всего заработано: {stats['total_earned']} ₽
👥 Рефералов: {stats['referrals']}
⭐️ Рейтинг: {stats['rating']}

<b>🔗 Ваша реферальная ссылка:</b>
<code>https://t.me/{BOT_USERNAME}?start=ref_{user.id}</code>
"""
        keyboard = [
            [InlineKeyboardButton("📋 Мои задания", callback_data="my_tasks")],
            [InlineKeyboardButton("💰 Вывод средств", callback_data="withdraw")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(profile_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    
    async def available_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ доступных заданий"""
        query = update.callback_query
        await query.answer()
        
        # Получаем все категории
        categories = await CategoryManager.get_all_categories()
        
        if not categories:
            keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="available_tasks")]]
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📋 <b>Доступные задания</b>\n\n"
                "😕 Пока нет доступных заданий.\n"
                "Загляни позже или подпишись на @wedferfwewf",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            return
        
        # Создаем клавиатуру с категориями
        keyboard = []
        for cat in categories[:10]:  # Ограничиваем 10 категориями
            keyboard.append([
                InlineKeyboardButton(
                    f"{cat.get('icon', '📁')} {cat['name']}", 
                    callback_data=f"category_{cat['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("📋 Все задания", callback_data="all_tasks")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📋 <b>Доступные задания</b>\n\n"
            "Выберите категорию:",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def show_category_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ заданий по категории"""
        query = update.callback_query
        await query.answer()
        
        category_id = int(query.data.split('_')[1])
        
        # Получаем подкатегории
        subcategories = await CategoryManager.get_subcategories(category_id)
        
        if subcategories:
            # Показываем подкатегории
            keyboard = []
            for sub in subcategories[:10]:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{sub.get('icon', '📌')} {sub['name']}", 
                        callback_data=f"subcategory_{sub['id']}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("📋 Все задания категории", callback_data=f"category_tasks_{category_id}")])
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="available_tasks")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📋 <b>Выберите подкатегорию:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        else:
            # Показываем задания категории
            await self.show_tasks_list(query, context, category_id=category_id)
    
    async def show_tasks_list(self, query, context, category_id: int = None, subcategory_id: int = None):
        """Отображение списка заданий"""
        user_id = query.from_user.id
        
        # Получаем задания
        if subcategory_id:
            tasks = await TaskManager.get_available_tasks()
            tasks = [t for t in tasks if t.get('subcategory_id') == subcategory_id]
        elif category_id:
            tasks = await TaskManager.get_available_tasks(category_id=category_id)
        else:
            tasks = await TaskManager.get_available_tasks()
        
        if not tasks:
            await query.edit_message_text(
                "📋 <b>Задания</b>\n\n"
                "😕 В этой категории пока нет заданий.",
                parse_mode=ParseMode.HTML,
                reply_markup=Keyboards.back_button("available_tasks")
            )
            return
        
        # Показываем первое задание
        await self.show_task_detail(query, context, tasks[0]['task_id'], 0, tasks)
    
    async def show_task_detail(self, query, context, task_id: str, index: int, tasks: List[Dict]):
        """Отображение деталей задания"""
        task = next((t for t in tasks if t['task_id'] == task_id), None)
        
        if not task:
            return
        
        total_tasks = len(tasks)
        
        task_text = f"""
<b>📌 {task['title']}</b>

📝 <b>Описание:</b>
{task['description']}

🎯 <b>Цель:</b> {task['target']}
💰 <b>Награда:</b> {task['reward']} ₽
👥 <b>Исполнителей:</b> {task['current_workers']}/{task['max_workers']}
📊 <b>Выполнено:</b> {task.get('current_count', 0)}/{task.get('target_count', 1)}

📋 <b>Требования:</b>
{task.get('requirements', 'Нет')}

<b>Задание {index + 1} из {total_tasks}</b>
"""
        # Кнопки навигации
        keyboard = []
        
        nav_buttons = []
        if index > 0:
            nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"task_{tasks[index-1]['task_id']}_{index-1}"))
        if index < total_tasks - 1:
            nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"task_{tasks[index+1]['task_id']}_{index+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("✅ Взять задание", callback_data=f"take_task_{task['task_id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад к списку", callback_data="available_tasks")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            task_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def take_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Взятие задания пользователем"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        task_id = query.data.split('_')[2]
        
        # Проверяем, админ ли пользователь (админы не могут брать задания)
        is_admin = await AdminManager.is_admin(user_id)
        if is_admin and user_id != MAIN_ADMIN_ID:
            await query.edit_message_text(
                "❌ Администраторы не могут брать задания!",
                reply_markup=Keyboards.back_button("available_tasks")
            )
            return
        
        # Взятие задания
        success, message, task = await TaskManager.take_task(task_id, user_id)
        
        if success and task:
            # Генерируем трекинговую ссылку
            user = await UserManager.get(user_id)
            tracking_link = await TrackingLinksManager.generate_link(
                user_id, 
                task_id, 
                task['title']
            )
            
            # Сохраняем в ожидающие ссылки и отправляем уведомление админу
            pending_id = await PendingLinksManager.create_pending(
                task_id,
                user_id,
                user.get('username', ''),
                task['title'],
                tracking_link
            )
            
            # Отправляем уведомление в группу админов
            await self.notify_admin_about_task_taken(
                task, 
                user_id, 
                user.get('username', ''),
                tracking_link,
                pending_id
            )
            
            # Сообщаем пользователю
            await query.edit_message_text(
                f"{message}\n\n"
                f"📌 <b>Задание:</b> {task['title']}\n"
                f"💰 <b>Награда:</b> {task['reward']} ₽\n\n"
                f"<i>Администратор скоро выдаст вам специальную ссылку для работы. Ожидайте...</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=Keyboards.back_button("my_tasks")
            )
        else:
            await query.edit_message_text(
                message,
                reply_markup=Keyboards.back_button("available_tasks")
            )
    
async def notify_admin_about_task_taken(self, task: Dict, user_id: int, username: str, tracking_link: str, pending_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Уведомление админов о взятии задания"""
    notification_text = (
        f"🆕 <b>НОВОЕ ВЗЯТОЕ ЗАДАНИЕ</b>\n\n"
        f"👤 <b>Пользователь:</b> @{username or 'Нет username'}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
        f"📌 <b>Задание:</b> {task['title']}\n"
        f"📝 <b>Описание:</b> {task['description'][:100]}...\n"
        f"💰 <b>Награда:</b> {task['reward']} ₽\n"
        f"🆔 <b>Task ID:</b> <code>{task['task_id']}</code>\n\n"
        f"🔗 <b>Трекинговая ссылка пользователя:</b>\n"
        f"<code>{tracking_link}</code>\n\n"
        f"<i>Выдайте пользователю рабочую ссылку, нажав кнопку ниже</i>"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔗 Выдать рабочую ссылку", callback_data=f"set_work_link_{pending_id}_{task['task_id']}_{user_id}")],
        [InlineKeyboardButton("👤 Профиль пользователя", callback_data=f"admin_user_{user_id}")],
        [InlineKeyboardButton("❌ Отменить задание", callback_data=f"cancel_task_{task['task_id']}_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if TASK_NOTIFICATION_GROUP:
            await context.bot.send_message(
                chat_id=TASK_NOTIFICATION_GROUP,
                text=notification_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления в группу {TASK_NOTIFICATION_GROUP}: {e}")
        
        # Отправляем главному админу в личку
        await context.bot.send_message(
            chat_id=MAIN_ADMIN_ID,
            text=notification_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

async def notify_admin_about_completion(self, task_id: str, user_id: int, proof: str, context: ContextTypes.DEFAULT_TYPE):
    """Уведомление админов о завершении задания"""
    task = await TaskManager.get_task(task_id)
    user = await UserManager.get(user_id)
    
    if not task or not user:
        return
    
    notification_text = (
        f"📋 <b>НОВОЕ ВЫПОЛНЕННОЕ ЗАДАНИЕ</b>\n\n"
        f"👤 <b>Пользователь:</b> {user.get('first_name', 'Неизвестно')}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"📱 <b>Username:</b> @{user.get('username', 'Нет')}\n\n"
        f"📌 <b>Задание:</b> {task['title']}\n"
        f"📝 <b>Описание:</b> {task['description'][:100]}...\n"
        f"💰 <b>Награда:</b> {task['reward']} ₽\n"
        f"🆔 <b>Task ID:</b> <code>{task_id}</code>\n\n"
        f"📎 <b>Доказательство:</b>\n{proof}\n\n"
        f"<i>Используйте кнопки ниже для подтверждения или отклонения</i>"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_task_{task_id}_{user_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_task_{task_id}_{user_id}")
        ],
        [InlineKeyboardButton("👤 Профиль пользователя", callback_data=f"admin_user_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        # Отправляем в группу для отчетов
        if REPORT_GROUP:
            await context.bot.send_message(
                chat_id=REPORT_GROUP,
                text=notification_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления в группу: {e}")

        
    async def set_work_link_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик выдачи рабочей ссылки админом"""
        query = update.callback_query
        await query.answer()
        
        admin_id = query.from_user.id
        
        # Проверяем, является ли пользователь админом
        is_admin = await AdminManager.is_admin(admin_id)
        if not is_admin:
            await query.edit_message_text("❌ У вас нет прав администратора")
            return
        
        # Разбираем callback_data
        parts = query.data.split('_')
        pending_id = int(parts[3])
        task_id = parts[4]
        user_id = int(parts[5])
        
        # Сохраняем данные в контексте для ConversationHandler
        context.user_data['pending_id'] = pending_id
        context.user_data['task_id'] = task_id
        context.user_data['user_id'] = user_id
        
        await query.edit_message_text(
            "🔗 <b>Введите рабочую ссылку для пользователя</b>\n\n"
            "Это может быть:\n"
            "• Ссылка на канал/группу\n"
            "• Ссылка на пост\n"
            "• Ссылка на бота\n"
            "• Любая другая ссылка для выполнения задания\n\n"
            "<i>Отправьте ссылку одним сообщением</i>",
            parse_mode=ParseMode.HTML
        )
        
        return ConversationState.ADMIN_SET_WORK_LINK
    
    async def save_work_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение рабочей ссылки"""
        admin_id = update.effective_user.id
        work_link = update.message.text
        
        # Проверяем, что это ссылка
        if not work_link.startswith(('http://', 'https://', 't.me/', '@')):
            await update.message.reply_text(
                "❌ Пожалуйста, отправьте корректную ссылку!\n"
                "Примеры:\n"
                "• https://t.me/channel\n"
                "• @channel_name\n"
                "• https://example.com"
            )
            return ConversationState.ADMIN_SET_WORK_LINK
        
        pending_id = context.user_data.get('pending_id')
        task_id = context.user_data.get('task_id')
        user_id = context.user_data.get('user_id')
        
        if not all([pending_id, task_id, user_id]):
            await update.message.reply_text("❌ Ошибка: данные не найдены. Начните заново.")
            return ConversationHandler.END
        
        # Получаем информацию о pending запросе
        pending = await PendingLinksManager.get_pending(pending_id)
        
        if not pending:
            await update.message.reply_text("❌ Запрос не найден или уже обработан")
            return ConversationHandler.END
        
        # Обновляем задание с рабочей ссылкой
        await TaskManager.set_work_link(task_id, work_link)
        
        # Отмечаем как обработанное
        await PendingLinksManager.mark_processed(pending_id, admin_id, work_link)
        
        # Отправляем ссылку пользователю
        task = await TaskManager.get_task(task_id)
        
        user_notification = (
            f"✅ <b>Администратор выдал вам ссылку для задания!</b>\n\n"
            f"📌 <b>Задание:</b> {task['title']}\n"
            f"💰 <b>Награда:</b> {task['reward']} ₽\n\n"
            f"🔗 <b>Ваша рабочая ссылка:</b>\n"
            f"{work_link}\n\n"
            f"<b>Инструкция:</b>\n"
            f"1. Перейдите по ссылке\n"
            f"2. Выполните требования задания\n"
            f"3. Нажмите кнопку '✅ Задание выполнено'\n"
            f"4. Отправьте доказательство\n\n"
            f"<i>Ваша трекинг-ссылка для приглашений:</i>\n"
            f"<code>{pending['tracking_link']}</code>"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Задание выполнено", callback_data=f"complete_task_{task_id}")],
            [InlineKeyboardButton("📊 Моя статистика", callback_data="my_stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=user_notification,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
        
        await update.message.reply_text(
            f"✅ Ссылка успешно отправлена пользователю!\n\n"
            f"📌 Задание: {task['title']}\n"
            f"🔗 Ссылка: {work_link}",
            reply_markup=Keyboards.admin_panel()
        )
        
        # Очищаем данные
        context.user_data.clear()
        
        return ConversationHandler.END
    
    async def complete_task_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик завершения задания"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        task_id = query.data.split('_')[2]
        
        # Проверяем, что пользователь взял это задание
        task = await TaskManager.get_task(task_id)
        
        if not task or task['taken_by'] != user_id:
            await query.edit_message_text(
                "❌ Задание не найдено или не принадлежит вам",
                reply_markup=Keyboards.back_button("my_tasks")
            )
            return
        
        # Сохраняем в контексте
        context.user_data['complete_task_id'] = task_id
        
        await query.edit_message_text(
            f"📎 <b>Отправка доказательства выполнения</b>\n\n"
            f"📌 <b>Задание:</b> {task['title']}\n\n"
            f"<b>Пожалуйста, отправьте доказательство выполнения:</b>\n"
            f"• Скриншот выполнения\n"
            f"• Ссылку на выполненное действие\n"
            f"• Любое другое подтверждение\n\n"
            f"<i>Вы можете отправить текст, фото или файл</i>",
            parse_mode=ParseMode.HTML
        )
        
        return ConversationState.USER_PROOF
    
    async def save_proof(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение доказательства выполнения"""
        user_id = update.effective_user.id
        task_id = context.user_data.get('complete_task_id')
        
        if not task_id:
            await update.message.reply_text("❌ Ошибка: задание не найдено")
            return ConversationHandler.END
        
        # Получаем доказательство
        if update.message.photo:
            # Если отправили фото
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            proof = f"Фото: {file.file_id}"
        elif update.message.text:
            proof = update.message.text
        elif update.message.document:
            doc = update.message.document
            proof = f"Файл: {doc.file_name} ({doc.file_id})"
        else:
            proof = "Доказательство отправлено"
        
        # Завершаем задание
        success, message = await TaskManager.complete_task(task_id, user_id, proof)
        
        if success:
            await update.message.reply_text(
                message + "\n\n✅ Администратор проверит ваше задание в ближайшее время.",
                reply_markup=Keyboards.main_menu(False)
            )
        else:
            await update.message.reply_text(
                message,
                reply_markup=Keyboards.main_menu(False)
            )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    async def approve_task_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Подтверждение задания админом"""
        query = update.callback_query
        await query.answer()
        
        admin_id = query.from_user.id
        
        # Проверяем права админа
        is_admin = await AdminManager.is_admin(admin_id)
        if not is_admin:
            await query.edit_message_text("❌ У вас нет прав администратора")
            return
        
        # Разбираем callback_data
        parts = query.data.split('_')
        task_id = parts[2]
        user_id = int(parts[3])
        
        # Подтверждаем задание
        success, message = await TaskManager.approve_task(task_id, user_id, admin_id)
        
        if success:
            # Обновляем сообщение
            await query.edit_message_text(
                query.message.text + "\n\n✅ <b>ЗАДАНИЕ ПОДТВЕРЖДЕНО АДМИНИСТРАТОРОМ</b>",
                parse_mode=ParseMode.HTML
            )
            
            # Уведомляем пользователя
            task = await TaskManager.get_task(task_id)
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"✅ <b>Ваше задание подтверждено!</b>\n\n"
                         f"📌 {task['title']}\n"
                         f"💰 Начислено: {task['reward']} ₽\n\n"
                         f"Продолжайте выполнять задания и зарабатывать! 🚀",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")
        else:
            await query.edit_message_text(
                query.message.text + f"\n\n❌ <b>Ошибка:</b> {message}",
                parse_mode=ParseMode.HTML
            )
    
    async def reject_task_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отклонение задания админом"""
        query = update.callback_query
        await query.answer()
        
        admin_id = query.from_user.id
        
        # Проверяем права админа
        is_admin = await AdminManager.is_admin(admin_id)
        if not is_admin:
            await query.edit_message_text("❌ У вас нет прав администратора")
            return
        
        # Разбираем callback_data
        parts = query.data.split('_')
        task_id = parts[2]
        user_id = int(parts[3])
        
        # Сохраняем в контексте
        context.user_data['reject_task_id'] = task_id
        context.user_data['reject_user_id'] = user_id
        
        await query.edit_message_text(
            query.message.text + "\n\n❌ <b>Введите причину отклонения:</b>",
            parse_mode=ParseMode.HTML
        )
        
        return "reject_reason"
    
    async def save_reject_reason(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение причины отклонения"""
        admin_id = update.effective_user.id
        reason = update.message.text
        
        task_id = context.user_data.get('reject_task_id')
        user_id = context.user_data.get('reject_user_id')
        
        if not task_id or not user_id:
            await update.message.reply_text("❌ Ошибка: данные не найдены")
            return ConversationHandler.END
        
        # Отклоняем задание
        success, message = await TaskManager.reject_task(task_id, user_id, admin_id, reason)
        
        if success:
            await update.message.reply_text(f"✅ Задание отклонено. Причина: {reason}")
            
            # Уведомляем пользователя
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"❌ <b>Ваше задание отклонено</b>\n\n"
                         f"📌 <b>Причина:</b> {reason}\n\n"
                         f"Пожалуйста, ознакомьтесь с требованиями и попробуйте снова.",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить пользователя {user_id}: {e}")
        else:
            await update.message.reply_text(f"❌ Ошибка: {message}")
        
        context.user_data.clear()
        return ConversationHandler.END
    
    async def my_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика пользователя"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        stats = await UserManager.get_stats(user_id)
        tracking_stats = await TrackingLinksManager.get_user_stats(user_id)
        
        stats_text = f"""
<b>📊 Ваша статистика</b>

✅ <b>Выполнено заданий:</b> {stats['completed_count']}
📌 <b>В работе:</b> {stats['active_count']}
⏳ <b>На проверке:</b> {stats['verifying_count']}
💰 <b>Заработано:</b> {stats['total_earned']} ₽

<b>🔗 Трекинг ссылки:</b>
📎 Всего ссылок: {tracking_stats['total_links']}
👥 Переходов: {tracking_stats['total_clicks']}
🔄 Конверсий: {tracking_stats['total_conversions']}

<b>👥 Реферальная программа:</b>
👤 Приглашено: {stats['referrals']}
⭐️ Бонус за рефералов: {stats['referrals'] * 10} ₽

<i>Приглашайте друзей и получайте 10% от их заработка!</i>
"""
        keyboard = [
            [InlineKeyboardButton("📋 Мои задания", callback_data="my_tasks")],
            [InlineKeyboardButton("🔗 Мои ссылки", callback_data="my_links")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            stats_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def my_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Список заданий пользователя"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        async with Database._pool.acquire() as conn:
            # Активные задания
            active_tasks = await conn.fetch(
                '''
                SELECT t.*, ut.status, ut.taken_date
                FROM tasks t
                JOIN user_tasks ut ON t.task_id = ut.task_id
                WHERE ut.user_id = $1 AND ut.status = 'taken'
                ORDER BY ut.taken_date DESC
                ''',
                user_id
            )
            
            # Задания на проверке
            verifying_tasks = await conn.fetch(
                '''
                SELECT t.*, ut.status, ut.completed_date
                FROM tasks t
                JOIN user_tasks ut ON t.task_id = ut.task_id
                WHERE ut.user_id = $1 AND ut.status = 'verifying'
                ORDER BY ut.completed_date DESC
                ''',
                user_id
            )
            
            # Выполненные задания
            completed_tasks = await conn.fetch(
                '''
                SELECT t.*, ut.completed_date, ut.earned
                FROM tasks t
                JOIN user_tasks ut ON t.task_id = ut.task_id
                WHERE ut.user_id = $1 AND ut.status = 'completed'
                ORDER BY ut.completed_date DESC
                LIMIT 10
                ''',
                user_id
            )
        
        text = "<b>📋 Мои задания</b>\n\n"
        
        if active_tasks:
            text += "<b>📌 В работе:</b>\n"
            for task in active_tasks[:3]:
                text += f"• {task['title']} - {task['reward']} ₽\n"
            if len(active_tasks) > 3:
                text += f"  ...и еще {len(active_tasks) - 3}\n"
            text += "\n"
        
        if verifying_tasks:
            text += "<b>⏳ На проверке:</b>\n"
            for task in verifying_tasks[:3]:
                text += f"• {task['title']} - {task['reward']} ₽\n"
            if len(verifying_tasks) > 3:
                text += f"  ...и еще {len(verifying_tasks) - 3}\n"
            text += "\n"
        
        if completed_tasks:
            text += "<b>✅ Выполнено:</b>\n"
            total_earned = sum(task['earned'] for task in completed_tasks)
            for task in completed_tasks[:5]:
                text += f"• {task['title']} - +{task['earned']} ₽\n"
            text += f"\n<b>💰 Всего заработано:</b> {total_earned} ₽\n"
        
        if not any([active_tasks, verifying_tasks, completed_tasks]):
            text += "😕 У вас пока нет заданий.\n"
            text += "Нажмите '📋 Доступные задания', чтобы начать зарабатывать!"
        
        keyboard = [
            [InlineKeyboardButton("📋 Доступные задания", callback_data="available_tasks")],
            [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    # ==================== АДМИН ПАНЕЛЬ ====================
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Админ панель"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        is_admin = await AdminManager.is_admin(user_id)
        
        if not is_admin:
            await query.edit_message_text(
                "❌ У вас нет доступа к админ панели.",
                reply_markup=Keyboards.back_button("back_to_main")
            )
            return
        
        await query.edit_message_text(
            "<b>⚙️ Административная панель</b>\n\n"
            "Выберите действие:",
            parse_mode=ParseMode.HTML,
            reply_markup=Keyboards.admin_panel()
        )
    
    async def admin_manage_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Управление администраторами"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        is_main_admin = await AdminManager.is_main_admin(user_id)
        
        if not is_main_admin:
            await query.edit_message_text(
                "❌ Только главный администратор может управлять админами.",
                reply_markup=Keyboards.back_button("admin_panel")
            )
            return
        
        # Получаем список админов
        admins = await AdminManager.get_all_admins()
        
        text = "<b>👥 Управление администраторами</b>\n\n"
        text += f"👑 <b>Главный админ:</b> <code>{MAIN_ADMIN_ID}</code>\n\n"
        
        if len(admins) > 1:
            text += "<b>Администраторы:</b>\n"
            for admin in admins:
                if admin['user_id'] != MAIN_ADMIN_ID:
                    user_link = f"@{admin['username']}" if admin['username'] else f"ID: {admin['user_id']}"
                    added_by = f" (добавлен: {admin.get('added_by', 'неизвестно')})"
                    text += f"• {user_link}{added_by}\n"
        else:
            text += "Нет других администраторов.\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить админа", callback_data="admin_add")],
            [InlineKeyboardButton("➖ Удалить админа", callback_data="admin_remove")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def admin_add_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало добавления админа"""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "➕ <b>Добавление администратора</b>\n\n"
            "Введите <b>ID пользователя</b>, которого хотите сделать администратором:\n\n"
            "<i>Чтобы узнать ID, пользователь может отправить любое сообщение боту @userinfobot</i>",
            parse_mode=ParseMode.HTML
        )
        
        return ConversationState.ADMIN_ADD_USER_ID
    
    async def admin_add_save(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение нового админа"""
        admin_id = update.effective_user.id
        target_id_text = update.message.text.strip()
        
        try:
            target_id = int(target_id_text)
        except ValueError:
            await update.message.reply_text(
                "❌ Пожалуйста, введите корректный числовой ID пользователя!"
            )
            return ConversationState.ADMIN_ADD_USER_ID
        
        if target_id == MAIN_ADMIN_ID:
            await update.message.reply_text("❌ Главный администратор уже имеет все права.")
            return ConversationHandler.END
        
        # Добавляем админа
        success, message = await AdminManager.add_admin(target_id, admin_id)
        
        if success:
            # Уведомляем нового админа
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text="✅ <b>Поздравляем!</b>\n\n"
                         "Вам назначены права администратора в боте.\n"
                         "Теперь вам доступна админ-панель.",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить нового админа {target_id}: {e}")
        
        await update.message.reply_text(
            message,
            reply_markup=Keyboards.admin_panel()
        )
        
        return ConversationHandler.END
    
    async def admin_remove_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало удаления админа"""
        query = update.callback_query
        await query.answer()
        
        # Получаем список админов
        admins = await AdminManager.get_all_admins()
        other_admins = [a for a in admins if a['user_id'] != MAIN_ADMIN_ID]
        
        if not other_admins:
            await query.edit_message_text(
                "❌ Нет других администраторов для удаления.",
                reply_markup=Keyboards.back_button("admin_manage_admins")
            )
            return ConversationHandler.END
        
        text = "➖ <b>Удаление администратора</b>\n\n"
        text += "Выберите администратора для удаления:\n\n"
        
        keyboard = []
        for admin in other_admins[:10]:  # Ограничиваем 10
            name = f"@{admin['username']}" if admin['username'] else f"ID: {admin['user_id']}"
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ {name}", 
                    callback_data=f"admin_remove_confirm_{admin['user_id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_manage_admins")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        
        return ConversationHandler.END
    
    async def admin_remove_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Подтверждение удаления админа"""
        query = update.callback_query
        await query.answer()
        
        target_id = int(query.data.split('_')[3])
        
        # Удаляем админа
        success, message = await AdminManager.remove_admin(target_id)
        
        if success:
            # Уведомляем удаленного админа
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text="⚠️ <b>Ваши права администратора были отозваны.</b>",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
        
        await query.edit_message_text(
            message,
            reply_markup=Keyboards.back_button("admin_manage_admins")
        )
    
    async def admin_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Управление категориями"""
        query = update.callback_query
        await query.answer()
        
        categories = await CategoryManager.get_all_categories(active_only=False)
        
        text = "<b>📁 Управление категориями</b>\n\n"
        
        if categories:
            text += "Существующие категории:\n"
            for cat in categories:
                status = "✅" if cat['is_active'] else "❌"
                text += f"{status} {cat.get('icon', '📁')} <b>{cat['name']}</b>\n"
                text += f"   ID: {cat['id']} | {cat.get('description', 'Нет описания')[:50]}\n"
        else:
            text += "Нет созданных категорий.\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ Создать категорию", callback_data="admin_create_category")],
            [InlineKeyboardButton("➕ Создать подкатегорию", callback_data="admin_create_subcategory")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def admin_create_category_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало создания категории"""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "➕ <b>Создание новой категории</b>\n\n"
            "Введите <b>название категории</b>:\n\n"
            "<i>Например: Социальные сети, Криптовалюта, Игры и т.д.</i>",
            parse_mode=ParseMode.HTML
        )
        
        return ConversationState.ADMIN_CREATE_CATEGORY
    
    async def admin_create_category_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение названия категории"""
        name = update.message.text.strip()
        context.user_data['category_name'] = name
        
        await update.message.reply_text(
            "📝 Введите <b>описание категории</b>:\n\n"
            "<i>Краткое описание того, какие задания будут в этой категории</i>",
            parse_mode=ParseMode.HTML
        )
        
        return ConversationState.ADMIN_CREATE_CATEGORY + 1
    
    async def admin_create_category_desc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение описания категории"""
        description = update.message.text.strip()
        context.user_data['category_description'] = description
        
        await update.message.reply_text(
            "🎨 Введите <b>иконку</b> для категории (один символ или эмодзи):\n\n"
            "<i>Например: 📱, 💰, 🎮, 🌐</i>\n\n"
            "Или отправьте '-' для использования стандартной иконки",
            parse_mode=ParseMode.HTML
        )
        
        return ConversationState.ADMIN_CREATE_CATEGORY + 2
    
    async def admin_create_category_icon(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение иконки и создание категории"""
        icon = update.message.text.strip()
        if icon == '-':
            icon = '📁'
        
        name = context.user_data.get('category_name')
        description = context.user_data.get('category_description')
        admin_id = update.effective_user.id
        
        if not name or not description:
            await update.message.reply_text("❌ Ошибка: данные не найдены. Начните заново.")
            return ConversationHandler.END
        
        # Создаем категорию
        category = await CategoryManager.create_category(name, description, icon, admin_id)
        
        if category:
            await update.message.reply_text(
                f"✅ <b>Категория успешно создана!</b>\n\n"
                f"{icon} <b>{name}</b>\n"
                f"📝 {description}\n"
                f"🆔 ID: {category['id']}",
                parse_mode=ParseMode.HTML,
                reply_markup=Keyboards.admin_panel()
            )
        else:
            await update.message.reply_text(
                "❌ Категория с таким названием уже существует!",
                reply_markup=Keyboards.admin_panel()
            )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    async def admin_create_subcategory_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало создания подкатегории"""
        query = update.callback_query
        await query.answer()
        
        categories = await CategoryManager.get_all_categories()
        
        if not categories:
            await query.edit_message_text(
                "❌ Сначала создайте хотя бы одну категорию!",
                reply_markup=Keyboards.back_button("admin_categories")
            )
            return ConversationHandler.END
        
        text = "➕ <b>Создание подкатегории</b>\n\n"
        text += "Выберите категорию:\n\n"
        
        keyboard = []
        for cat in categories[:10]:
            keyboard.append([
                InlineKeyboardButton(
                    f"{cat.get('icon', '📁')} {cat['name']}", 
                    callback_data=f"subcat_category_{cat['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_categories")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
        
        return ConversationState.ADMIN_CREATE_SUBCATEGORY
    
    async def admin_create_subcategory_choose(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор категории для подкатегории"""
        query = update.callback_query
        await query.answer()
        
        category_id = int(query.data.split('_')[2])
        context.user_data['subcat_category_id'] = category_id
        
        await query.edit_message_text(
            "➕ <b>Создание подкатегории</b>\n\n"
            "Введите <b>название подкатегории</b>:",
            parse_mode=ParseMode.HTML
        )
        
        return ConversationState.ADMIN_CREATE_SUBCATEGORY + 1
    
    async def admin_create_subcategory_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение названия подкатегории"""
        name = update.message.text.strip()
        context.user_data['subcat_name'] = name
        
        await update.message.reply_text(
            "📝 Введите <b>описание подкатегории</b>:",
            parse_mode=ParseMode.HTML
        )
        
        return ConversationState.ADMIN_CREATE_SUBCATEGORY + 2
    
    async def admin_create_subcategory_desc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение описания подкатегории"""
        description = update.message.text.strip()
        context.user_data['subcat_description'] = description
        
        await update.message.reply_text(
            "🎨 Введите <b>иконку</b> для подкатегории:\n\n"
            "Или отправьте '-' для использования стандартной иконки",
            parse_mode=ParseMode.HTML
        )
        
        return ConversationState.ADMIN_CREATE_SUBCATEGORY + 3
    
    async def admin_create_subcategory_icon(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение иконки и создание подкатегории"""
        icon = update.message.text.strip()
        if icon == '-':
            icon = '📌'
        
        category_id = context.user_data.get('subcat_category_id')
        name = context.user_data.get('subcat_name')
        description = context.user_data.get('subcat_description')
        admin_id = update.effective_user.id
        
        if not all([category_id, name, description]):
            await update.message.reply_text("❌ Ошибка: данные не найдены. Начните заново.")
            return ConversationHandler.END
        
        # Создаем подкатегорию
        subcategory = await CategoryManager.create_subcategory(
            category_id, name, description, icon, admin_id
        )
        
        if subcategory:
            await update.message.reply_text(
                f"✅ <b>Подкатегория успешно создана!</b>\n\n"
                f"{icon} <b>{name}</b>\n"
                f"📝 {description}\n"
                f"🆔 ID: {subcategory['id']}",
                parse_mode=ParseMode.HTML,
                reply_markup=Keyboards.admin_panel()
            )
        else:
            await update.message.reply_text(
                "❌ Подкатегория с таким названием уже существует в этой категории!",
                reply_markup=Keyboards.admin_panel()
            )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    async def admin_create_task_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало создания задания"""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "➕ <b>Создание нового задания</b>\n\n"
            "<b>Шаг 1 из 7:</b>\n"
            "Введите <b>название задания</b>:\n\n"
            "<i>Краткое, понятное название (до 100 символов)</i>",
            parse_mode=ParseMode.HTML
        )
        
        return ConversationState.ADMIN_CREATE_TASK_TITLE
    
    async def admin_create_task_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение названия задания"""
        title = update.message.text.strip()
        if len(title) > 100:
            await update.message.reply_text(
                "❌ Название слишком длинное! Максимум 100 символов.\n"
                "Попробуйте еще раз:"
            )
            return ConversationState.ADMIN_CREATE_TASK_TITLE
        
        context.user_data['task_title'] = title
        
        await update.message.reply_text(
            "✅ Название сохранено!\n\n"
            "<b>Шаг 2 из 7:</b>\n"
            "Введите <b>описание задания</b>:\n\n"
            "<i>Подробно опишите, что нужно сделать</i>",
            parse_mode=ParseMode.HTML
        )
        
        return ConversationState.ADMIN_CREATE_TASK_DESC
    
    async def admin_create_task_desc(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение описания задания"""
        description = update.message.text.strip()
        context.user_data['task_description'] = description
        
        await update.message.reply_text(
            "✅ Описание сохранено!\n\n"
            "<b>Шаг 3 из 7:</b>\n"
            "Выберите <b>тип задания</b>:",
            parse_mode=ParseMode.HTML,
            reply_markup=Keyboards.task_types()
        )
        
        return ConversationState.ADMIN_CREATE_TASK_TYPE
    
    async def admin_create_task_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение типа задания"""
        query = update.callback_query
        await query.answer()
        
        task_type = query.data.split('_')[1]
        context.user_data['task_type'] = task_type
        
        await query.edit_message_text(
            "✅ Тип задания сохранен!\n\n"
            "<b>Шаг 4 из 7:</b>\n"
            "Введите <b>цель задания</b>:\n\n"
            "<i>Например:</i>\n"
            "• Ссылка на канал/пост\n"
            "• Username бота\n"
            "• URL сайта",
            parse_mode=ParseMode.HTML
        )
        
        return ConversationState.ADMIN_CREATE_TASK_TARGET
    
    async def admin_create_task_target(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение цели задания"""
        target = update.message.text.strip()
        context.user_data['task_target'] = target
        
        await update.message.reply_text(
            "✅ Цель сохранена!\n\n"
            "<b>Шаг 5 из 7:</b>\n"
            "Введите <b>вознаграждение</b> в рублях:\n\n"
            "<i>Только число (например: 50, 100, 200)</i>",
            parse_mode=ParseMode.HTML
        )
        
        return ConversationState.ADMIN_CREATE_TASK_REWARD
    
    async def admin_create_task_reward(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение вознаграждения"""
        try:
            reward = float(update.message.text.strip())
            if reward <= 0:
                raise ValueError()
            context.user_data['task_reward'] = reward
        except ValueError:
            await update.message.reply_text(
                "❌ Пожалуйста, введите положительное число!"
            )
            return ConversationState.ADMIN_CREATE_TASK_REWARD
        
        await update.message.reply_text(
            "✅ Вознаграждение сохранено!\n\n"
            "<b>Шаг 6 из 7:</b>\n"
            "Введите <b>требования</b> к исполнителю:\n\n"
            "<i>Например: возраст 18+, подписка на канал и т.д.</i>\n"
            "Или отправьте '-' если требований нет",
            parse_mode=ParseMode.HTML
        )
        
        return ConversationState.ADMIN_CREATE_TASK_REQUIREMENTS
    
    async def admin_create_task_requirements(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохранение требований"""
        requirements = update.message.text.strip()
        if requirements == '-':
            requirements = ""
        
        context.user_data['task_requirements'] = requirements
        
        # Получаем категории
        categories = await CategoryManager.get_all_categories()
        
        if categories:
            keyboard = []
            for cat in categories[:10]:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{cat.get('icon', '📁')} {cat['name']}", 
                        callback_data=f"task_category_{cat['id']}"
                    )
                ])
            keyboard.append([InlineKeyboardButton("⏭ Пропустить", callback_data="task_category_skip")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "✅ Требования сохранены!\n\n"
                "<b>Шаг 7 из 7:</b>\n"
                "Выберите <b>категорию</b> для задания:",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        else:
            # Создаем задание без категории
            await self.finish_task_creation(update, context, None, None)
        
        return ConversationState.ADMIN_CREATE_TASK_CATEGORY
    
    async def admin_create_task_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор категории для задания"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "task_category_skip":
            # Создаем задание без категории
            await self.finish_task_creation(query, context, None, None)
            return ConversationHandler.END
        
        category_id = int(query.data.split('_')[2])
        context.user_data['task_category_id'] = category_id
        
        # Получаем подкатегории
        subcategories = await CategoryManager.get_subcategories(category_id)
        
        if subcategories:
            keyboard = []
            for sub in subcategories[:10]:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{sub.get('icon', '📌')} {sub['name']}", 
                        callback_data=f"task_subcategory_{sub['id']}"
                    )
                ])
            keyboard.append([InlineKeyboardButton("⏭ Пропустить", callback_data="task_subcategory_skip")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "✅ Категория выбрана!\n\n"
                "Выберите <b>подкатегорию</b>:",
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            
            return ConversationState.ADMIN_CREATE_TASK_SUBCATEGORY
        else:
            # Создаем задание без подкатегории
            await self.finish_task_creation(query, context, category_id, None)
            return ConversationHandler.END
    
    async def admin_create_task_subcategory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор подкатегории для задания"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "task_subcategory_skip":
            subcategory_id = None
        else:
            subcategory_id = int(query.data.split('_')[2])
        
        category_id = context.user_data.get('task_category_id')
        
        await self.finish_task_creation(query, context, category_id, subcategory_id)
        return ConversationHandler.END
    
    async def finish_task_creation(self, update_or_query, context, category_id, subcategory_id):
        """Завершение создания задания"""
        # Получаем данные из контекста
        title = context.user_data.get('task_title')
        description = context.user_data.get('task_description')
        task_type = context.user_data.get('task_type')
        target = context.user_data.get('task_target')
        reward = context.user_data.get('task_reward')
        requirements = context.user_data.get('task_requirements', '')
        admin_id = update_or_query.from_user.id
        
        if not all([title, description, task_type, target, reward]):
            error_text = "❌ Ошибка: не все данные заполнены. Начните создание заново."
            
            if hasattr(update_or_query, 'edit_message_text'):
                await update_or_query.edit_message_text(error_text)
            else:
                await update_or_query.message.reply_text(error_text)
            
            context.user_data.clear()
            return
        
        # Создаем задание
        task_id = await TaskManager.create_task(
            title, description, task_type, target, reward,
            admin_id, requirements, category_id, subcategory_id
        )
        
        success_text = (
            f"✅ <b>Задание успешно создано!</b>\n\n"
            f"📌 <b>{title}</b>\n"
            f"💰 Награда: {reward} ₽\n"
            f"🆔 ID: <code>{task_id}</code>\n\n"
            f"Задание появится в списке доступных."
        )
        
        keyboard = [
            [InlineKeyboardButton("📋 Создать еще", callback_data="admin_create_task")],
            [InlineKeyboardButton("⚙️ Админ панель", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(update_or_query, 'edit_message_text'):
            await update_or_query.edit_message_text(
                success_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        else:
            await update_or_query.message.reply_text(
                success_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
        
        # Отправляем уведомление в группу
        try:
            if TASK_NOTIFICATION_GROUP:
                notification = (
                    f"🆕 <b>НОВОЕ ЗАДАНИЕ</b>\n\n"
                    f"📌 <b>{title}</b>\n"
                    f"📝 {description[:200]}...\n"
                    f"💰 Награда: {reward} ₽\n\n"
                    f"👉 Открыть бота: @{BOT_USERNAME}"
                )
                await context.bot.send_message(
                    chat_id=TASK_NOTIFICATION_GROUP,
                    text=notification,
                    parse_mode=ParseMode.HTML
                )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о новом задании: {e}")
        
        context.user_data.clear()
    
    async def admin_pending_links(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Просмотр ожидающих ссылок"""
        query = update.callback_query
        await query.answer()
        
        pendings = await PendingLinksManager.get_unprocessed()
        
        if not pendings:
            await query.edit_message_text(
                "⏳ <b>Ожидающие ссылки</b>\n\n"
                "Нет необработанных запросов.",
                parse_mode=ParseMode.HTML,
                reply_markup=Keyboards.back_button("admin_panel")
            )
            return
        
        text = f"<b>⏳ Ожидающие ссылки ({len(pendings)})</b>\n\n"
        
        for i, pending in enumerate(pendings[:5], 1):
            text += f"{i}. <b>{pending['task_title'][:50]}</b>\n"
            text += f"   👤 @{pending['username'] or 'Нет username'}\n"
            text += f"   🆔 ID: <code>{pending['user_id']}</code>\n"
            text += f"   🕐 {pending['message_sent'].strftime('%d.%m %H:%M')}\n"
            text += f"   [Выдать ссылку](callback:set_work_link_{pending['id']})\n\n"
        
        keyboard = [
            [InlineKeyboardButton("🔗 Выдать первую ссылку", callback_data=f"set_work_link_{pendings[0]['id']}_{pendings[0]['task_id']}_{pendings[0]['user_id']}")],
            [InlineKeyboardButton("🔄 Обновить", callback_data="admin_pending_links")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    
    async def admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Просмотр статистики"""
        query = update.callback_query
        await query.answer()
        
        async with Database._pool.acquire() as conn:
            # Общая статистика
            total_users = await conn.fetchval('SELECT COUNT(*) FROM users')
            total_tasks = await conn.fetchval('SELECT COUNT(*) FROM tasks')
            completed_tasks = await conn.fetchval('SELECT COUNT(*) FROM tasks WHERE completed = TRUE') or 0
            active_tasks = await conn.fetchval('SELECT COUNT(*) FROM tasks WHERE taken_by IS NOT NULL AND completed = FALSE') or 0
            
            # Статистика за сегодня
            today_stats = await conn.fetchrow(
                'SELECT * FROM stats WHERE date = CURRENT_DATE'
            )
            
            # Общая сумма выплат
            total_payout = await conn.fetchval('SELECT COALESCE(SUM(reward), 0) FROM tasks WHERE completed = TRUE') or 0
            
            # Топ пользователей
            top_users = await conn.fetch(
                '''
                SELECT user_id, username, total_earned, tasks_completed
                FROM users
                WHERE total_earned > 0
                ORDER BY total_earned DESC
                LIMIT 5
                '''
            )
        
        text = f"""
<b>📊 ГЛОБАЛЬНАЯ СТАТИСТИКА</b>

<b>👥 Пользователи:</b>
Всего: {total_users}
Новых сегодня: {today_stats['new_users'] if today_stats else 0}

<b>📋 Задания:</b>
Всего создано: {total_tasks}
Выполнено: {completed_tasks}
В работе: {active_tasks}
Создано сегодня: {today_stats['tasks_created'] if today_stats else 0}
Выполнено сегодня: {today_stats['tasks_completed'] if today_stats else 0}

<b>💰 Финансы:</b>
Всего выплачено: {total_payout:.2f} ₽
Выплачено сегодня: {today_stats['total_payout'] if today_stats else 0:.2f} ₽

<b>🔗 Клики по ссылкам:</b>
Всего: {today_stats['clicks'] if today_stats else 0} сегодня

<b>🏆 Топ исполнителей:</b>
"""
        
        for i, user in enumerate(top_users, 1):
            username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
            text += f"{i}. {username} - {user['total_earned']} ₽ ({user['tasks_completed']} зад.)\n"
        
        keyboard = [
            [InlineKeyboardButton("📊 Детальная статистика", callback_data="admin_detailed_stats")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def back_to_main(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Возврат в главное меню"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        is_admin = await AdminManager.is_admin(user_id)
        
        await query.edit_message_text(
            self.welcome_text,
            parse_mode=ParseMode.HTML,
            reply_markup=Keyboards.main_menu(is_admin)
        )
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Ошибка: {context.error}")
        
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "❌ Произошла ошибка. Пожалуйста, попробуйте позже."
                )
        except:
            pass
    
    def setup_handlers(self, application: Application):
        """Настройка обработчиков"""
        
        # ==================== КОМАНДЫ ====================
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("profile", self.profile))
        
        # ==================== CONVERSATION HANDLERS ====================
        
        # Добавление админа
        add_admin_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.admin_add_start, pattern="^admin_add$")],
            states={
                ConversationState.ADMIN_ADD_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_add_save)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)],
            allow_reentry=True
        )
        application.add_handler(add_admin_conv)
        
        # Удаление админа
        remove_admin_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.admin_remove_start, pattern="^admin_remove$")],
            states={},
            fallbacks=[],
            allow_reentry=True
        )
        application.add_handler(remove_admin_conv)
        application.add_handler(CallbackQueryHandler(self.admin_remove_confirm, pattern="^admin_remove_confirm_"))
        
        # Создание категории
        create_category_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.admin_create_category_start, pattern="^admin_create_category$")],
            states={
                ConversationState.ADMIN_CREATE_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_create_category_name)],
                ConversationState.ADMIN_CREATE_CATEGORY + 1: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_create_category_desc)],
                ConversationState.ADMIN_CREATE_CATEGORY + 2: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_create_category_icon)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)],
            allow_reentry=True
        )
        application.add_handler(create_category_conv)
        
        # Создание подкатегории
        create_subcategory_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.admin_create_subcategory_start, pattern="^admin_create_subcategory$")],
            states={
                ConversationState.ADMIN_CREATE_SUBCATEGORY: [CallbackQueryHandler(self.admin_create_subcategory_choose, pattern="^subcat_category_")],
                ConversationState.ADMIN_CREATE_SUBCATEGORY + 1: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_create_subcategory_name)],
                ConversationState.ADMIN_CREATE_SUBCATEGORY + 2: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_create_subcategory_desc)],
                ConversationState.ADMIN_CREATE_SUBCATEGORY + 3: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_create_subcategory_icon)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)],
            allow_reentry=True
        )
        application.add_handler(create_subcategory_conv)
        
        # Создание задания
        create_task_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.admin_create_task_start, pattern="^admin_create_task$")],
            states={
                ConversationState.ADMIN_CREATE_TASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_create_task_title)],
                ConversationState.ADMIN_CREATE_TASK_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_create_task_desc)],
                ConversationState.ADMIN_CREATE_TASK_TYPE: [CallbackQueryHandler(self.admin_create_task_type, pattern="^tasktype_")],
                ConversationState.ADMIN_CREATE_TASK_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_create_task_target)],
                ConversationState.ADMIN_CREATE_TASK_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_create_task_reward)],
                ConversationState.ADMIN_CREATE_TASK_REQUIREMENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.admin_create_task_requirements)],
                ConversationState.ADMIN_CREATE_TASK_CATEGORY: [CallbackQueryHandler(self.admin_create_task_category, pattern="^task_category_")],
                ConversationState.ADMIN_CREATE_TASK_SUBCATEGORY: [CallbackQueryHandler(self.admin_create_task_subcategory, pattern="^task_subcategory_")],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)],
            allow_reentry=True,
            per_chat=True
        )
        application.add_handler(create_task_conv)
        
        # Выдача рабочей ссылки
        set_work_link_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.set_work_link_handler, pattern="^set_work_link_")],
            states={
                ConversationState.ADMIN_SET_WORK_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.save_work_link)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)],
            allow_reentry=True
        )
        application.add_handler(set_work_link_conv)
        
        # Отправка доказательства
        complete_task_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.complete_task_handler, pattern="^complete_task_")],
            states={
                ConversationState.USER_PROOF: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.save_proof),
                    MessageHandler(filters.PHOTO, self.save_proof),
                    MessageHandler(filters.Document.ALL, self.save_proof)
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)],
            allow_reentry=True
        )
        application.add_handler(complete_task_conv)
        
        # Отклонение задания с причиной
        reject_reason_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.reject_task_handler, pattern="^reject_task_")],
            states={
                "reject_reason": [MessageHandler(filters.TEXT & ~filters.COMMAND, self.save_reject_reason)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)],
            allow_reentry=True
        )
        application.add_handler(reject_reason_conv)
        
        # ==================== CALLBACK QUERY HANDLERS ====================
        application.add_handler(CallbackQueryHandler(self.back_to_main, pattern="^back_to_main$"))
        application.add_handler(CallbackQueryHandler(self.available_tasks, pattern="^available_tasks$"))
        application.add_handler(CallbackQueryHandler(self.my_stats, pattern="^my_stats$"))
        application.add_handler(CallbackQueryHandler(self.profile, pattern="^profile$"))
        application.add_handler(CallbackQueryHandler(self.my_tasks, pattern="^my_tasks$"))
        application.add_handler(CallbackQueryHandler(self.admin_panel, pattern="^admin_panel$"))
        application.add_handler(CallbackQueryHandler(self.admin_manage_admins, pattern="^admin_manage_admins$"))
        application.add_handler(CallbackQueryHandler(self.admin_categories, pattern="^admin_categories$"))
        application.add_handler(CallbackQueryHandler(self.admin_pending_links, pattern="^admin_pending_links$"))
        application.add_handler(CallbackQueryHandler(self.admin_stats, pattern="^admin_stats$"))
        application.add_handler(CallbackQueryHandler(self.show_category_tasks, pattern="^category_"))
        application.add_handler(CallbackQueryHandler(self.take_task, pattern="^take_task_"))
        application.add_handler(CallbackQueryHandler(self.approve_task_handler, pattern="^approve_task_"))
        
        # ==================== ERROR HANDLER ====================
        application.add_error_handler(self.error_handler)
    
    async def cancel_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена текущего диалога"""
        user_id = update.effective_user.id
        is_admin = await AdminManager.is_admin(user_id)
        
        await update.message.reply_text(
            "❌ Действие отменено.",
            reply_markup=Keyboards.main_menu(is_admin)
        )
        
        context.user_data.clear()
        return ConversationHandler.END

# ==================== ЗАПУСК БОТА ====================

async def post_init(application: Application):
    """Действия после инициализации бота"""
    # Устанавливаем команды бота
    commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("profile", "Мой профиль"),
        BotCommand("tasks", "Доступные задания"),
        BotCommand("help", "Помощь"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("✅ Команды бота установлены")

def main():
    """Главная функция"""
    if not TOKEN:
        logger.error("❌ Токен бота не найден! Установите BOT_TOKEN в переменных окружения.")
        return
    
    try:
        # Инициализируем базу данных
        asyncio.run(Database.init_db())
        
        # Создаем приложение
        application = Application.builder().token(TOKEN).post_init(post_init).build()
        
        # Создаем экземпляр бота и настраиваем обработчики
        bot = TrafficBot()
        bot.setup_handlers(application)
        
        # Запускаем бота
        logger.info("🚀 Бот запущен и готов к работе!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except AttributeError as e:
        logger.error(f"❌ Ошибка совместимости: {e}")
        logger.error("Установите python-telegram-bot версии 20.7:")
        logger.error("pip install python-telegram-bot==20.7")
    except Exception as e:
        logger.error(f"❌ Неизвестная ошибка: {e}")
    finally:
        # Закрываем соединение с БД
        asyncio.run(Database.close_pool())

if __name__ == '__main__':
    main()