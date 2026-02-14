# database.py (полная версия с поддержкой частичного взятия заданий)
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
        """Создание всех необходимых таблиц с проверкой и добавлением недостающих колонок"""
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
            # Добавляем parent_id, если его нет (для старых таблиц)
            try:
                await conn.execute('ALTER TABLE categories ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES categories(id) ON DELETE CASCADE')
                logger.info("✅ Колонка parent_id в categories проверена/добавлена")
            except Exception as e:
                logger.warning(f"Не удалось добавить parent_id в categories: {e}")

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
            # Таблица запросов на подтверждение выполнения задания
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS completion_requests (
                    id SERIAL PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    request_date TIMESTAMP DEFAULT NOW(),
                    status TEXT DEFAULT 'pending',   -- pending, approved, rejected
                    admin_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
                    processed_date TIMESTAMP,
                    UNIQUE(task_id, user_id, status)  -- можно один активный запрос на пару
                )
            ''')
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS payment_awaiting (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                    request_id INTEGER REFERENCES completion_requests(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    status TEXT DEFAULT 'waiting'
                )
            ''')
            # ---- Задания (добавлены новые колонки для многочастности) ----
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    target_type TEXT,
                    target TEXT,
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
                    proof TEXT,
                    -- новые поля для многочастных заданий
                    total_quantity INTEGER DEFAULT 1,
                    remaining_quantity INTEGER DEFAULT 1,
                    price_per_unit DECIMAL(10,2),
                    available_quantities TEXT  -- JSON список доступных объёмов
                )
            ''')

            # Добавляем недостающие колонки в tasks (для совместимости со старыми базами)
            try:
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS target_type TEXT')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS target TEXT')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS requirements TEXT')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS work_link TEXT')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS proof TEXT')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS available BOOLEAN DEFAULT TRUE')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS taken_by BIGINT REFERENCES users(user_id) ON DELETE SET NULL')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS assigned_date TIMESTAMP')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS completed BOOLEAN DEFAULT FALSE')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS completed_date TIMESTAMP')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS total_quantity INTEGER DEFAULT 1')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS remaining_quantity INTEGER DEFAULT 1')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS price_per_unit DECIMAL(10,2)')
                await conn.execute('ALTER TABLE tasks ADD COLUMN IF NOT EXISTS available_quantities TEXT')
                logger.info("✅ Недостающие колонки в tasks проверены/добавлены")
            except Exception as e:
                logger.warning(f"Не удалось добавить колонки в tasks: {e}")

            # ---- Задания, взятые пользователями (добавлено taken_quantity) ----
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_tasks (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                    status TEXT DEFAULT 'active',
                    taken_date TIMESTAMP DEFAULT NOW(),
                    completed_date TIMESTAMP,
                    earned DECIMAL(10,2),
                    taken_quantity INTEGER DEFAULT 1,  -- сколько единиц взято
                    UNIQUE(user_id, task_id)
                )
            ''')
            # Добавляем taken_quantity, если нет
            try:
                await conn.execute('ALTER TABLE user_tasks ADD COLUMN IF NOT EXISTS taken_quantity INTEGER DEFAULT 1')
            except Exception as e:
                logger.warning(f"Не удалось добавить taken_quantity в user_tasks: {e}")

            # ---- Отслеживающие ссылки ----
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

            # ---- Ожидающие ссылки ----
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

            # ---- Статистика ----
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
                await conn.execute('''
                    INSERT INTO stats (date, new_users) VALUES (CURRENT_DATE, 1)
                    ON CONFLICT (date) DO UPDATE SET new_users = stats.new_users + 1
                ''')
                user = await conn.fetchrow('SELECT * FROM users WHERE user_id = $1', user_id)
            else:
                # Обновляем username/first_name, если они изменились
                await conn.execute(
                    'UPDATE users SET username = $2, first_name = $3 WHERE user_id = $1',
                    user_id, username, first_name
                )
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

    @staticmethod
    async def get_all_user_ids() -> List[int]:
        """Возвращает список ID всех пользователей (для рассылки)"""
        async with Database._pool.acquire() as conn:
            rows = await conn.fetch('SELECT user_id FROM users')
            return [row['user_id'] for row in rows]


class AdminManager:
    MAIN_ADMIN_ID = int(os.environ.get('MAIN_ADMIN_ID', '8358009538'))

    @staticmethod
    async def is_admin(user_id: int) -> bool:
        # Главный админ всегда админ
        if user_id == AdminManager.MAIN_ADMIN_ID:
            return True

        async with Database._pool.acquire() as conn:
            user = await conn.fetchrow('SELECT is_admin FROM users WHERE user_id = $1', user_id)
            return bool(user['is_admin']) if user else False

    @staticmethod
    async def is_main_admin(user_id: int) -> bool:
        return user_id == AdminManager.MAIN_ADMIN_ID

    @staticmethod
    async def add_admin(user_id: int, username: str = "", added_by: int = None) -> bool:
        async with Database.transaction() as conn:
            await UserManager.get_or_create(user_id, username, "")
            result = await conn.execute(
                'UPDATE users SET is_admin = TRUE, added_by = $2 WHERE user_id = $1',
                user_id, added_by or AdminManager.MAIN_ADMIN_ID
            )
            if result == "UPDATE 0":
                logger.error(f"Не удалось обновить пользователя {user_id}")
                return False
            logger.info(f"Администратор {user_id} успешно добавлен")
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
                ORDER BY user_id
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
            rows = await conn.fetch('SELECT * FROM categories ORDER BY COALESCE(parent_id, 0), id')
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
        requirements: str = "",
        total_quantity: int = 1,
        price_per_unit: Optional[float] = None,
        available_quantities: Optional[List[int]] = None
    ) -> str:
        task_id = hashlib.md5(f"{title}_{datetime.now()}_{secrets.token_hex(4)}".encode()).hexdigest()[:8]
        async with Database._pool.acquire() as conn:
            if category_id:
                cat_exists = await conn.fetchval('SELECT id FROM categories WHERE id = $1', category_id)
                if not cat_exists:
                    logger.warning(f"Категория {category_id} не существует, устанавливаем NULL")
                    category_id = None

            # Если available_quantities не задан, задание простое
            if available_quantities is None:
                available_quantities_json = None
                price_per_unit = reward  # для простого задания цена за единицу = награда
                total_quantity = 1
            else:
                available_quantities_json = json.dumps(available_quantities)

            await conn.execute('''
                INSERT INTO tasks 
                    (task_id, category_id, title, description, target_type, target, reward, requirements, created_by,
                     total_quantity, remaining_quantity, price_per_unit, available_quantities, available, active)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            ''', task_id, category_id, title, description, target_type, target, reward, requirements, created_by,
                total_quantity, total_quantity, price_per_unit, available_quantities_json, True, True)

            check = await conn.fetchrow('SELECT task_id, available, active, taken_by FROM tasks WHERE task_id = $1', task_id)
            logger.info(f"✅ Задание {task_id} создано: available={check['available']}, active={check['active']}, taken_by={check['taken_by']}")
        return task_id

    @staticmethod
    async def get_available(category_id: Optional[int] = None) -> List[dict]:
        async with Database._pool.acquire() as conn:
            query = '''
                SELECT * FROM tasks 
                WHERE available = TRUE AND active = TRUE AND taken_by IS NULL AND remaining_quantity > 0
            '''
            args = []
            if category_id is not None:
                query += " AND category_id = $1"
                args.append(category_id)
            query += " ORDER BY created_date DESC"

            logger.info(f"SQL get_available: {query}, args={args}")
            rows = await conn.fetch(query, *args)
            result = [dict(r) for r in rows]
            # Парсим JSON для available_quantities
            for r in result:
                if r['available_quantities']:
                    try:
                        r['available_quantities'] = json.loads(r['available_quantities'])
                    except:
                        r['available_quantities'] = None
            logger.info(f"Найдено доступных заданий: {len(result)}")
            return result

    @staticmethod
    async def get_by_id(task_id: str) -> Optional[dict]:
        async with Database._pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM tasks WHERE task_id = $1', task_id)
            if row:
                result = dict(row)
                if result['available_quantities']:
                    try:
                        result['available_quantities'] = json.loads(result['available_quantities'])
                    except:
                        result['available_quantities'] = None
                return result
            return None

    @staticmethod
    async def assign(task_id: str, user_id: int) -> bool:
        """Используется для простых заданий (total_quantity = 1)"""
        async with Database.transaction() as conn:
            task = await conn.fetchrow('SELECT * FROM tasks WHERE task_id = $1 FOR UPDATE', task_id)
            if not task or task['taken_by'] or not task['available'] or task['remaining_quantity'] <= 0:
                return False
            # Для простого задания уменьшаем remaining_quantity до 0
            await conn.execute(
                'UPDATE tasks SET taken_by = $2, available = FALSE, assigned_date = NOW(), remaining_quantity = 0 WHERE task_id = $1',
                task_id, user_id
            )
            await conn.execute(
                'INSERT INTO user_tasks (user_id, task_id, taken_quantity) VALUES ($1, $2, 1)',
                user_id, task_id
            )
            return True

    @staticmethod
    async def take_partial(task_id: str, user_id: int, quantity: int) -> bool:
        """Резервирует часть многочастного задания"""
        async with Database.transaction() as conn:
            task = await conn.fetchrow('SELECT * FROM tasks WHERE task_id = $1 FOR UPDATE', task_id)
            if not task or task['remaining_quantity'] < quantity:
                return False

            new_remaining = task['remaining_quantity'] - quantity
            if new_remaining == 0:
                # Если задание полностью выбрано, помечаем как недоступное
                await conn.execute(
                    'UPDATE tasks SET remaining_quantity = 0, available = FALSE, taken_by = $2 WHERE task_id = $1',
                    task_id, user_id
                )
            else:
                # Иначе просто уменьшаем остаток, задание остаётся доступным
                await conn.execute(
                    'UPDATE tasks SET remaining_quantity = $2 WHERE task_id = $1',
                    task_id, new_remaining
                )

            await conn.execute(
                'INSERT INTO user_tasks (user_id, task_id, taken_quantity) VALUES ($1, $2, $3)',
                user_id, task_id, quantity
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
            # Вычисляем заработанную сумму на основе взятого количества
            ut = await conn.fetchrow('SELECT taken_quantity FROM user_tasks WHERE user_id = $1 AND task_id = $2', user_id, task_id)
            taken_q = ut['taken_quantity'] if ut else 1
            earned = taken_q * task['price_per_unit']

            await conn.execute(
                'UPDATE tasks SET completed = TRUE, completed_date = NOW(), proof = $2, active = FALSE WHERE task_id = $1',
                task_id, proof
            )
            await conn.execute(
                'UPDATE user_tasks SET status = $2, completed_date = NOW(), earned = $3 WHERE user_id = $4 AND task_id = $1',
                task_id, 'completed', earned, user_id
            )
            await conn.execute(
                'UPDATE users SET total_earned = total_earned + $2, completed_tasks = completed_tasks + 1 WHERE user_id = $1',
                user_id, earned
            )
            await conn.execute('''
                INSERT INTO stats (date, tasks_completed, total_payout) 
                VALUES (CURRENT_DATE, 1, $1)
                ON CONFLICT (date) DO UPDATE SET 
                    tasks_completed = stats.tasks_completed + 1,
                    total_payout = stats.total_payout + $1
            ''', earned)
            return True

    @staticmethod
    async def get_user_tasks(user_id: int, status: Optional[str] = None) -> List[dict]:
        async with Database._pool.acquire() as conn:
            query = '''
                SELECT t.*, ut.status, ut.taken_date, ut.earned, ut.taken_quantity
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

    @staticmethod
    async def delete_task(task_id: str, admin_id: int) -> bool:
        """Удаление задания администратором (полное удаление из БД)"""
        async with Database.transaction() as conn:
            # Проверяем, существует ли задание
            task = await conn.fetchrow('SELECT * FROM tasks WHERE task_id = $1', task_id)
            if not task:
                return False
            
            # Удаляем связанные записи
            await conn.execute('DELETE FROM user_tasks WHERE task_id = $1', task_id)
            await conn.execute('DELETE FROM pending_links WHERE task_id = $1', task_id)
            await conn.execute('DELETE FROM completion_requests WHERE task_id = $1', task_id)
            await conn.execute('DELETE FROM tracking_links WHERE task_id = $1', task_id)
            await conn.execute('DELETE FROM payment_awaiting WHERE task_id = $1', task_id)
            
            # Удаляем само задание
            await conn.execute('DELETE FROM tasks WHERE task_id = $1', task_id)
            logger.info(f"✅ Задание {task_id} удалено администратором {admin_id}")
            return True


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
            total_users = await conn.fetchval('SELECT COUNT(*) FROM users') or 0
            total_tasks = await conn.fetchval('SELECT COUNT(*) FROM tasks') or 0
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


class CompletionManager:
    """Управление запросами на подтверждение выполнения заданий"""

    @staticmethod
    async def create_request(task_id: str, user_id: int) -> int:
        """Создаёт запрос на подтверждение, возвращает ID запроса"""
        async with Database._pool.acquire() as conn:
            # Проверим, нет ли уже активного запроса
            existing = await conn.fetchval('''
                SELECT id FROM completion_requests
                WHERE task_id = $1 AND user_id = $2 AND status = 'pending'
            ''', task_id, user_id)
            if existing:
                return existing

            row = await conn.fetchrow('''
                INSERT INTO completion_requests (task_id, user_id)
                VALUES ($1, $2)
                RETURNING id
            ''', task_id, user_id)
            return row['id']

    @staticmethod
    async def get_pending_requests() -> List[dict]:
        """Возвращает все необработанные запросы с информацией о задании и пользователе"""
        async with Database._pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT r.*,
                       t.title as task_title, t.reward,
                       u.username, u.first_name
                FROM completion_requests r
                JOIN tasks t ON r.task_id = t.task_id
                JOIN users u ON r.user_id = u.user_id
                WHERE r.status = 'pending'
                ORDER BY r.request_date ASC
            ''')
            return [dict(r) for r in rows]

    @staticmethod
    async def get_request(request_id: int) -> Optional[dict]:
        async with Database._pool.acquire() as conn:
            row = await conn.fetchrow('SELECT * FROM completion_requests WHERE id = $1', request_id)
            return dict(row) if row else None

    @staticmethod
    async def approve_request(request_id: int, admin_id: int) -> bool:
        """Подтверждает выполнение, переводит задание в статус ожидания оплаты"""
        logger.info(f"🔍 CompletionManager.approve_request: request_id={request_id}, admin_id={admin_id}")
        try:
            async with Database.transaction() as conn:
                # Получаем запрос с блокировкой
                req = await conn.fetchrow('SELECT * FROM completion_requests WHERE id = $1 FOR UPDATE', request_id)
                if not req:
                    logger.error(f"❌ Запрос {request_id} не найден")
                    return False
                if req['status'] != 'pending':
                    logger.error(f"❌ Запрос {request_id} имеет статус {req['status']}")
                    return False

                # Обновляем статус запроса
                await conn.execute('''
                    UPDATE completion_requests
                    SET status = 'approved', admin_id = $2, processed_date = NOW()
                    WHERE id = $1
                ''', request_id, admin_id)

                # Обновляем статус в user_tasks на 'awaiting_payment'
                await conn.execute('''
                    UPDATE user_tasks
                    SET status = 'awaiting_payment'
                    WHERE user_id = $2 AND task_id = $1
                ''', req['task_id'], req['user_id'])

                logger.info(f"✅ Запрос {request_id} одобрен, задание переведено в awaiting_payment")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка в approve_request: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    @staticmethod
    async def reject_request(request_id: int, admin_id: int) -> bool:
        """Отклоняет запрос, возвращает задание в доступные"""
        logger.info(f"🔍 CompletionManager.reject_request: request_id={request_id}, admin_id={admin_id}")
        try:
            async with Database.transaction() as conn:
                req = await conn.fetchrow('SELECT * FROM completion_requests WHERE id = $1 FOR UPDATE', request_id)
                if not req or req['status'] != 'pending':
                    return False

                # Обновляем статус запроса
                await conn.execute('''
                    UPDATE completion_requests
                    SET status = 'rejected', admin_id = $2, processed_date = NOW()
                    WHERE id = $1
                ''', request_id, admin_id)

                # Возвращаем задание обратно в доступные (увеличиваем remaining_quantity)
                # Сначала получаем количество, которое взял пользователь
                ut = await conn.fetchrow('SELECT taken_quantity FROM user_tasks WHERE user_id = $1 AND task_id = $2', req['user_id'], req['task_id'])
                taken_q = ut['taken_quantity'] if ut else 1

                await conn.execute('''
                    UPDATE tasks 
                    SET taken_by = NULL, 
                        available = CASE WHEN remaining_quantity + $1 > 0 THEN TRUE ELSE available END,
                        remaining_quantity = remaining_quantity + $1
                    WHERE task_id = $2
                ''', taken_q, req['task_id'])

                await conn.execute('''
                    DELETE FROM user_tasks 
                    WHERE user_id = $2 AND task_id = $1
                ''', req['task_id'], req['user_id'])

                logger.info(f"✅ Запрос {request_id} отклонен, задание возвращено")
                return True
        except Exception as e:
            logger.error(f"❌ Ошибка в reject_request: {e}")
            return False


class PaymentAwaitingManager:
    @staticmethod
    async def add(user_id: int, task_id: str, request_id: int) -> int:
        async with Database._pool.acquire() as conn:
            row = await conn.fetchrow('''
                INSERT INTO payment_awaiting (user_id, task_id, request_id)
                VALUES ($1, $2, $3)
                RETURNING id
            ''', user_id, task_id, request_id)
            return row['id']

    @staticmethod
    async def get_by_user(user_id: int) -> Optional[dict]:
        async with Database._pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT * FROM payment_awaiting
                WHERE user_id = $1 AND status = 'waiting'
                ORDER BY created_at DESC
                LIMIT 1
            ''', user_id)
            return dict(row) if row else None

    @staticmethod
    async def mark_completed(awaiting_id: int):
        async with Database._pool.acquire() as conn:
            await conn.execute('UPDATE payment_awaiting SET status = $1 WHERE id = $2', 'completed', awaiting_id)