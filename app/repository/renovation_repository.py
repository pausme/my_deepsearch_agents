"""
装修业务数据仓库层

会话、文件、任务、报告、风险项的持久化读写。所有函数同步执行
（SQLite 单文件写入很快，不需要异步驱动），返回 dict 或 None/list。
数据库异常不向上抛——持久化是辅助能力，不能打断 Agent 执行链路，
调用方（工具/API）拿不到数据时按"无记录"处理即可。
"""

import json
import uuid
from datetime import datetime

from app.db.database import get_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _rows_to_dicts(cursor) -> list[dict]:
    return [dict(row) for row in cursor.fetchall()]


# ---------- 会话 ----------


def create_session(
    user_id: int,
    city: str,
    house_area: float,
    room_type: str,
    renovation_stage: str = "INITIAL",
    district: str = "",
    budget_min: float | None = None,
    budget_max: float | None = None,
    priority_tags: list[str] | None = None,
    delivery_date: str = "",
) -> dict:
    conn = get_connection()
    session_id = _new_id("session")
    thread_id = uuid.uuid4().hex
    now = _now()
    conn.execute(
        """INSERT INTO renovation_session
           (user_id, session_id, thread_id, city, district, house_area, room_type,
            renovation_stage, budget_min, budget_max, priority_tags, delivery_date,
            status, create_time, update_time)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?)""",
        (
            user_id, session_id, thread_id, city, district, house_area, room_type,
            renovation_stage, budget_min, budget_max,
            json.dumps(priority_tags or [], ensure_ascii=False), delivery_date,
            now, now,
        ),
    )
    conn.commit()
    return get_session(session_id, user_id)


def get_session(session_id: str, user_id: int | None = None) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM renovation_session WHERE session_id = ? AND deleted = 0",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    session = dict(row)
    if user_id is not None and session["user_id"] != user_id:
        return None
    session["priority_tags"] = json.loads(session["priority_tags"] or "[]")
    return session


def list_sessions(user_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM renovation_session WHERE user_id = ? AND deleted = 0 ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    sessions = []
    for row in rows:
        session = dict(row)
        session["priority_tags"] = json.loads(session["priority_tags"] or "[]")
        sessions.append(session)
    return sessions


def get_session_by_thread(thread_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM renovation_session WHERE thread_id = ? AND deleted = 0",
        (thread_id,),
    ).fetchone()
    if row is None:
        return None
    session = dict(row)
    session["priority_tags"] = json.loads(session["priority_tags"] or "[]")
    return session


# ---------- 任务 ----------


def create_task(
    session_id: str, user_id: int, thread_id: str, analysis_type: str, query: str
) -> dict:
    conn = get_connection()
    task_id = _new_id("task")
    conn.execute(
        """INSERT INTO renovation_task
           (task_id, session_id, user_id, thread_id, analysis_type, query,
            status, create_time)
           VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)""",
        (task_id, session_id, user_id, thread_id, analysis_type, query, _now()),
    )
    conn.commit()
    return get_task(task_id)


def get_task(task_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM renovation_task WHERE task_id = ?", (task_id,)
    ).fetchone()
    return dict(row) if row else None


def get_active_task_by_thread(thread_id: str) -> dict | None:
    """取线程下最新的未完结任务（PENDING/RUNNING）。"""
    conn = get_connection()
    row = conn.execute(
        """SELECT * FROM renovation_task WHERE thread_id = ?
           AND status IN ('PENDING', 'RUNNING') ORDER BY id DESC LIMIT 1""",
        (thread_id,),
    ).fetchone()
    return dict(row) if row else None


def update_task_status(
    task_id: str, status: str, error_message: str | None = None
) -> None:
    conn = get_connection()
    updates = ["status = ?"]
    params: list = [status]
    if status == "RUNNING":
        updates.append("start_time = ?")
        params.append(_now())
    elif status in ("SUCCESS", "FAILED", "CANCELLED"):
        updates.append("finish_time = ?")
        params.append(_now())
    if error_message is not None:
        updates.append("error_message = ?")
        params.append(error_message)
    params.append(task_id)
    conn.execute(f"UPDATE renovation_task SET {', '.join(updates)} WHERE task_id = ?", params)
    conn.commit()


def list_tasks(session_id: str) -> list[dict]:
    conn = get_connection()
    return _rows_to_dicts(
        conn.execute(
            "SELECT * FROM renovation_task WHERE session_id = ? ORDER BY id DESC LIMIT 50",
            (session_id,),
        )
    )


# ---------- 报告 ----------


def create_report(
    session_id: str,
    task_id: str,
    report_id: str,
    title: str,
    summary: str,
    budget_score: int | None,
    markdown_path: str,
) -> dict | None:
    conn = get_connection()
    conn.execute(
        """INSERT INTO renovation_report
           (report_id, session_id, task_id, title, summary, budget_score,
            markdown_path, status, create_time)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?)""",
        (report_id, session_id, task_id, title, summary, budget_score, markdown_path, _now()),
    )
    # 同任务内已落库的风险项回填报告编号
    conn.execute(
        "UPDATE renovation_risk_item SET report_id = ? WHERE task_id = ? AND report_id IS NULL",
        (report_id, task_id),
    )
    conn.commit()
    return get_report(report_id)


def get_report(report_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM renovation_report WHERE report_id = ?", (report_id,)
    ).fetchone()
    return dict(row) if row else None


def list_reports(session_id: str) -> list[dict]:
    conn = get_connection()
    return _rows_to_dicts(
        conn.execute(
            "SELECT * FROM renovation_report WHERE session_id = ? ORDER BY id DESC",
            (session_id,),
        )
    )


# ---------- 风险项 ----------


def save_risk_items(task_id: str, risks: list[dict]) -> int:
    """保存风险项（与报告的关联在 create_report 时回填）。"""
    if not risks:
        return 0
    conn = get_connection()
    now = _now()
    count = 0
    for risk in risks:
        conn.execute(
            """INSERT INTO renovation_risk_item
               (task_id, title, risk_type, risk_level, evidence, description,
                suggestion, create_time)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id,
                risk.get("title", ""),
                risk.get("risk_type", ""),
                risk.get("level", "MEDIUM"),
                risk.get("evidence", ""),
                risk.get("description", ""),
                risk.get("suggestion", ""),
                now,
            ),
        )
        count += 1
    conn.commit()
    return count


def save_risk_items_by_thread(thread_id: str, risks: list[dict]) -> bool:
    """按线程找到未完结任务并保存风险项；无任务记录时静默跳过。"""
    try:
        task = get_active_task_by_thread(thread_id)
        if task is None:
            return False
        save_risk_items(task["task_id"], risks)
        return True
    except Exception as e:  # noqa: BLE001 - 持久化失败不影响 Agent 执行
        logger.warning("保存风险项失败: %s", e)
        return False


def list_risk_items(task_id: str) -> list[dict]:
    conn = get_connection()
    return _rows_to_dicts(
        conn.execute(
            "SELECT * FROM renovation_risk_item WHERE task_id = ? ORDER BY id",
            (task_id,),
        )
    )


# ---------- 文件 ----------

ALLOWED_FILE_TYPES = {"QUOTE", "CONTRACT", "HOUSE_INFO", "MATERIAL", "REPORT"}


def record_file(
    user_id: int,
    session_id: str,
    original_name: str,
    storage_name: str,
    storage_path: str,
    file_type: str = "MATERIAL",
    file_size: int = 0,
) -> dict:
    conn = get_connection()
    file_id = _new_id("file")
    extension = ("." + storage_name.rsplit(".", 1)[-1].lower()) if "." in storage_name else ""
    conn.execute(
        """INSERT INTO renovation_file
           (user_id, session_id, file_id, original_name, storage_name, file_type,
            extension, file_size, storage_path, parse_status, create_time)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'SUCCESS', ?)""",
        (user_id, session_id, file_id, original_name, storage_name, file_type,
         extension, file_size, storage_path, _now()),
    )
    conn.commit()
    return get_file(file_id)


def get_file(file_id: str) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM renovation_file WHERE file_id = ? AND deleted = 0", (file_id,)
    ).fetchone()
    return dict(row) if row else None


def list_files(session_id: str, file_type: str | None = None) -> list[dict]:
    conn = get_connection()
    if file_type:
        cursor = conn.execute(
            "SELECT * FROM renovation_file WHERE session_id = ? AND file_type = ? AND deleted = 0 ORDER BY id DESC",
            (session_id, file_type),
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM renovation_file WHERE session_id = ? AND deleted = 0 ORDER BY id DESC",
            (session_id,),
        )
    return _rows_to_dicts(cursor)
