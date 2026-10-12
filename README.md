# Product Assistant Agent

多模态产品使用助手的单仓库工程。当前已完成阶段一工程骨架：React 前端、FastAPI API、Celery worker、PostgreSQL + pgvector + BM25、Redis、MinIO、迁移、健康检查和 CI。

## 环境要求

- Docker Desktop 与 Docker Compose；
- 本地开发可使用 Python 3.12、Node.js 22 和 pnpm 10。

## 一键启动

```bash
cp .env.example .env
docker compose up --build
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
docker compose up --build
```

启动后：

- 前端：http://localhost:8080
- API 文档：http://localhost:8000/docs
- Liveness：http://localhost:8000/api/v1/health/live
- Readiness：http://localhost:8000/api/v1/health/ready
- MinIO Console：http://localhost:9001

Readiness 会实际检查 PostgreSQL 的 `vector`/`pg_search` 扩展、Redis 和 MinIO bucket。

## 本地开发

后端：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\backend[dev]"
Set-Location backend
uvicorn app.main:app --reload
```

前端：

```powershell
Set-Location frontend
corepack enable
pnpm install
pnpm dev
```

## 质量检查

```powershell
Set-Location backend
ruff check .
pyright
pytest

Set-Location ..\frontend
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

完整产品设计见 [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md)。
