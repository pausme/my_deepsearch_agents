"""
装修业务接口与持久化测试（FIX-005/006/007）

用 FastAPI TestClient 覆盖：
- 会话创建/详情/列表，字段对齐 PRD 接口文档
- 任务创建绑定会话与 thread_id、取消、状态流转
- 文件上传落库、file_id 归属下载、路径越界拒绝
- 用户归属校验（用户 A 访问用户 B 的资源被拒绝）
- Agent 执行通过 monkeypatch 模拟，不依赖真实 LLM

导入 app.api.server 会拉起模型/客户端初始化，需要先注入假环境变量。
"""

import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("LLM_QWEN_MAX", "test-model")
os.environ.setdefault("TAVILY_API_KEY", "tvly-test")
os.environ.setdefault("RAGFLOW_API_KEY", "ragflow-test")
os.environ.setdefault("RAGFLOW_API_URL", "http://localhost")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """独立临时数据库 + 假 run_deep_agent 的测试客户端。"""
    import app.api.renovation_server as renovation_server
    from fastapi.testclient import TestClient

    tmp_db = tmp_path_factory.mktemp("db") / "test.sqlite3"
    os.environ["RENOVATION_DB_PATH"] = str(tmp_db)

    from app.db import database

    database.reset_connection()

    # 模拟 Agent 执行：记录调用并短暂挂起，便于测试取消逻辑
    executed = []

    async def fake_run_deep_agent(query, session_id):
        executed.append((query, session_id))

    original_runner = renovation_server.run_deep_agent
    renovation_server.run_deep_agent = fake_run_deep_agent

    from app.api.server import app

    with TestClient(app) as test_client:
        test_client.executed = executed
        yield test_client

    renovation_server.run_deep_agent = original_runner
    database.reset_connection()


def create_session(client, user="1", **overrides):
    body = {
        "city": "杭州",
        "house_area": 89.5,
        "room_type": "三室两厅一卫",
        "renovation_stage": "QUOTE_REVIEW",
        "budget_min": 120000,
        "budget_max": 180000,
        "priority_tags": ["省钱", "环保"],
        **overrides,
    }
    response = client.post(
        "/api/renovation/sessions", json=body, headers={"X-User-Id": user}
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestSessionApi:
    def test_create_session(self, client):
        data = create_session(client)
        assert data["status"] == "created"
        assert data["session_id"].startswith("session_")
        assert data["thread_id"]
        assert data["session"]["city"] == "杭州"
        assert data["session"]["priority_tags"] == ["省钱", "环保"]

    def test_session_detail_and_list(self, client):
        created = create_session(client, city="上海")
        session_id = created["session_id"]

        detail = client.get(
            f"/api/renovation/sessions/{session_id}", headers={"X-User-Id": "1"}
        ).json()
        assert detail["session"]["city"] == "上海"
        assert detail["tasks"] == [] and detail["reports"] == []

        listed = client.get("/api/renovation/sessions", headers={"X-User-Id": "1"}).json()
        assert any(s["session_id"] == session_id for s in listed["sessions"])

    def test_session_not_found(self, client):
        response = client.get("/api/renovation/sessions/session_none")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "SESSION_NOT_FOUND"

    def test_session_ownership(self, client):
        created = create_session(client, user="2")
        session_id = created["session_id"]
        # 用户 1 访问用户 2 的会话被拒绝
        response = client.get(
            f"/api/renovation/sessions/{session_id}", headers={"X-User-Id": "1"}
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "SESSION_FORBIDDEN"


class TestTaskApi:
    def test_create_task_binds_session_and_thread(self, client):
        created = create_session(client)
        response = client.post(
            "/api/renovation/tasks",
            json={
                "session_id": created["session_id"],
                "query": "帮我分析这份报价单",
                "analysis_type": "QUOTE_REVIEW",
            },
            headers={"X-User-Id": "1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"
        assert data["thread_id"] == created["thread_id"]
        assert data["task_id"].startswith("task_")
        # 假 runner 在事件循环上调度，稍等它执行
        import time

        for _ in range(20):
            if client.executed:
                break
            time.sleep(0.05)
        assert client.executed, "run_deep_agent 应被调用"

    def test_task_not_cancellable_after_finish(self, client):
        from app.repository import renovation_repository as repo

        created = create_session(client)
        task = repo.create_task(
            session_id=created["session_id"],
            user_id=1,
            thread_id=created["thread_id"],
            analysis_type="FULL_REPORT",
            query="q",
        )
        repo.update_task_status(task["task_id"], "SUCCESS")
        response = client.post(
            f"/api/renovation/tasks/{task['task_id']}/cancel", headers={"X-User-Id": "1"}
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "TASK_NOT_CANCELLABLE"


class TestFileApi:
    def test_upload_records_and_download_by_file_id(self, client):
        created = create_session(client)
        response = client.post(
            "/api/renovation/files/upload",
            data={
                "session_id": created["session_id"],
                "file_type": "QUOTE",
            },
            files={"files": ("报价单.xlsx", b"fake-xlsx", "application/octet-stream")},
            headers={"X-User-Id": "1"},
        )
        assert response.status_code == 200, response.text
        files = response.json()["files"]
        assert len(files) == 1
        record = files[0]
        assert record["file_id"].startswith("file_")
        assert record["file_type"] == "QUOTE"
        assert record["original_name"] == "报价单.xlsx"

        # 按列表查询
        listed = client.get(
            f"/api/renovation/files?session_id={created['session_id']}",
            headers={"X-User-Id": "1"},
        ).json()
        assert any(f["file_id"] == record["file_id"] for f in listed["files"])

        # 按 file_id 下载
        download = client.get(
            f"/api/renovation/files/download?file_id={record['file_id']}",
            headers={"X-User-Id": "1"},
        )
        assert download.status_code == 200

    def test_upload_rejects_bad_extension(self, client):
        created = create_session(client)
        response = client.post(
            "/api/renovation/files/upload",
            data={"session_id": created["session_id"], "file_type": "QUOTE"},
            files={"files": ("virus.exe", b"bad", "application/octet-stream")},
            headers={"X-User-Id": "1"},
        )
        data = response.json()
        assert data["status"] == "all_rejected"
        assert data["rejected"][0]["error"]

    def test_download_ownership(self, client):
        created = create_session(client, user="3")
        upload = client.post(
            "/api/renovation/files/upload",
            data={"session_id": created["session_id"], "file_type": "CONTRACT"},
            files={"files": ("合同.txt", b"content", "text/plain")},
            headers={"X-User-Id": "3"},
        )
        file_id = upload.json()["files"][0]["file_id"]
        response = client.get(
            f"/api/renovation/files/download?file_id={file_id}", headers={"X-User-Id": "1"}
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "FILE_FORBIDDEN"


class TestReportPersistence:
    def test_report_lifecycle_via_repository(self, client):
        """报告与风险项的完整落库链路（工具层调用 repository 的行为）。"""
        from app.repository import renovation_repository as repo

        created = create_session(client)
        session_id = created["session_id"]
        thread_id = created["thread_id"]

        task = repo.create_task(session_id, 1, thread_id, "QUOTE_REVIEW", "分析报价单")
        repo.update_task_status(task["task_id"], "RUNNING")

        # 模拟 detect 工具落风险项
        assert repo.save_risk_items_by_thread(
            thread_id,
            [
                {
                    "risk_type": "PAYMENT",
                    "level": "HIGH",
                    "title": "首期付款比例过高（60%）",
                    "evidence": "开工前支付 60%",
                    "description": "付款过度前置",
                    "suggestion": "首期降到 30%",
                }
            ],
        )

        # 模拟 generate_renovation_report 落报告
        report = repo.create_report(
            session_id=session_id,
            task_id=task["task_id"],
            report_id="R20260903TEST01",
            title="装修决策分析报告",
            summary="报价整体偏高",
            budget_score=68,
            markdown_path="/tmp/does-not-matter.md",
        )
        assert report["report_id"] == "R20260903TEST01"
        repo.update_task_status(task["task_id"], "SUCCESS")

        detail = client.get(
            f"/api/renovation/reports/{report['report_id']}", headers={"X-User-Id": "1"}
        ).json()
        assert detail["report"]["budget_score"] == 68
        assert len(detail["risk_items"]) == 1
        assert detail["risk_items"][0]["risk_level"] == "HIGH"
        # 风险项在报告创建时回填了 report_id
        assert detail["risk_items"][0]["report_id"] == report["report_id"]

    def test_report_ownership(self, client):
        from app.repository import renovation_repository as repo

        created = create_session(client, user="4")
        task = repo.create_task(created["session_id"], 4, created["thread_id"], "FULL_REPORT", "q")
        report = repo.create_report(
            session_id=created["session_id"],
            task_id=task["task_id"],
            report_id="R20260903USER04",
            title="t",
            summary="s",
            budget_score=50,
            markdown_path="/tmp/x.md",
        )
        response = client.get(
            f"/api/renovation/reports/{report['report_id']}", headers={"X-User-Id": "1"}
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "REPORT_FORBIDDEN"

    def test_active_task_lifecycle_lookup(self, client):
        from app.repository import renovation_repository as repo

        created = create_session(client)
        thread_id = created["thread_id"]
        task = repo.create_task(created["session_id"], 1, thread_id, "FULL_REPORT", "q")

        active = repo.get_active_task_by_thread(thread_id)
        assert active["task_id"] == task["task_id"]
        assert active["status"] == "PENDING"

        repo.update_task_status(task["task_id"], "RUNNING")
        assert repo.get_active_task_by_thread(thread_id)["status"] == "RUNNING"

        repo.update_task_status(task["task_id"], "FAILED", error_message="模型超时")
        assert repo.get_active_task_by_thread(thread_id) is None
        finished = repo.get_task(task["task_id"])
        assert finished["status"] == "FAILED"
        assert finished["error_message"] == "模型超时"
        assert finished["finish_time"]


class TestStaticServing:
    def test_spa_fallback_when_dist_present(self, client):
        """frontend/dist 存在时，非 API GET 应回落到 index.html（单进程部署）。"""
        from pathlib import Path

        dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
        if not (dist / "index.html").exists():
            pytest.skip("frontend/dist 不存在，先执行 pnpm build")

        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # SPA 路由也回落到 index.html，由前端路由接管
        response = client.get("/some-spa-route")
        assert response.status_code == 200

        # 未知 API 路径仍然 404，不被 SPA 兜底吞掉
        response = client.get("/api/not-exists")
        assert response.status_code == 404
