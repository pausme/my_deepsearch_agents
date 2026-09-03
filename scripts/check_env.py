"""
部署前环境自检脚本

用法：uv run python scripts/check_env.py
按依赖顺序检查运行环境的每一项，输出 ✅/⚠️/❌ 汇总；有 ❌ 时退出码为 1。
故意不导入 app 包（避免拉起 langchain/tavily 等重依赖），只做静态检查。
"""

import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

results: list[tuple[str, str, bool]] = []  # (级别, 说明, 是否通过)


def ok(message: str) -> None:
    results.append(("✅", message, True))


def warn(message: str) -> None:
    results.append(("⚠️ ", message, True))


def fail(message: str) -> None:
    results.append(("❌", message, False))


def main() -> int:
    print("== 装修决策管家 部署前自检 ==\n")

    # 1. Python 版本
    if sys.version_info >= (3, 12):
        ok(f"Python {sys.version_info.major}.{sys.version_info.minor}")
    else:
        fail(f"Python 版本 {sys.version_info.major}.{sys.version_info.minor}，项目要求 3.12")

    # 2. .env 存在与必填项
    env_file = PROJECT_ROOT / ".env"
    env_values: dict[str, str] = {}
    if env_file.exists():
        ok(".env 文件存在")
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_values[key.strip()] = value.strip()
        # 已导出的环境变量优先（与 python-dotenv 行为一致）
        env_values.update({k: v for k, v in os.environ.items() if k in (
            "OPENAI_API_KEY", "LLM_QWEN_MAX", "TAVILY_API_KEY",
            "RAGFLOW_API_KEY", "RAGFLOW_API_URL",
        )})
    else:
        fail(".env 不存在，请先 cp .env.example .env 并填写")

    def require_env(key: str, hint: str) -> bool:
        value = env_values.get(key, "")
        if value and not value.startswith("你的"):
            return True
        fail(f"{key} 未配置（{hint}）")
        return False

    if env_values:
        require_env("OPENAI_API_KEY", "大模型 API Key")
        if require_env("LLM_QWEN_MAX", "模型名，如 qwen-max") and "OPENAI_BASE_URL" not in env_values:
            warn("OPENAI_BASE_URL 未配置，将使用 langchain-openai 默认地址")
        require_env("TAVILY_API_KEY", "网络搜索必需，https://app.tavily.com")
        ragflow_url = env_values.get("RAGFLOW_API_URL", "")
        ragflow_key = env_values.get("RAGFLOW_API_KEY", "")
        if ragflow_url.startswith("http") and ragflow_key and "your-ragflow" not in ragflow_url:
            ok("RAGFlow 已配置")
        else:
            warn("RAGFlow 未配置（知识库链路不可用，其余功能不受影响）")
        _ = llm_ok

    # 3. 关键文件
    template = PROJECT_ROOT / "app" / "templates" / "renovation_report.md"
    if template.exists():
        ok("报告模板存在")
    else:
        fail(f"报告模板缺失：{template}")

    # 4. 目录可写
    for name in ("output", "updated"):
        directory = PROJECT_ROOT / "app" / name
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".write_check"
            probe.write_text("ok")
            probe.unlink()
            ok(f"{name}/ 目录可写")
        except OSError as e:
            fail(f"{name}/ 目录不可写：{e}")

    # 5. SQLite 业务库
    from app.db.database import get_connection  # noqa: PLC0415 轻量导入

    try:
        conn = get_connection()
        conn.execute("SELECT 1")
        db_path = os.getenv(
            "RENOVATION_DB_PATH", PROJECT_ROOT / "app" / "data" / "renovation.sqlite3"
        )
        ok(f"业务元数据库可读写：{db_path}")
    except sqlite3.Error as e:
        fail(f"业务元数据库初始化失败：{e}")

    # 6. MySQL（数据库查询助手链路，可选）
    mysql_ready = all(env_values.get(k) for k in ("MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"))
    if mysql_ready:
        try:
            from mysql.connector import connect  # noqa: PLC0415

            with connect(
                host=env_values.get("MYSQL_HOST", "localhost"),
                port=int(env_values.get("MYSQL_PORT", "3306")),
                user=env_values["MYSQL_USER"],
                password=env_values["MYSQL_PASSWORD"],
                database=env_values["MYSQL_DATABASE"],
                connection_timeout=5,
            ):
                ok("MySQL 可连接")
        except Exception as e:  # noqa: BLE001
            warn(f"MySQL 暂不可连接（数据库助手链路不可用，不影响其余功能）：{e}")
    else:
        warn("MySQL 未完整配置（数据库助手链路不可用）")

    # 7. 前端构建产物
    dist = PROJECT_ROOT / "frontend" / "dist"
    frontend_dist_env = os.getenv("FRONTEND_DIST", "")
    if frontend_dist_env == "disabled":
        warn("前端静态托管已关闭（FRONTEND_DIST=disabled），需自行配置 nginx")
    elif (dist / "index.html").exists():
        ok("前端构建产物存在，将由 FastAPI 直接托管")
    else:
        warn("frontend/dist 不存在：本地开发可用 pnpm dev；部署前需执行 pnpm build")

    # 汇总
    print()
    has_fail = False
    for level, message, _ in results:
        print(f"{level} {message}")
        if level == "❌":
            has_fail = True

    print()
    if has_fail:
        print("自检未通过：请先解决 ❌ 项再启动服务。部署步骤见 docs/deployment.md")
        return 1
    print("自检通过，可以启动服务：uv run uvicorn app.api.server:app --host 0.0.0.0 --port 8000")
    _ = urlparse  # 保持导入对称，避免 lint 误报
    return 0


if __name__ == "__main__":
    sys.exit(main())
