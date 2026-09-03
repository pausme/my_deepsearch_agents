# 部署指南

本文档描述把「装修决策管家」部署到一台公网服务器（推荐配置 **2 核 2GB**，如阿里云/腾讯云入门 ECS）的完整步骤。

## 1. 部署形态

推荐**单进程部署**：FastAPI 同时提供业务接口、WebSocket 和前端静态文件，只跑一个 uvicorn 进程，另加一个 MySQL 容器（可选）。

```text
用户浏览器 ──▶ nginx(80/443, 可选) ──▶ uvicorn:8000 ──▶ 外部 LLM / Tavily / RAGFlow API
                                          └── SQLite（业务元数据）
                                          └── app/output（报告产物）
```

两条硬性约束：

- **uvicorn 必须单 worker**（不加 `--workers`）。WebSocket 连接表、后台任务表、会话检查点均为进程内状态，多 worker 会导致事件推送错乱、任务无法取消。
- **RAGFlow 不能装在同一台机器**。RAGFlow 官方要求 4 核 16GB 起（内含 ES/MinIO 全家桶）；不接私有知识库不影响其余功能。

## 2. 服务器准备

```bash
# 系统依赖（Ubuntu 22.04/24.04）
sudo apt update && sudo apt install -y python3.12 python3.12-venv git
# 安装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```bash
# 2GB 内存建议加 swap，防止 Agent 长任务期间 OOM
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 3. 拉取代码与依赖

```bash
sudo mkdir -p /opt/renovation-agent && sudo chown $USER /opt/renovation-agent
git clone git@github.com:pausme/my_deepsearch_agents.git /opt/renovation-agent
cd /opt/renovation-agent
uv sync
```

> 前端构建建议在本地电脑完成后上传，不要在 2GB 服务器上装 Node 构建（见第 5 步）。

## 4. 配置环境变量

```bash
cp .env.example .env
vim .env
```

生产环境注意三项：

| 变量 | 建议 |
| --- | --- |
| `ALLOWED_ORIGINS` | 改为你的具体域名（如 `https://renov.example.com`），不要用 `*` |
| `RENOVATION_DB_PATH` | 默认在项目目录内；有数据盘时移到数据盘 |
| `LOG_LEVEL` | 一般 `INFO`，排查问题时临时开 `DEBUG` |

改完执行自检：

```bash
uv run python scripts/check_env.py
```

全部 ✅ 后再继续。MySQL 教学库可选（只有"数据库查询助手"需要）：

```bash
docker compose -f docker/docker-compose.yaml up -d
```

## 5. 前端构建与上传（本地电脑执行）

```bash
git clone git@github.com:pausme/my_deepsearch_agents.git
cd my_deepsearch_agents/frontend
pnpm install && pnpm build
# 把构建产物同步到服务器（FastAPI 会自动托管 dist 目录）
rsync -avz --delete dist/ user@your-server:/opt/renovation-agent/frontend/dist/
```

同源部署下前端**不需要**配置 `VITE_API_BASE_URL`，页面会自动请求当前域名。

## 6. 启动与开机自启（systemd）

```bash
# 修改 service 文件里的 User / WorkingDirectory / EnvironmentFile 路径
sudo cp deploy/renovation-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now renovation-agent
journalctl -u renovation-agent -f     # 观察启动日志
```

验证：

```bash
curl http://127.0.0.1:8000/api/files?path=x   # 应返回 JSON（路径校验失败信息）
curl -I http://127.0.0.1:8000/                # 应返回 200 text/html（前端首页）
```

## 7. nginx + HTTPS（有域名时）

```bash
sudo apt install -y nginx
sudo cp deploy/nginx.conf.sample /etc/nginx/sites-available/renovation
# 编辑 server_name 为你的域名
sudo ln -s /etc/nginx/sites-available/renovation /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
# HTTPS（推荐）
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d renov.example.com
```

没有域名/IP 直连时，可跳过 nginx，直接访问 `http://服务器IP:8000`（记得在安全组放行 8000）。

## 8. 数据备份与升级

```bash
# 备份（SQLite 单文件 + 会话产物）
crontab -e
# 每天 3:17 备份数据库与报告产物
17 3 * * * sqlite3 /opt/renovation-agent/app/data/renovation.sqlite3 ".backup /opt/backups/renovation-$(date +\%F).sqlite3" && tar czf /opt/backups/output-$(date +\%F).tgz /opt/renovation-agent/app/output
```

```bash
# 升级版本
cd /opt/renovation-agent && git pull && uv sync
sudo systemctl restart renovation-agent
```

## 9. 安全清单（上线前过一遍）

- [ ] `ALLOWED_ORIGINS` 已收紧为具体域名
- [ ] `.env` 权限 600，不进 git
- [ ] SQLite、`app/output`、`app/updated` 已纳入备份
- [ ] 服务器防火墙/安全组只放行 80/443（或 8000），SSH 用密钥登录
- [ ] 已知边界可接受：无真实登录态（`X-User-Id` 预留）、会话记忆重启丢失（`InMemorySaver`）、无任务队列
- [ ] 页面已展示"仅供参考，不构成法律/财务/工程意见"免责声明（报告模板自动附带）

## 10. 常见问题

| 现象 | 原因与处理 |
| --- | --- |
| WebSocket 连不上 | nginx 未配置 `/ws/` 的 Upgrade 头，或缺 `proxy_read_timeout` |
| 任务发起后收不到进度 | WebSocket 与任务不在同一进程（开了多 worker），必须单 worker |
| 页面空白/接口 404 | `frontend/dist` 未上传，或 `FRONTEND_DIST` 指错目录 |
| 内存吃紧 | 调低 MySQL `innodb_buffer_pool_size=128M`、`performance_schema=OFF`；确认 swap 已开 |
| RAGFlow 助手报错 | RAGFlow 需独立部署或使用托管服务，改 `.env` 里的 `RAGFLOW_API_URL` 即可 |
