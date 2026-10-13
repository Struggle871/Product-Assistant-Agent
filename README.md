# Product Assistant Agent

多模态产品使用助手的单仓库工程。阶段二已实现产品目录、可信来源、文档解析/OCR、结构化切片、Celery 入库任务和知识库管理页面。阶段三已接入语义向量、混合检索、Qwen 结构化评估、带引用的文本回答和评测入口。真实基础设施已通过联调，问答质量仍在校准，尚未完成阶段三验收。

## 环境要求

- Docker Desktop 与 Docker Compose；
- 本地开发可使用 Python 3.12、Node.js 22 和 pnpm 10。

## 一键启动

```bash
test -f .env || cp .env.example .env
docker compose up --build
```

Windows PowerShell：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 首次运行前在 .env 填写 EMBEDDING_API_KEY 和 CHAT_API_KEY。
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-local.ps1 -Evaluate
```

Windows 首次配置需要安装 [WSL](https://learn.microsoft.com/windows/wsl/install) 和
[Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)。
可以在管理员 PowerShell 中运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-wsl.ps1`；该脚本不会自动重启，
若 `.local/wsl-install-status.json` 中的 `restart_required` 为 true，需要手动重启 Windows，再启动 Docker Desktop。
`start-local.ps1` 会等待依赖就绪、初始化 bucket、启动应用并迁移数据库、导入演示资料，
`-Evaluate` 额外运行检索冒烟评测。仅启动依赖时使用 `-DependenciesOnly`。
API 的健康检查通过后才启动 Worker 和前端，确保数据库迁移已完成。

项目 PostgreSQL 默认使用宿主机 **5433** 端口，避免与已安装的本机 PostgreSQL 5432 冲突。
容器内仍使用 `postgres:5432`。如更改 `POSTGRES_PORT`，本地 `DATABASE_URL` 的端口也要同步。
普通 PostgreSQL 安装不一定包含 `vector` 和 `pg_search`，请使用 Compose 中的 ParadeDB 服务。
当前镜像固定为包含 PostgreSQL 18 的 ParadeDB 摘要，数据卷挂载在 `/var/lib/postgresql`。
已有其他 PostgreSQL 主版本的数据卷需要先备份并按官方流程升级，不能直接复用。

启动后：

- 前端：http://localhost:8080
- API 文档：http://localhost:8000/docs
- Liveness：http://localhost:8000/api/v1/health/live
- Readiness：http://localhost:8000/api/v1/health/ready
- MinIO Console：http://localhost:9001

管理页位于前端的“知识库管理”工作区。使用 `.env` 中的 `ADMIN_API_KEY` 输入管理密钥，然后点击“初始化演示目录”。也可以在后端容器中执行：

```bash
cd backend
python scripts/seed_catalog.py
python scripts/import_demo.py
```

三个固定演示产品的资料位于 `data/demo/`。上传资料支持 Markdown、HTML、TXT 和 PDF；PDF 在文本抽取不足时会通过 Tesseract OCR 兜底。重复内容按 SHA-256 幂等，归档资料不会进入新的活动索引，失败任务可以在管理页重试。

Readiness 会实际检查 PostgreSQL 的 `vector`/`pg_search` 扩展、Redis 和 MinIO bucket。
MinIO 社区版按[官方源码分发方式](https://github.com/minio/minio#source-only-distribution)
在本地构建固定版本 `RELEASE.2025-10-15T17-29-55Z`，不依赖已不可拉取的 `minio/minio`、`minio/mc` 镜像。
首次构建会下载 Go 工具链和模块；bucket 由后端的 `scripts.init_object_store` 初始化。
在 `backend` 目录运行 `python -m scripts.check_dependencies` 可以独立诊断，失败时返回非零退出码。
检查设有超时，返回缺失扩展、连接不可用、凭据无效或 bucket 缺失等代码，不打印连接密码。

## 阶段三：向量服务与文本问答

默认配置使用 SiliconFlow 的 `BAAI/bge-m3`，地址为 `https://api.siliconflow.cn/v1`。
复制 `.env.example` 后，在本地 `.env` 填写 `EMBEDDING_API_KEY`，不要提交密钥。
该模型输出 1024 维向量，`EMBEDDING_SEND_DIMENSIONS=false`；适配器会严格检查返回维度。
数据库同时支持 1024 与 1536 维向量，并通过模型配置标记隔离不同向量空间。
接口契约参考 [OpenAI Embeddings](https://developers.openai.com/api/reference/resources/embeddings/methods/create)，
模型维度参考 [BGE-M3 官方模型说明](https://huggingface.co/BAAI/bge-m3)。

完成资料导入后，在“助手对话”中选择产品并输入问题，可以查看文本回答、章节/页码引用及可回答性状态。
语义评估默认使用兼容 OpenAI 的 SiliconFlow `Qwen/Qwen3-8B`，在 `.env` 配置 `CHAT_API_KEY`；
可与 Embedding 使用同一服务密钥。问题和检索到的资料片段会发送到所配置的对话服务。
服务接口参考 [SiliconFlow Chat Completions](https://docs.siliconflow.cn/docs/api/chat-completions-post)。
`CHAT_ENABLE_THINKING` 和 `CHAT_THINKING_BUDGET` 控制 Qwen 推理模式；思维链不会返回给前端。
当前基线使用 `CHAT_STRUCTURED_OUTPUT=json_schema` 与非推理模式；模式对比结果保存在评测报告中。
兼容服务不支持 JSON Schema 时，可配置 `CHAT_STRUCTURED_OUTPUT=json_object`，仍执行服务端结构与引用校验。

文本问答接口为 `POST /api/v1/rag/answer`，保留仅检索接口 `POST /api/v1/rag/search`。
回答采用模型选择原文、服务端组织引用的方式；技术事实和步骤必须逐字对应可信资料。
模型只返回可回答性状态和资料 ID，原文由服务器读取；复合问题分别评估后汇总。
服务器校验产品/版本、句子边界、数字、引用 ID 和原文，失败时拒答并给出降级状态。
危险拆机/电气问题、缺少产品身份在检索前拦截，避免无范围检索。
尚未接入多轮会话或多模态 Agent。

在 `backend` 目录运行 `python -m scripts.check_embeddings` 可检查真实向量接口，命令只输出连接状态、模型、数量和维度，不输出密钥或向量内容。
运行 `python -m scripts.check_chat` 可用固定的合成句子检查 Qwen JSON 输出和引用校验。

更换模型、服务地址或维度后，旧向量不会与新查询混用。执行迁移和重建：

```powershell
docker compose exec api python -m scripts.reembed_documents
docker compose exec api python -m scripts.evaluate_retrieval
```

本地开发时，在 `backend` 目录执行：

```powershell
alembic upgrade head
python -m scripts.reembed_documents
python -m scripts.evaluate_retrieval --validate-only
python -m scripts.evaluate_retrieval
```

评测数据位于 `evals/retrieval-smoke-v1.json`，结果默认写入 `evals/reports/retrieval-latest.json`。
指标包括 Recall@10、nDCG@10、MRR、五分类 Macro-F1、危险误答计数和降级情况。
当前 13 条样本属于小规模冒烟集，缺少真实版本冲突等类别，报告会明确列出未覆盖类别；
它不能替代规划中的完整锁定验收集。`/search` 使用保守规则，`/answer` 使用结构化语义评估。

文本回答评测：

```powershell
python -m scripts.evaluate_answers --validate-only
python -m scripts.evaluate_answers --dataset ../evals/answer-demo-development-v1.json --output ../evals/reports/answers-demo.json
python -m scripts.evaluate_answers --output ../evals/reports/answers-synthetic.json
```

13 条演示开发样本实际执行数据库混合检索；24 条合成回归样本覆盖五分类、矛盾说明和提示注入。
另有 `answer-holdout-candidate-v1.json` 的 20 条新留出候选样本，不能用它调优 Prompt。
报告记录数据集摘要、Prompt 版本、模型配置、分类、金标原文的引用精确率/召回率和端到端正确率。
已观察的失败样本只能作为回归集，不能重复调参后声称是独立盲测。
这些标签由开发代理编写，仍需独立人工审核及新的锁定验收集；报告不会自动宣称阶段三验收通过。
审核说明见 `evals/HUMAN_REVIEW.md`。在 `backend` 执行 `python -m scripts.check_retrieval_filters`
可使用自动回滚的合成记录，验证真实数据库的产品/型号/版本/语言过滤及向量空间、归档隔离。

没有向量服务时可显式设置 `EMBEDDING_PROVIDER=hash` 验证工程链路，报告会标记该模式不提供语义检索。
API 和 Celery worker 必须使用相同配置。向量接口失败时检索可降级至 BM25，失败入库任务不会发布索引。

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
