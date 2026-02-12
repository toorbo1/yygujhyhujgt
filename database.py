import os
import asyncpg
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class PostgresDB:
    """Менеджер подключения к PostgreSQL"""
    _pool = None
    
    @classmethod
    async def init_db(cls):
        """Инициализация пула подключений и создание таблиц"""
        # Получаем DATABASE_URL из переменных окружения Railway
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            # Для локальной разработки
            database_url = os.environ.get(
                'DATABASE_URL',
                'postgresql://postgres:password@localhost:5432/bot_db'
            )
        
        try:
            cls._pool = await asyncpg.create_pool(database_url)
            logger.info("✅ Подключение к PostgreSQL установлено")
            
            # Создаем таблицы
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
                    joined_date TIMESTAMP DEFAULT NOW(),
                    is_admin BOOLEAN DEFAULT FALSE,
                    added_by BIGINT,
                    permissions JSONB DEFAULT '[]',
                    total_earned DECIMAL(10,2) DEFAULT 0,
                    rating INTEGER DEFAULT 0
                )
            ''')
            
            # Таблица заданий
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    task_type TEXT,
                    target TEXT,
                    reward DECIMAL(10,2),
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
                    FOREIGN KEY (taken_by) REFERENCES users(user_id) ON DELETE SET NULL,
                    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL
                )
            ''')
            
            # Таблица заданий пользователей
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_tasks (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    task_id TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    taken_date TIMESTAMP DEFAULT NOW(),
                    completed_date TIMESTAMP,
                    earned DECIMAL(10,2),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE,
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
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
            ''')
            
            # Таблица ожидающих ссылок
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS pending_links (
                    task_id TEXT PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username TEXT,
                    task_title TEXT,
                    message_sent TIMESTAMP DEFAULT NOW(),
                    tracking_link TEXT,
                    processed BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
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
                    clicks INTEGER DEFAULT 0
                )
            ''')
            
            # Индексы для ускорения запросов
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_users_admin ON users(is_admin)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_available ON tasks(available, active)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_taken_by ON tasks(taken_by)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_user_tasks_user ON user_tasks(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_tracking_links_active ON tracking_links(active)')
            
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


class UserManager:
    """Менеджер для работы с пользователями"""
    
    @staticmethod
    async def get_or_create_user(user_id: int, username: str = "", first_name: str = "") -> Dict:
        """Получить или создать пользователя"""
        async with PostgresDB._pool.acquire() as conn:
            user = await conn.fetchrow(
                'SELECT * FROM users WHERE user_id = $1',
                user_id
            )
            
            if not user:
                await conn.execute(
                    '''
                    INSERT INTO users (user_id, username, first_name, joined_date)
                    VALUES ($1, $2, $3, NOW())
                    ''',
                    user_id, username, first_name
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
    async def get_user(user_id: int) -> Optional[Dict]:
        """Получить пользователя по ID"""
        async with PostgresDB._pool.acquire() as conn:
            user = await conn.fetchrow(
                'SELECT * FROM users WHERE user_id = $1',
                user_id
            )
            return dict(user) if user else None
    
    @staticmethod
    async def update_user(user_id: int, **kwargs) -> bool:
        """Обновить данные пользователя"""
        async with PostgresDB._pool.acquire() as conn:
            set_clause = ', '.join(f"{key} = ${i+2}" for i, key in enumerate(kwargs.keys()))
            query = f'UPDATE users SET {set_clause} WHERE user_id = $1'
            await conn.execute(query, user_id, *kwargs.values())
            return True
    
    @staticmethod
    async def get_user_stats(user_id: int) -> Dict:
        """Получение статистики пользователя"""
        async with PostgresDB._pool.acquire() as conn:
            # Получаем завершенные задания
            completed = await conn.fetchval(
                '''
                SELECT COUNT(*) FROM user_tasks 
                WHERE user_id = $1 AND status = 'completed'
                ''',
                user_id
            ) or 0
            
            # Получаем активные задания
            active = await conn.fetchval(
                '''
                SELECT COUNT(*) FROM user_tasks 
                WHERE user_id = $1 AND status = 'active'
                ''',
                user_id
            ) or 0
            
            # Получаем общий заработок
            total_earned = await conn.fetchval(
                '''
                SELECT COALESCE(SUM(earned), 0) FROM user_tasks 
                WHERE user_id = $1 AND status = 'completed'
                ''',
                user_id
            ) or 0
            
            return {
                "completed_count": completed,
                "active_count": active,
                "total_earned": float(total_earned),
                "rating": completed * 10
            }


class AdminManager:
    """Менеджер для работы с администраторами"""
    
    MAIN_ADMIN_ID = int(os.environ.get('MAIN_ADMIN_ID', '8358009538'))
    
    @staticmethod
    async def is_admin(user_id: int) -> bool:
        """Проверка, является ли пользователь админом"""
        if user_id == AdminManager.MAIN_ADMIN_ID:
            return True
        
        async with PostgresDB._pool.acquire() as conn:
            user = await conn.fetchval(
                'SELECT is_admin FROM users WHERE user_id = $1',
                user_id
            )
            return bool(user)
    
    @staticmethod
    async def is_main_admin(user_id: int) -> bool:
        """Проверка, является ли пользователь главным админом"""
        return user_id == AdminManager.MAIN_ADMIN_ID
    
    @staticmethod
    async def add_admin(user_id: int, username: str = "", added_by: int = None) -> bool:
        """Добавление администратора"""
        async with PostgresDB._pool.acquire() as conn:
            # Сначала создаем пользователя, если его нет
            await UserManager.get_or_create_user(user_id, username, "")
            
            # Делаем админом
            await conn.execute(
                '''
                UPDATE users 
                SET is_admin = TRUE, added_by = $2, permissions = '["manage_tasks", "view_stats"]'::jsonb
                WHERE user_id = $1
                ''',
                user_id, added_by or AdminManager.MAIN_ADMIN_ID
            )
            return True
    
    @staticmethod
    async def remove_admin(user_id: int) -> bool:
        """Удаление администратора"""
        if user_id == AdminManager.MAIN_ADMIN_ID:
            return False
        
        async with PostgresDB._pool.acquire() as conn:
            await conn.execute(
                'UPDATE users SET is_admin = FALSE WHERE user_id = $1',
                user_id
            )
            return True
    
    @staticmethod
    async def get_all_admins() -> List[Dict]:
        """Получение списка всех админов"""
        async with PostgresDB._pool.acquire() as conn:
            admins = await conn.fetch(
                'SELECT * FROM users WHERE is_admin = TRUE OR user_id = $1',
                AdminManager.MAIN_ADMIN_ID
            )
            return [dict(admin) for admin in admins]


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
        requirements: str = ""
    ) -> str:
        """Создание нового задания"""
        import hashlib
        from datetime import datetime
        
        task_id = hashlib.md5(f"{title}_{datetime.now()}".encode()).hexdigest()[:8]
        
        async with PostgresDB._pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO tasks (
                    task_id, title, description, task_type, target, 
                    reward, requirements, created_by, created_date
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                ''',
                task_id, title, description, task_type, target,
                reward, requirements, created_by
            )
            
        return task_id
    
    @staticmethod
    async def get_available_tasks() -> List[Dict]:
        """Получение списка доступных заданий"""
        async with PostgresDB._pool.acquire() as conn:
            tasks = await conn.fetch(
                '''
                SELECT * FROM tasks 
                WHERE available = TRUE AND active = TRUE AND taken_by IS NULL
                ORDER BY created_date DESC
                '''
            )
            return [dict(task) for task in tasks]
    
    @staticmethod
    async def get_task(task_id: str) -> Optional[Dict]:
        """Получение задания по ID"""
        async with PostgresDB._pool.acquire() as conn:
            task = await conn.fetchrow(
                'SELECT * FROM tasks WHERE task_id = $1',
                task_id
            )
            return dict(task) if task else None
    
    @staticmethod
    async def assign_task(task_id: str, user_id: int) -> bool:
        """Назначение задания пользователю"""
        async with PostgresDB.transaction() as conn:
            # Проверяем, доступно ли задание
            task = await conn.fetchrow(
                'SELECT * FROM tasks WHERE task_id = $1 FOR UPDATE',
                task_id
            )
            
            if not task or task['taken_by'] or not task['available']:
                return False
            
            # Назначаем задание
            await conn.execute(
                '''
                UPDATE tasks 
                SET taken_by = $2, available = FALSE, assigned_date = NOW(), work_link = NULL
                WHERE task_id = $1
                ''',
                task_id, user_id
            )
            
            # Добавляем запись в user_tasks
            await conn.execute(
                '''
                INSERT INTO user_tasks (user_id, task_id, status, taken_date)
                VALUES ($1, $2, 'active', NOW())
                ''',
                user_id, task_id
            )
            
            return True
    
    @staticmethod
    async def set_work_link(task_id: str, link: str) -> bool:
        """Установка рабочей ссылки для задания"""
        async with PostgresDB._pool.acquire() as conn:
            await conn.execute(
                'UPDATE tasks SET work_link = $1 WHERE task_id = $2',
                link, task_id
            )
            return True
    
    @staticmethod
    async def complete_task(task_id: str, user_id: int, proof: str = "") -> bool:
        """Завершение задания"""
        async with PostgresDB.transaction() as conn:
            task = await conn.fetchrow(
                'SELECT * FROM tasks WHERE task_id = $1 AND taken_by = $2 FOR UPDATE',
                task_id, user_id
            )
            
            if not task:
                return False
            
            # Обновляем задание
            await conn.execute(
                '''
                UPDATE tasks 
                SET completed = TRUE, completed_date = NOW(), proof = $2, active = FALSE
                WHERE task_id = $1
                ''',
                task_id, proof
            )
            
            # Обновляем запись пользователя
            await conn.execute(
                '''
                UPDATE user_tasks 
                SET status = 'completed', completed_date = NOW(), earned = $3
                WHERE user_id = $2 AND task_id = $1
                ''',
                task_id, user_id, task['reward']
            )
            
            # Обновляем баланс пользователя
            await conn.execute(
                '''
                UPDATE users 
                SET total_earned = total_earned + $2
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
            
            return True


class TrackingLinksManager:
    """Менеджер для работы с отслеживающими ссылками"""
    
    @staticmethod
    async def generate_link(user_id: int, task_id: str) -> str:
        """Генерация уникальной ссылки для отслеживания"""
        import secrets
        import hashlib
        
        token = secrets.token_urlsafe(16)
        link_id = hashlib.md5(f"{user_id}_{task_id}_{token}".encode()).hexdigest()[:8]
        
        async with PostgresDB._pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO tracking_links (link_id, user_id, task_id)
                VALUES ($1, $2, $3)
                ''',
                link_id, user_id, task_id
            )
        
        # Формируем ссылку
        bot_username = os.environ.get('BOT_USERNAME', 'your_bot')
        return f"https://t.me/{bot_username}?start={link_id}"
    
    @staticmethod
    async def get_link(link_id: str) -> Optional[Dict]:
        """Получение информации о ссылке"""
        async with PostgresDB._pool.acquire() as conn:
            link = await conn.fetchrow(
                'SELECT * FROM tracking_links WHERE link_id = $1',
                link_id
            )
            return dict(link) if link else None
    
    @staticmethod
    async def increment_clicks(link_id: str) -> None:
        """Увеличение счетчика кликов"""
        async with PostgresDB._pool.acquire() as conn:
            await conn.execute(
                'UPDATE tracking_links SET clicks = clicks + 1 WHERE link_id = $1',
                link_id
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


class PendingLinksManager:
    """Менеджер для работы с ожидающими ссылками"""
    
    @staticmethod
    async def save_pending(task_id: str, data: Dict) -> None:
        """Сохранение ожидающей ссылки"""
        async with PostgresDB._pool.acquire() as conn:
            await conn.execute(
                '''
                INSERT INTO pending_links (task_id, user_id, username, task_title, tracking_link)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (task_id) DO UPDATE
                SET user_id = EXCLUDED.user_id,
                    username = EXCLUDED.username,
                    task_title = EXCLUDED.task_title,
                    message_sent = NOW(),
                    tracking_link = EXCLUDED.tracking_link,
                    processed = FALSE
                ''',
                task_id,
                data['user_id'],
                data.get('username', ''),
                data.get('task_title', ''),
                data.get('tracking_link', '')
            )
    
    @staticmethod
    async def get_pending(task_id: str) -> Optional[Dict]:
        """Получение ожидающей ссылки"""
        async with PostgresDB._pool.acquire() as conn:
            pending = await conn.fetchrow(
                'SELECT * FROM pending_links WHERE task_id = $1 AND processed = FALSE',
                task_id
            )
            return dict(pending) if pending else None
    
    @staticmethod
    async def mark_processed(task_id: str) -> None:
        """Отметить ссылку как обработанную"""
        async with PostgresDB._pool.acquire() as conn:
            await conn.execute(
                'UPDATE pending_links SET processed = TRUE WHERE task_id = $1',
                task_id
            )
    
    @staticmethod
    async def delete_pending(task_id: str) -> None:
        """Удалить ожидающую ссылку"""
        async with PostgresDB._pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM pending_links WHERE task_id = $1',
                task_id
            )


class StatsManager:
    """Менеджер для работы со статистикой"""
    
    @staticmethod
    async def get_global_stats() -> Dict:
        """Получение глобальной статистики"""
        async with PostgresDB._pool.acquire() as conn:
            # Общая статистика
            total_users = await conn.fetchval('SELECT COUNT(*) FROM users')
            total_tasks = await conn.fetchval('SELECT COUNT(*) FROM tasks')
            completed_tasks = await conn.fetchval(
                'SELECT COUNT(*) FROM tasks WHERE completed = TRUE'
            ) or 0
            total_payout = await conn.fetchval(
                'SELECT COALESCE(SUM(reward), 0) FROM tasks WHERE completed = TRUE'
            ) or 0
            
            # Ожидающие ссылки
            pending_links = await conn.fetchval(
                'SELECT COUNT(*) FROM pending_links WHERE processed = FALSE'
            ) or 0
            
            # Активные задания
            active_tasks = await conn.fetchval(
                'SELECT COUNT(*) FROM tasks WHERE taken_by IS NOT NULL AND completed = FALSE'
            ) or 0
            
            return {
                "total_users": total_users,
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "total_payout": float(total_payout),
                "pending_links": pending_links,
                "active_tasks": active_tasks
            }
    
    @staticmethod
    async def get_daily_stats(days: int = 7) -> List[Dict]:
        """Получение статистики за последние N дней"""
        async with PostgresDB._pool.acquire() as conn:
            stats = await conn.fetch(
                '''
                SELECT * FROM stats 
                WHERE date >= CURRENT_DATE - $1::integer
                ORDER BY date DESC
                ''',
                days
            )
            return [dict(stat) for stat in stats]