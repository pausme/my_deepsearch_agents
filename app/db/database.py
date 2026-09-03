"""
SQLite 持久化连接管理

存储装修业务元数据（会话、文件、任务、报告、风险项），表结构对齐
docs/prd/home-renovation-data-model.md。选 SQLite 是因为零配置、适合
学习型项目与 2c2g 小服务器部署；repository 层字段命名与 PRD 的 MySQL
DDL 一致，后续迁 MySQL 只需替换本模块的连接实现。

数据库文件路径由 RENOVATION_DB_PATH 环境变量控制，默认 app/data/renovation.sqlite3。
"""

import os
import sqlite3
import threading
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger(__name__)

_connection: sqlite3.Connection | None = None
_db_lock = threading.Lock()
_schema_ready = False

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS renovation_session (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
    session_id TEXT NOT NULL UNIQUE,
    thread_id TEXT NOT NULL UNIQUE,
    city TEXT NOT NULL,
    district TEXT,
    house_area REAL NOT NULL,
    room_type TEXT NOT NULL,
    renovation_stage TEXT NOT NULL DEFAULT 'INITIAL',
    budget_min REAL,
    budget_max REAL,
    priority_tags TEXT,
    delivery_date TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    create_time TEXT NOT NULL,
    update_time TEXT NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS renovation_file (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
    session_id TEXT NOT NULL,
    file_id TEXT NOT NULL UNIQUE,
    original_name TEXT NOT NULL,
    storage_name TEXT NOT NULL,
    file_type TEXT NOT NULL DEFAULT 'MATERIAL',
    extension TEXT NOT NULL DEFAULT '',
    file_size INTEGER NOT NULL DEFAULT 0,
    storage_path TEXT NOT NULL,
    parse_status TEXT NOT NULL DEFAULT 'PENDING',
    create_time TEXT NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS renovation_task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    user_id INTEGER NOT NULL DEFAULT 1,
    thread_id TEXT NOT NULL,
    analysis_type TEXT NOT NULL,
    query TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    error_message TEXT,
    start_time TEXT,
    finish_time TEXT,
    create_time TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS renovation_report (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '装修决策分析报告',
    summary TEXT,
    budget_score INTEGER,
    risk_level TEXT,
    markdown_path TEXT,
    pdf_path TEXT,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    create_time TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS renovation_risk_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    report_id TEXT,
    title TEXT NOT NULL,
    risk_type TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'MEDIUM',
    evidence TEXT,
    description TEXT,
    suggestion TEXT,
    create_time TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_thread ON renovation_task(thread_id, status);
CREATE INDEX IF NOT EXISTS idx_file_session ON renovation_file(session_id);
CREATE INDEX IF NOT EXISTS idx_report_session ON renovation_report(session_id);
CREATE INDEX IF NOT EXISTS idx_risk_task ON renovation_risk_item(task_id);
"""


def _resolve_db_path() -> Path:
    return Path(os.getenv("RENOVATION_DB_PATH", Path(__file__).parents[1] / "data" / "renovation.sqlite3"))


def reset_connection() -> None:
    """关闭并重置连接（测试切换数据库路径时使用）。"""
    global _connection, _schema_ready
    with _db_lock:
        if _connection is not None:
            _connection.close()
        _connection = None
        _schema_ready = False


def get_connection() -> sqlite3.Connection:
    """获取共享连接（懒初始化，自动建表）。WAL 模式支持并发读。"""
    global _connection, _schema_ready
    with _db_lock:
        if _connection is None:
            db_path = _resolve_db_path()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            _connection = sqlite3.connect(str(db_path), check_same_thread=False)
            _connection.row_factory = sqlite3.Row
            _connection.execute("PRAGMA journal_mode=WAL")
            _connection.execute("PRAGMA foreign_keys=ON")
            logger.info("SQLite 已连接: %s", db_path)
        if not _schema_ready:
            _connection.executescript(SCHEMA_SQL)
            _connection.commit()
            _schema_ready = True
        return _connection
