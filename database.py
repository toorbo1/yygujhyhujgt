import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from contextlib import asynccontextmanager
import asyncpg
import json
import hashlib
import secrets

logger = logging.getLogger(__name__)


class Database:
    """Пул подключений к PostgreSQL"""
    _pool = None

    @classmethod
    async def init_pool(cls):
        """Инициализация пула и создание таблиц"""
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            database_url = 'postgresql://postgres:password@localhost:5432/bot_db'

        try:
            cls._pool = await asyncpg.create_pool(database_url)
            logger.info("✅ Подключение к PostgreSQL установлено")
            await cls._create_tables()
            return cls._pool
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к PostgreSQL: {e}")
            raise

    @classmethod
    async def _create_tables(cls):
        """Создание всех необходимых таблиц"""
        async with cls._pool.acquire() as conn:
            # ---- Категории (блоки и подблоки) ----
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    parent_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
                    created_by BIGINT NOT NULL,
                    created_date TIMESTAMP DEFAULT NOW()
                )
            ''')

            # ---- Пользователи ----
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    joined_date TIMESTAMP DEFAULT NOW(),
                    is_admin BOOLEAN DEFAULT FALSE,
                    added_by BIGINT,
                    permissions JSONB DEFAULT '[]',
                    total_earned DECIMAL(10,2) DEFAULT 0,
                    rating INTEGER DEFAULT 0,
                    completed_tasks INTEGER DEFAULT 0
                )
            ''')

            # ---- Задания ----
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    target_type TEXT,      -- 'channel', 'post', 'link'
                    target TEXT,           -- ссылка или username
                    reward DECIMAL(10,2) NOT NULL,
                    requirements TEXT,
                    created_by BIGINT NOT NULL,
                    created_date TIMESTAMP DEFAULT NOW(),
                    active BOOLEAN DEFAULT TRUE,
                    available BOOLEAN DEFAULT TRUE,
                    taken_by BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
                    assigned_date TIMESTAMP,
                    work_link TEXT,
                    completed BOOLEAN DEFAULT FALSE,
                    completed_date TIMESTAMP,
                    proof TEXT
                )
            ''')

            # ---- Задания, взятые пользователями ----
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_tasks (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                    status TEXT DEFAULT 'active',   -- active, completed, cancelled
                    taken_date TIMESTAMP DEFAULT NOW(),
                    completed_date TIMESTAMP,
                    earned DECIMAL(10,2),
                    UNIQUE(user_id, task_id)
                )
            ''')

            # ---- Отслеживающие ссылки (для рефералов / приглашений) ----
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tracking_links (
                    link_id TEXT PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                    created TIMESTAMP DEFAULT NOW(),
                    clicks INTEGER DEFAULT 0,
                    conversions INTEGER DEFAULT 0,
                    active BOOLEAN DEFAULT TRUE
                )
            ''')

            # ---- Ожидающие ссылки (когда пользователь взял задание, но админ ещё не выдал рабочую ссылку) ----
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS pending_links (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(task_id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    username TEXT,
                    task_title TEXT,
                    message_sent TIMESTAMP DEFAULT NOW(),
                    tracking_link TEXT,
                    processed BOOLEAN DEFAULT FALSE
                )
            ''')

            # ---- Статистика (ежедневная) ----
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS stats (
                    id SERIAL PRIMARY KEY,
                    date DATE UNIQUE DEFAULT CURRENT_DATE,
                    new_users INTEGER DEFAULT 0,
                    tasks_completed INTEGER DEFAULT 0,
                    total_payout DECIMAL(10,2) DEFAULT 0,
                    clicks INTEGER DEFAULT 0
                )
            ''')

            # Индексы
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_available ON tasks(available, active)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_user_tasks_user ON user_tasks(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_tracking_links_user ON tracking_links(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_pending_unprocessed ON pending_links(processed)')
            logger.info("✅ Таблицы созданы/проверены")

    @classmethod
    async def close_pool(cls):
        if cls._pool:
            await cls._pool.close()
            logger.info("✅ Пул закрыт")

    @classmethod
    @asynccontextmanager
    async def transaction(cls):
        async with cls._pool.acquire() as conn:
            async with conn.transaction():
                yield conn


# ==================== МЕНЕДЖЕРЫ ====================

class UserManager:
    @staticmethod
    async def get_or_create(user_id: int, username: str = "", first_name: str = "") -> dict:
        async with Database._pool.acquire() as conn:
            user = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
            if not user:
                await conn.execute(
                    'INSERT INTO users (user_id, username, first_name) VALUES ($1, $2, $3)',
                    user_id, username, first_name
                )
                # Обновляем статистику
                await conn.execute('''
                    INSERT INTO stats (date, new_users) VALUES (CURRENT_DATE, 1)
                    ON CONFLICT (date) DO UPDATE SET new_users = stats.new_users + 1
                ''')
                user = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
            return dict(user)

    @staticmethod
    async def get(user_id: int) -> Optional[dict]:
        async with Database._pool.acquire() as conn:
            user = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
            return dict(user) if user else None

    @staticmethod
    async def update(user_id: int, **kwargs) -> bool:
        async with Database._pool.acquire() as conn:
            set_clause = ', '.join(f"{k} = ${i+2}" for i, k in enumerate(kwargs))
            query = f"UPDATE users SET {set_clause} WHERE user_id = $1"
            await conn.execute(query, user_id, *kwargs.values())
            return True

    @staticmethod
    async def get_stats(user_id: int) -> dict:
        async with Database._pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'completed') as completed,
                    COUNT(*) FILTER (WHERE status = 'active') as active,
                    COALESCE(SUM(earned), 0) as total_earned
                FROM user_tasks WHERE user_id = $1
            ''', user_id)
            completed = row['completed'] or 0
            return {
                'completed_count': completed,
                'active_count': row['active'] or 0,
                'total_earned': float(row['total_earned']),
                'rating': completed * 10
            }


class AdminManager:
    MAIN_ADMIN_ID = int(os.environ.get('MAIN_ADMIN_ID', '8358009538'))

    @staticmethod
    async def is_admin(user_id: int) -> bool:
        if user_id == AdminManager.MAIN_ADMIN_ID:
            return True
        async with Database._pool.acquire() as conn:
            val = await conn.fetchval('SELECT is_admin FROM users WHERE user_id = $1', user_id)
            return bool(val)

    @staticmethod
    async def is_main_admin(user_id: int) -> bool:
        return user_id == AdminManager.MAIN_ADMIN_ID

    @staticmethod
    async def add_admin(user_id: int, username: str = "", added_by: int = None) -> bool:
        async with Database.transaction() as conn:
            await UserManager.get_or_create(user_id, username, "")
            await conn.execute(
                'UPDATE users SET is_admin = TRUE, added_by = $2 WHERE user_id = $1',
                user_id, added_by or AdminManager.MAIN_ADMIN_ID
            )
            return True

    @staticmethod
    async def remove_admin(user_id: int) -> bool:
        if user_id == AdminManager.MAIN_ADMIN_ID:
            return False
        async with Database._pool.acquire() as conn:
            await conn.execute('UPDATE users SET is_admin = FALSE WHERE user_id = $1', user_id)
            return True

    @staticmethod
    async def get_all_admins() -> List[dict]:
        async with Database._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT * FROM users 
                WHERE is_admin = TRUE OR user_id = $1
            ''', AdminManager.MAIN_ADMIN_ID)
            return [dict(r) for r in rows]


class CategoryManager:
    @staticmethod
    async def create(name: str, parent_id: Optional[int], created_by: int) -> int:
        async with Database._pool.acquire() as conn:
            row = await conn.fetchrow(
                'INSERT INTO categories (name, parent_id, created_by) VALUES ($1, $2, $3) RETURNING id',
                name, parent_id, created_by
            )
            return row['id']

    @staticmethod
    async def get_all() -> List[dict]:
        async with Database._pool.acquire() as conn:
            rows = await conn.fetch('SELECT * FROM categories ORDER BY parent_id NULLS FIRST, id')
            return [dict(r) for r in rows]

    @staticmethod
    async def get_children(parent_id: Optional[int] = None) -> List[dict]:
        async with Database._pool.acquire() as conn:
            if parent_id is None:
                rows = await conn.fetch('SELECT * FROM categories WHERE parent_id IS NULL ORDER BY id')
            else:
                rows = await conn.fetch('SELECT * FROM categories WHERE parent_id = $1 ORDER BY id', parent_id)
            return [dict(r) for r in rows]

    @staticmethod
    async def delete(category_id: int) -> bool:
        async with Database._pool.acquire() as conn:
            # Проверяем, есть ли подкатегории
            children = await conn.fetchval('SELECT COUNT(*) FROM categories WHERE parent_id = $1', category_id)
            if children > 0:
                return False
            await conn.execute('DELETE FROM categories WHERE id = $1', category_id)
            return True

    @staticmethod
    async def get_by_id(category_id: int) -> Optional[dict]:
        async with Database._pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM categories WHERE id = $1', category_id)
            return dict(row) if row else None


class TaskManager:
    @staticmethod
    async def create(
        title: str,
        description: str,
        target_type: str,
        target: str,
        reward: float,
        created_by: int,
        category_id: Optional[int] = None,
        requirements: str = ""
    ) -> str:
        task_id = hashlib.md5(f"{title}_{datetime.now()}_{secrets.token_hex(4)}".encode()).hexdigest()[:8]
        async with Database._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO tasks 
                    (task_id, category_id, title, description, target_type, target, reward, requirements, created_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ''', task_id, category_id, title, description, target_type, target, reward, requirements, created_by)
        return task_id

    @staticmethod
    async def get_available(category_id: Optional[int] = None) -> List[dict]:
        async with Database._pool.acquire() as conn:
            query = '''
                SELECT * FROM tasks 
                WHERE available = TRUE AND active = TRUE AND taken_by IS NULL
            '''
            args = []
            if category_id is not None:
                query += " AND category_id = $1"
                args.append(category_id)
            query += " ORDER BY created_date DESC"
            rows = await conn.fetch(query, *args)
            return [dict(r) for r in rows]

    @staticmethod
    async def get_by_id(task_id: str) -> Optional[dict]:
        async with Database._pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM tasks WHERE task_id = $1', task_id)
            return dict(row) if row else None

    @staticmethod
    async def assign(task_id: str, user_id: int) -> bool:
        async with Database.transaction() as conn:
            task = await conn.fetchrow('SELECT * FROM tasks WHERE task_id = $1 FOR UPDATE', task_id)
            if not task or task['taken_by'] or not task['available']:
                return False
            await conn.execute(
                'UPDATE tasks SET taken_by = $2, available = FALSE, assigned_date = NOW() WHERE task_id = $1',
                task_id, user_id
            )
            await conn.execute(
                'INSERT INTO user_tasks (user_id, task_id) VALUES ($1, $2)',
                user_id, task_id
            )
            return True

    @staticmethod
    async def set_work_link(task_id: str, link: str) -> bool:
        async with Database._pool.acquire() as conn:
            await conn.execute('UPDATE tasks SET work_link = $1 WHERE task_id = $2', link, task_id)
            return True

    @staticmethod
    async def complete(task_id: str, user_id: int, proof: str = "") -> bool:
        async with Database.transaction() as conn:
            task = await conn.fetchrow(
                'SELECT * FROM tasks WHERE task_id = $1 AND taken_by = $2 FOR UPDATE',
                task_id, user_id
            )
            if not task:
                return False
            await conn.execute(
                'UPDATE tasks SET completed = TRUE, completed_date = NOW(), proof = $2, active = FALSE WHERE task_id = $1',
                task_id, proof
            )
            await conn.execute(
                'UPDATE user_tasks SET status = $2, completed_date = NOW(), earned = $3 WHERE user_id = $4 AND task_id = $1',
                task_id, 'completed', task['reward'], user_id
            )
            await conn.execute(
                'UPDATE users SET total_earned = total_earned + $2, completed_tasks = completed_tasks + 1 WHERE user_id = $1',
                user_id, task['reward']
            )
            await conn.execute('''
                INSERT INTO stats (date, tasks_completed, total_payout) 
                VALUES (CURRENT_DATE, 1, $1)
                ON CONFLICT (date) DO UPDATE SET 
                    tasks_completed = stats.tasks_completed + 1,
                    total_payout = stats.total_payout + $1
            ''', task['reward'])
            return True

    @staticmethod
    async def get_user_tasks(user_id: int, status: Optional[str] = None) -> List[dict]:
        async with Database._pool.acquire() as conn:
            query = '''
                SELECT t.*, ut.status, ut.taken_date, ut.earned 
                FROM tasks t
                JOIN user_tasks ut ON t.task_id = ut.task_id
                WHERE ut.user_id = $1
            '''
            args = [user_id]
            if status:
                query += " AND ut.status = $2"
                args.append(status)
            query += " ORDER BY ut.taken_date DESC"
            rows = await conn.fetch(query, *args)
            return [dict(r) for r in rows]

    @staticmethod
    async def get_pending_links() -> List[dict]:
        async with Database._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT p.*, t.title, t.reward, u.username as user_username
                FROM pending_links p
                JOIN tasks t ON p.task_id = t.task_id
                JOIN users u ON p.user_id = u.user_id
                WHERE p.processed = FALSE
                ORDER BY p.message_sent ASC
            ''')
            return [dict(r) for r in rows]


class TrackingManager:
    @staticmethod
    async def generate_link(user_id: int, task_id: str) -> str:
        link_id = secrets.token_urlsafe(8)
        async with Database._pool.acquire() as conn:
            await conn.execute(
                'INSERT INTO tracking_links (link_id, user_id, task_id) VALUES ($1, $2, $3)',
                link_id, user_id, task_id
            )
        bot_username = os.environ.get('BOT_USERNAME', 'TrafficWorkeee_bot')
        return f"https://t.me/{bot_username}?start={link_id}"

    @staticmethod
    async def get_link(link_id: str) -> Optional[dict]:
        async with Database._pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM tracking_links WHERE link_id = $1', link_id)
            return dict(row) if row else None

    @staticmethod
    async def increment_clicks(link_id: str) -> None:
        async with Database.transaction() as conn:
            await conn.execute('UPDATE tracking_links SET clicks = clicks + 1 WHERE link_id = $1', link_id)
            await conn.execute('''
                INSERT INTO stats (date, clicks) VALUES (CURRENT_DATE, 1)
                ON CONFLICT (date) DO UPDATE SET clicks = stats.clicks + 1
            ''')


class PendingManager:
    @staticmethod
    async def save(task_id: str, user_id: int, username: str, task_title: str, tracking_link: str) -> None:
        async with Database._pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO pending_links (task_id, user_id, username, task_title, tracking_link)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (task_id) DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    username = EXCLUDED.username,
                    task_title = EXCLUDED.task_title,
                    message_sent = NOW(),
                    tracking_link = EXCLUDED.tracking_link,
                    processed = FALSE
            ''', task_id, user_id, username, task_title, tracking_link)

    @staticmethod
    async def get(task_id: str) -> Optional[dict]:
        async with Database._pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM pending_links WHERE task_id = $1 AND processed = FALSE',
                task_id
            )
            return dict(row) if row else None

    @staticmethod
    async def mark_processed(task_id: str) -> None:
        async with Database._pool.acquire() as conn:
            await conn.execute('UPDATE pending_links SET processed = TRUE WHERE task_id = $1', task_id)

    @staticmethod
    async def delete(task_id: str) -> None:
        async with Database._pool.acquire() as conn:
            await conn.execute('DELETE FROM pending_links WHERE task_id = $1', task_id)


class StatsManager:
    @staticmethod
    async def get_global() -> dict:
        async with Database._pool.acquire() as conn:
            total_users = await conn.fetchval('SELECT COUNT(*) FROM users')
            total_tasks = await conn.fetchval('SELECT COUNT(*) FROM tasks')
            completed_tasks = await conn.fetchval('SELECT COUNT(*) FROM tasks WHERE completed = TRUE') or 0
            total_payout = await conn.fetchval('SELECT COALESCE(SUM(reward), 0) FROM tasks WHERE completed = TRUE') or 0
            pending_links = await conn.fetchval('SELECT COUNT(*) FROM pending_links WHERE processed = FALSE') or 0
            active_tasks = await conn.fetchval('SELECT COUNT(*) FROM tasks WHERE taken_by IS NOT NULL AND completed = FALSE') or 0
            return {
                'total_users': total_users,
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'total_payout': float(total_payout),
                'pending_links': pending_links,
                'active_tasks': active_tasks
            }

    @staticmethod
    async def get_daily(days: int = 7) -> List[dict]:
        async with Database._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT * FROM stats 
                WHERE date >= CURRENT_DATE - $1::integer
                ORDER BY date DESC
            ''', days)
            return [dict(r) for r in rows]