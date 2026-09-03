"""
API 层共享运行时状态

active_tasks、output/updated 目录等进程内状态集中在这里，
供通用接口（server.py）和装修业务接口（renovation_server.py）共同使用，
避免循环导入。
"""

import asyncio
from pathlib import Path

# 当前文件位于 app/api/runtime_state.py，parents[1] 即 app 目录
project_root = Path(__file__).resolve().parents[1]

# 保存 thread_id -> 后台 Agent 任务，用于同一会话任务替换和主动取消
active_tasks: dict[str, asyncio.Task] = {}

# output 保存每个会话最终工作区，前端只允许从这里浏览和下载生成文件
output_dir = project_root / "output"
output_dir.mkdir(exist_ok=True)

# updated 暂存用户上传文件，run_deep_agent 启动时会复制到对应 output/session_xxx
updated_dir = project_root / "updated"
updated_dir.mkdir(exist_ok=True)


def forget_task(thread_id: str, task: asyncio.Task) -> None:
    """
    清理已结束任务的登记关系。

    done_callback 触发时，active_tasks 中可能已经被新任务替换；只有仍是同一个
    task 时才删除，避免误清理同 thread_id 下刚启动的新任务。
    """
    if active_tasks.get(thread_id) is task:
        active_tasks.pop(thread_id, None)
