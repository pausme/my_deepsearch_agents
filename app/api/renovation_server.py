"""
装修业务接口（FIX-005/006/007）

提供 PRD 接口清单中的装修会话、分析任务、资料文件和报告接口：
- POST /api/renovation/sessions                创建装修会话
- GET  /api/renovation/sessions                历史会话列表
- GET  /api/renovation/sessions/{session_id}   会话详情（含任务与报告）
- POST /api/renovation/tasks                   提交分析任务（绑定会话与 thread_id）
- POST /api/renovation/tasks/{task_id}/cancel  取消分析任务
- POST /api/renovation/files/upload            上传装修资料（按会话隔离并落库）
- GET  /api/renovation/files                   会话资料列表
- GET  /api/renovation/files/download          按 file_id 下载（不信任前端路径）
- GET  /api/renovation/reports                 会话报告列表
- GET  /api/renovation/reports/{report_id}     报告详情（含风险项）
- GET  /api/renovation/reports/{report_id}/content  报告 Markdown 内容

用户归属（FIX-007）：MVP 阶段用请求头 X-User-Id 预留用户身份（默认 1），
会话/文件/报告均校验归属；后续接入真实登录态时只需替换 get_user_id 依赖。
"""

import asyncio
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from fastapi.responses import FileResponse

from app.agent.main_agent import run_deep_agent
from app.api.error_codes import (
    FILE_FORBIDDEN,
    FILE_NOT_FOUND,
    FILE_PATH_INVALID,
    REPORT_FORBIDDEN,
    REPORT_NOT_FOUND,
    SESSION_FORBIDDEN,
    SESSION_NOT_FOUND,
    TASK_NOT_CANCELLABLE,
    TASK_NOT_FOUND,
    UPLOAD_REJECTED,
    biz_error,
)
from app.api.renovation_schema import RenovationSessionCreate, RenovationTaskCreate
from app.api.runtime_state import active_tasks, forget_task, output_dir, updated_dir
from app.repository import renovation_repository as repo
from app.utils.upload_security import MAX_FILE_SIZE, validate_upload

router = APIRouter(prefix="/api/renovation", tags=["renovation"])


def get_user_id(x_user_id: str = Header(default="", alias="X-User-Id")) -> int:
    """从 X-User-Id 请求头取当前用户；MVP 默认单用户 1。"""
    try:
        return int(x_user_id) if x_user_id else 1
    except ValueError:
        return 1


def _require_session(session_id: str, user_id: int) -> dict:
    session = repo.get_session(session_id)
    if session is None:
        raise biz_error(404, SESSION_NOT_FOUND, f"会话不存在: {session_id}")
    if session["user_id"] != user_id:
        raise biz_error(403, SESSION_FORBIDDEN, "无权访问该会话")
    return session


# ---------- 会话 ----------


@router.post("/sessions")
async def create_session(body: RenovationSessionCreate, user_id: int = Depends(get_user_id)):
    session = repo.create_session(
        user_id=user_id,
        city=body.city,
        house_area=body.house_area,
        room_type=body.room_type,
        renovation_stage=body.renovation_stage,
        district=body.district,
        budget_min=body.budget_min,
        budget_max=body.budget_max,
        priority_tags=body.priority_tags,
        delivery_date=body.delivery_date,
    )
    return {"status": "created", "session_id": session["session_id"], "thread_id": session["thread_id"], "session": session}


@router.get("/sessions")
async def list_sessions(user_id: int = Depends(get_user_id)):
    sessions = repo.list_sessions(user_id)
    # 附带每个会话的报告数，前端历史列表直接展示
    for session in sessions:
        session["report_count"] = len(repo.list_reports(session["session_id"]))
    return {"sessions": sessions}


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str, user_id: int = Depends(get_user_id)):
    session = _require_session(session_id, user_id)
    return {
        "session": session,
        "tasks": repo.list_tasks(session_id),
        "reports": repo.list_reports(session_id),
        "files": repo.list_files(session_id),
    }


# ---------- 分析任务 ----------


@router.post("/tasks")
async def create_task(body: RenovationTaskCreate, user_id: int = Depends(get_user_id)):
    session = _require_session(body.session_id, user_id)
    thread_id = session["thread_id"]

    # 同一会话只允许一个运行中任务，新任务先取消旧任务（与通用接口行为一致）
    old_task = active_tasks.get(thread_id)
    if old_task and not old_task.done():
        old_task.cancel()

    task = repo.create_task(
        session_id=session["session_id"],
        user_id=user_id,
        thread_id=thread_id,
        analysis_type=body.analysis_type,
        query=body.query,
    )

    agent_task = asyncio.create_task(run_deep_agent(body.query, thread_id))
    active_tasks[thread_id] = agent_task
    agent_task.add_done_callback(lambda finished: forget_task(thread_id, finished))

    return {
        "status": "started",
        "task_id": task["task_id"],
        "session_id": session["session_id"],
        "thread_id": thread_id,
    }


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, user_id: int = Depends(get_user_id)):
    task_row = repo.get_task(task_id)
    if task_row is None:
        raise biz_error(404, TASK_NOT_FOUND, f"任务不存在: {task_id}")
    if task_row["user_id"] != user_id:
        raise biz_error(403, SESSION_FORBIDDEN, "无权操作该任务")
    if task_row["status"] in ("SUCCESS", "FAILED", "CANCELLED"):
        raise biz_error(409, TASK_NOT_CANCELLABLE, f"任务已结束（{task_row['status']}），不可取消")

    thread_id = task_row["thread_id"]
    running = active_tasks.get(thread_id)
    if running and not running.done():
        running.cancel()
        try:
            await asyncio.wait_for(running, timeout=1.0)
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError:
            return {"status": "cancelling", "task_id": task_id, "thread_id": thread_id}

    repo.update_task_status(task_id, "CANCELLED")
    return {"status": "cancelled", "task_id": task_id, "thread_id": thread_id}


# ---------- 资料文件 ----------


@router.post("/files/upload")
async def upload_files(
    session_id: str = Form(...),
    file_type: str = Form("MATERIAL"),
    files: List[UploadFile] = File(...),
    user_id: int = Depends(get_user_id),
):
    session = _require_session(session_id, user_id)
    if file_type not in repo.ALLOWED_FILE_TYPES:
        raise biz_error(400, UPLOAD_REJECTED, f"file_type 仅支持：{', '.join(sorted(repo.ALLOWED_FILE_TYPES))}")

    target_dir = updated_dir / f"session_{session['thread_id']}"
    target_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    rejected = []
    for file in files:
        storage_name, extension, error = validate_upload(file.filename, None)
        if error:
            rejected.append({"original_name": file.filename, "error": error})
            continue

        file_path = target_dir / storage_name
        written = 0
        try:
            with file_path.open("wb") as buffer:
                while chunk := await file.read(1024 * 1024):
                    written += len(chunk)
                    if written > MAX_FILE_SIZE:
                        raise ValueError("文件超过 20MB 上限")
                    buffer.write(chunk)
        except ValueError as e:
            file_path.unlink(missing_ok=True)
            rejected.append({"original_name": file.filename, "error": str(e)})
            continue
        except Exception as e:  # noqa: BLE001
            file_path.unlink(missing_ok=True)
            rejected.append({"original_name": file.filename, "error": f"保存失败: {e}"})
            continue

        record = repo.record_file(
            user_id=user_id,
            session_id=session_id,
            original_name=file.filename,
            storage_name=storage_name,
            storage_path=str(file_path),
            file_type=file_type,
            file_size=written,
        )
        saved.append(record)

    return {
        "status": "uploaded" if saved else "all_rejected",
        "files": saved,
        "rejected": rejected,
    }


@router.get("/files")
async def list_session_files(session_id: str, file_type: str | None = None, user_id: int = Depends(get_user_id)):
    _require_session(session_id, user_id)
    return {"files": repo.list_files(session_id, file_type)}


@router.get("/files/download")
async def download_file(file_id: str, user_id: int = Depends(get_user_id)):
    record = repo.get_file(file_id)
    if record is None:
        raise biz_error(404, FILE_NOT_FOUND, f"文件不存在: {file_id}")
    if record["user_id"] != user_id:
        raise biz_error(403, FILE_FORBIDDEN, "无权下载该文件")

    abs_path = Path(record["storage_path"]).resolve()
    allowed_roots = [updated_dir.resolve(), output_dir.resolve()]
    if not any(abs_path.is_relative_to(root) for root in allowed_roots):
        raise biz_error(400, FILE_PATH_INVALID, "文件路径越界")
    if not abs_path.exists():
        raise biz_error(404, FILE_NOT_FOUND, "文件已不存在于磁盘")

    return FileResponse(abs_path, filename=record["original_name"])


# ---------- 报告 ----------


def _require_report(report_id: str, user_id: int) -> dict:
    report = repo.get_report(report_id)
    if report is None:
        raise biz_error(404, REPORT_NOT_FOUND, f"报告不存在: {report_id}")
    session = repo.get_session(report["session_id"])
    if session is None or session["user_id"] != user_id:
        raise biz_error(403, REPORT_FORBIDDEN, "无权访问该报告")
    return report


@router.get("/reports")
async def list_session_reports(session_id: str, user_id: int = Depends(get_user_id)):
    _require_session(session_id, user_id)
    reports = repo.list_reports(session_id)
    for report in reports:
        report["risk_items"] = repo.list_risk_items(report["task_id"])
    return {"reports": reports}


@router.get("/reports/{report_id}")
async def get_report_detail(report_id: str, user_id: int = Depends(get_user_id)):
    report = _require_report(report_id, user_id)
    return {"report": report, "risk_items": repo.list_risk_items(report["task_id"])}


@router.get("/reports/{report_id}/content")
async def get_report_content(report_id: str, user_id: int = Depends(get_user_id)):
    report = _require_report(report_id, user_id)
    markdown_path = report.get("markdown_path")
    if not markdown_path:
        raise biz_error(404, REPORT_NOT_FOUND, "报告没有关联的 Markdown 文件")

    abs_path = Path(markdown_path).resolve()
    if not abs_path.is_relative_to(output_dir.resolve()):
        raise biz_error(400, FILE_PATH_INVALID, "报告路径越界")
    if not abs_path.exists():
        raise biz_error(404, FILE_NOT_FOUND, "报告文件已不存在")

    return {
        "report_id": report_id,
        "title": report["title"],
        "markdown": abs_path.read_text(encoding="utf-8"),
    }
