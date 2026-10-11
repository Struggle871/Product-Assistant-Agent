# 产品使用助手 Agent 技术选型学习文档

## 1. 文档说明

本文根据最新的 `docs/PROJECT_PLAN.md` 整理项目的技术选型，重点回答两个问题：

1. 每个技术领域有哪些常见方案？
2. 当前项目为什么选择其中一种方案？

`PROJECT_PLAN.md` 在本文中只作为项目设计和约束的参考资料。本文不是对原设计的替代，也不新增产品范围。所有选型都围绕当前项目的目标展开：本地单用户部署、文字/图片/音频输入、ASR 转写确认、图文音多模态融合、混合 RAG、官方 Web Search、LangGraph 工作流、DeepAgents 复杂研究、长期记忆、可追踪和可测试。

本次修订特别补充了音频链路。项目中的语音不是“直接把音频交给聊天模型”，而是：

```text
浏览器录音或音频上传
  → 音频安全校验与 MinIO 保存
  → SpeechRecognizer/ASR 转写
  → 分段、时间戳、置信度和型号字段检查
  → 必要时暂停，请用户编辑或确认转写
  → 与文字、图片观察、已批准记忆融合
  → 产品身份解析、RAG 和回答
```

语音合成和实时语音通话仍然不是当前项目范围。ASR 只负责把音频转换成可审查的用户输入，不负责回答问题，也不能绕过 LangGraph 的确认和安全门禁。

## 2. 先理解项目的选型原则

这个项目不是单纯的聊天机器人，而是一个“有证据约束的多模态产品知识助手”。因此选型时优先考虑：

- 是否能明确控制流程，而不是完全依赖模型自由发挥；
- 是否能保存暂停、恢复、重试和降级状态；
- 是否方便同时处理结构化数据、向量检索和关键词检索；
- 是否能限制网页、子 Agent 和模型的权限；
- 是否能区分原始音频、ASR 转写、用户编辑文本和最终证据；
- 是否能在 ASR 失败或低置信度时让图片和文字路径继续工作；
- 是否适合 Docker Compose 一键启动和面试演示；
- 是否有清晰的替换边界，避免业务代码绑定某一家模型或搜索供应商；
- 是否便于自动测试、评测和追踪问题。

一个重要原则是：技术选型不是简单比较“谁功能最多”，而是比较“谁最适合当前的边界、复杂度和交付目标”。

## 3. 前端技术选型

### 3.1 前端框架：React

常见方案：

- React：组件生态成熟，适合构建复杂交互界面；
- Vue：上手成本较低，模板语法直观；
- Angular：框架约束完整，适合大型企业应用；
- Svelte/SvelteKit：运行时较轻，开发体验简洁；
- Next.js：在 React 基础上提供服务端渲染、路由和全栈能力。

当前选择：React。

选择理由：

- 项目需要聊天流、来源抽屉、图片上传、录音、身份确认、澄清恢复、记忆管理和知识库管理等多个交互区域，React 的组件化方式适合拆分这些功能；
- 生态中对 SSE、文件上传、表单、可访问性和测试的支持成熟；
- 当前后端已经由 FastAPI 提供 API，前端不需要再引入 Next.js 的服务端能力；
- 使用纯 React 可以让前后端边界更清楚，减少“前端框架同时承担后端职责”的复杂度。

学习重点：组件拆分、受控表单、异步状态、错误边界、文件上传、流式消息渲染和可访问性。

### 3.2 前端语言：TypeScript strict

常见方案：JavaScript、TypeScript 宽松模式、TypeScript strict、Flow。

当前选择：TypeScript strict。

选择理由：

- SSE 事件是多个带类型的数据结构，例如 `run.started`、`evidence.added`、`clarification.required` 和 `run.completed`；严格类型可以减少事件字段写错；
- OpenAPI 自动生成的类型可以和后端接口保持一致；
- 图片观察、候选型号、引用、记忆提案等对象字段较多，strict 模式能尽早发现空值和分支遗漏；
- TypeScript 的生态和团队招聘普及度高，便于面试讲解和后续维护。

### 3.3 构建工具：Vite

常见方案：Vite、Webpack、Rspack、Rsbuild、Next.js 内置构建工具。

当前选择：Vite。

选择理由：

- 当前前端是独立 React 应用，不需要服务端渲染；
- 开发启动快，配置量少，适合快速迭代面试演示界面；
- 与 TypeScript、Vitest、ESLint 和 Playwright 的组合自然；
- 不把构建、路由和服务端渲染等额外职责引入项目。

### 3.4 服务端数据请求：TanStack Query

常见方案：原生 `fetch`、Axios、自定义 Hooks、SWR、TanStack Query、Redux Toolkit Query。

当前选择：TanStack Query，底层 HTTP 客户端可以使用原生 `fetch` 或轻量封装。

选择理由：

- 会话、运行状态、记忆列表、文档状态和反馈数据都属于服务端状态，而不是普通 UI 状态；
- TanStack Query 提供缓存、失效、重试、加载状态和并发请求管理；
- 它和 Zustand 的职责边界清楚：Query 管服务端数据，Zustand 管界面和本地交互状态；
- 不必为了几个全局数据对象引入完整 Redux 架构。

### 3.5 前端本地状态：Zustand

常见方案：React Context、Redux Toolkit、Zustand、Jotai、MobX。

当前选择：Zustand。

选择理由：

- 需要保存当前会话、SSE 连接状态、选中的产品候选、来源抽屉状态、录音状态和界面偏好；
- Zustand API 简单、样板代码少，适合中等规模的单页应用；
- React Context 适合低频全局配置，不适合高频流式事件更新；
- Redux Toolkit 能提供更强的约束，但当前项目并不需要为此承担更高的状态样板成本。

### 3.6 包管理器：pnpm

常见方案：npm、Yarn、pnpm、Bun。

当前选择：pnpm。

选择理由：

- 节省磁盘空间，安装速度较好；
- 对 workspace 和共享类型包支持自然，适合单仓库结构；
- 依赖隔离更严格，能减少“依赖被隐式提升后本地能运行、CI 不能运行”的问题；
- Bun 速度有优势，但在面试成品中优先考虑生态稳定性和团队可复现性。

### 3.7 流式传输：SSE

常见方案：短轮询、长轮询、SSE、WebSocket、WebTransport。

当前选择：SSE。

选择理由：

- 当前主要是服务端向浏览器推送 Agent 进度、回答增量、证据和状态事件，通信方向以单向为主；
- SSE 基于 HTTP，代理、负载均衡和浏览器调试支持通常比 WebSocket 简单；
- `Last-Event-ID` 可用于断线续传，适合项目要求的事件恢复；
- 用户恢复、取消等操作仍然可以使用普通 HTTP API；
- WebSocket 更适合双向高频实时协作，当前语音实时通话也不在产品范围内。

## 4. 后端与 API 技术选型

### 4.1 后端语言：Python 3.12

常见方案：Python、Node.js/TypeScript、Go、Java/Kotlin、C#。

当前选择：Python 3.12。

选择理由：

- AI、Embedding、ASR、视觉模型、RAG 和评测工具的 Python 生态最完整；
- LangGraph、DeepAgents、Pydantic、SQLAlchemy 和 Celery 可以在同一技术栈内协作；
- 适合快速编写模型适配器、检索实验和评测脚本；
- 当前场景不是高吞吐网关，也不需要用 Go 或 Java 解决极端并发问题；
- 通过异步 I/O、任务队列和明确的超时控制，可以满足本地演示与测试要求。

### 4.2 Web 框架：FastAPI

常见方案：FastAPI、Django、Flask、Starlette、Node.js NestJS/Express。

当前选择：FastAPI。

选择理由：

- 原生支持异步路由，适合模型调用、检索、SSE 和外部 Web Search；
- 基于 Pydantic 自动生成请求校验和 OpenAPI 文档；
- 路由层、依赖注入、后台任务和测试客户端都足够成熟；
- Django 功能更完整，但会带来当前项目不需要的后台管理和 ORM 约束；
- Flask 更轻，但需要手动补充类型校验、OpenAPI 和异步相关能力。

### 4.3 数据模型校验：Pydantic

常见方案：Pydantic、dataclasses、attrs、Marshmallow、手写校验。

当前选择：Pydantic。

选择理由：

- API 请求、Agent 状态、结构化模型输出、证据评估和 SSE 事件都需要可靠校验；
- 能把模型输出解析失败变成明确错误，从而触发“修复一次后降级”的策略；
- 与 FastAPI 集成紧密；
- 可以把 `ResearchRequest`、`ResearchResult`、`EvidenceAssessment` 等契约写成可读的模型。

### 4.4 API 契约：OpenAPI 自动生成 TypeScript 类型

常见方案：手工维护前后端接口、OpenAPI、GraphQL、tRPC、Protocol Buffers/gRPC。

当前选择：OpenAPI 作为唯一 HTTP 契约。

选择理由：

- 项目以 HTTP API 和 SSE 为主，OpenAPI 能覆盖常规请求、响应、错误结构和参数说明；
- 可以从 FastAPI 生成规范，再自动生成前端 TypeScript 类型；
- 避免前后端分别维护两套请求模型；
- GraphQL 更适合前端自由组合查询，但会增加缓存、权限、错误和流式设计复杂度；
- gRPC 更适合服务间通信，当前单体/模块化单仓库不需要以它作为浏览器主协议。

## 5. Agent 编排与模型接入

### 5.1 全局工作流：LangGraph

常见方案：手写状态机、LangChain AgentExecutor、LangGraph、Semantic Kernel、AutoGen、CrewAI、Temporal 等工作流平台。

当前选择：LangGraph。

选择理由：

- 项目有明确的状态节点、条件边、并行分支、暂停、恢复、循环上限和错误降级；
- `interrupt()` 与 `Command(resume/goto/update)` 适合“等待用户确认型号”这类人机协作流程；
- Checkpoint 可以保存中断前状态，进程重启后仍可恢复；
- 能把本地检索和 Web Search 做成可审计的 fan-out/fan-in 流程；
- 相比完全自主的 Agent 循环，LangGraph 更容易定义业务边界和测试路径；
- Temporal 等通用工作流系统可靠性很强，但对当前本地面试成品而言基础设施和实现成本偏高。

学习重点：状态定义、reducer、条件边、并行节点、interrupt/resume、Checkpoint、重试、超时和图测试。

### 5.2 复杂研究执行：DeepAgents

常见方案：手写 ReAct 循环、LangChain Agent、AutoGen、CrewAI、DeepAgents、完全确定性的多步服务编排。

当前选择：DeepAgents 作为 LangGraph 控制下的受限 research 子图。

选择理由：

- 复杂问题需要 Todo 规划、专业子 Agent、Skills、上下文摘要、虚拟文件系统和大型工具结果卸载；
- 这些能力如果全部手写，会产生大量通用 Agent 基础设施代码，且容易出现上下文污染和权限遗漏；
- DeepAgents 可以提供现成的 Agent Harness，同时由 LangGraph 控制进入条件、工具白名单、预算和最终发布门禁；
- 简单问题仍然走 DIRECT 确定性路径，避免所有请求都使用多 Agent 导致延迟和成本上升；
- 这不是让 DeepAgents 自主决定产品身份、Web 授权或长期记忆写入，而是将它限制为“复杂研究执行器”。

学习重点：Supervisor、task 委派、子 Agent 最小权限、Skills 渐进加载、CompositeBackend、结构化输出和预算控制。

### 5.3 短期状态与长期记忆：LangGraph PostgreSQL Checkpointer + PostgreSQL Store

常见方案：内存、SQLite、Redis、MongoDB、自建会话表、LangGraph Checkpointer/Store。

当前选择：

- 当前 thread 状态使用 LangGraph PostgreSQL Checkpointer；
- 跨 thread 的长期记忆使用 LangGraph PostgreSQL Store；
- 业务可编辑、可审计的记忆仍保存到业务表；
- DeepAgents 使用 CompositeBackend 路由临时文件、长期记忆和只读 Skills。

选择理由：

- Checkpoint 解决“这一次运行进行到哪里”；Store 解决“这个用户跨会话记住什么”，两个问题需要分开；
- PostgreSQL 与业务数据库共用基础设施，适合 Docker Compose 和本地演示；
- 业务表保留用户可查看、纠正、删除和审计的权威记录，避免把框架内部 Store 当成唯一业务真相；
- Redis 适合短期缓存和队列，但不适合作为长期可审计记忆的唯一存储；
- 内存和 SQLite 难以覆盖重启恢复、并发和跨会话隔离要求。

### 5.4 模型网关：统一 ModelGateway 适配层

常见方案：业务代码直接调用厂商 SDK、使用 LiteLLM 等统一代理、自建 `ModelGateway`、每种模型各写一套服务。

当前选择：在业务层定义统一 `ModelGateway`，由适配器调用具体供应商或本地模型。

选择理由：

- Chat、Vision、Embedding、Reranker 和 ASR 的供应商可能不同；
- 业务节点只依赖 `chat`、`embed`、`vision` 等稳定接口，便于切换模型；
- 可以统一记录超时、重试、模型版本、供应商、Token 和成本；
- 可以为本地测试提供 Fake Gateway，不必每次运行都调用真实模型；
- LiteLLM 可以作为实现选项，但不能替代项目自己的业务级错误处理、结构化校验和权限边界。

### 5.5 语音输入方式：浏览器录音或音频文件上传

常见方案：浏览器 `MediaRecorder` 录音、直接上传 WAV/MP3/M4A/WebM、浏览器 Web Speech API、实时 WebRTC 音频流、第三方录音组件。

当前选择：支持浏览器录音和音频文件上传，前端展示时长、大小和播放控件，后端统一写入 MinIO 后再异步或受控调用 ASR。

选择理由：

- 两种入口能覆盖“按住说话”和“已有录音文件”两类使用场景；
- 音频先成为可管理的 `AudioAsset`，后续可以做 MIME、编码、时长、采样率、声道和保留期校验；
- 不采用 Web Speech API 作为唯一方案，因为浏览器兼容性、供应商行为和可测试性不稳定；
- 不采用 WebRTC 实时流，因为实时语音通话明确不在当前产品范围；
- 音频和转写可以分别删除，满足会话删除和隐私控制要求。

### 5.6 ASR 引擎：云端、本地与混合部署

常见方案：

- 云端 ASR API：接入快，通常有较好的中文、英文和标点能力；
- 本地 Whisper/faster-whisper：数据不出本机，可离线运行，但需要 CPU/GPU 和模型管理；
- 浏览器 Web Speech API：前端实现简单，但依赖浏览器和平台能力；
- 云端主用、本地兜底或按隐私策略路由的混合方案。

当前选择：通过统一 `SpeechRecognizer` 适配层支持可配置的云端或本地 ASR，具体供应商不写死在业务流程中。

选择理由：

- 面试演示可以使用云端 ASR 快速获得稳定效果，也能在网络不可用或隐私要求较高时切换本地模型；
- 项目真正依赖的是统一转写契约，而不是某一家供应商：语言、原始文本、规范化文本、分段、词级时间戳、置信度、模型版本和错误状态；
- 适配层便于写 Fake ASR 做单元测试和故障注入；
- 混合方案的路由策略可按语言、音频时长、服务可用性和隐私设置扩展；
- 当前不把实时流式 ASR 作为必需能力，因为产品验收重点是“上传/录音 → 转写确认 → 问题理解”。

### 5.7 ASR 输出与转写确认

常见方案：直接使用整段文本、只保留最终文本、保存分段文本、保留词级时间戳和置信度、完全由模型自动纠错。

当前选择：保存原始转写、规范化转写、分段/词级时间戳、置信度、语言、模型版本和用户确认/编辑状态。

选择理由：

- `AX55` 与 `H55`、数字与字母、错误码和菜单名称容易发生 ASR 混淆，不能只保留一段不可追溯文本；
- 低置信度、多个型号候选、字母数字混淆或否定词歧义时，LangGraph 进入 `WAITING_FOR_USER`，展示可编辑转写；
- 用户确认后的文本才进入产品身份解析和检索；未经确认的转写最多作为待确认上下文，不能直接作为产品过滤条件或操作事实；
- 原始文本不能被规范化结果覆盖，方便调试、评测和用户纠错；
- ASR 本身不是知识证据，回答必须区分“用户语音描述”和“官方资料支持的结论”。

推荐的转写状态：`PENDING`、`COMPLETED`、`NEEDS_CONFIRMATION`、`FAILED`、`REJECTED`。

### 5.8 音频安全与隐私

常见方案：只检查扩展名、信任客户端 MIME、上传后直接送第三方 ASR、原始音频长期保存、把音频和文本全部写入日志。

当前选择：服务端依据文件签名检测真实类型，只允许配置的 WAV/MP3/M4A/WebM 等编码和容器，并限制文件大小、总时长、采样率、声道数和解码后大小；调用第三方 ASR 前移除不必要元数据，日志和 Trace 不保存原始音频内容。

选择理由：

- 扩展名和客户端 MIME 可以伪造，必须用真实媒体检测避免畸形音频和超大解码结果；
- 音频可能包含个人信息，原始音频和转写文本应有不同的删除、保留和脱敏策略；
- ASR 转写和用户编辑文本都属于不可信用户输入，必须做长度限制、Prompt 分隔和敏感信息处理；
- 语音中的“忽略之前规则”或“打开某链接”只是用户内容，不能改变系统提示词或工具权限；
- 音频默认按会话保留策略保存，并支持单独删除和随会话级联删除。

### 5.9 图片和视觉理解

常见方案：通用多模态大模型、专用 OCR/目标检测、纯图像分类、云端视觉 API、本地视觉模型。

当前选择：通过统一模型网关调用视觉模型，并结合 OCR、产品目录匹配和确定性的身份确认流程。

选择理由：

- 通用视觉模型适合从产品图片中提取品牌、型号、标签、错误码和外观观察；
- OCR 可以处理铭牌、屏幕文字和序列化字段，弥补纯视觉模型对小文字的不足；
- 视觉模型只能产生候选和观察，不能直接决定最终产品身份；最终确认必须经过产品目录和强证据匹配；
- 纯分类模型难以覆盖不同品牌、型号和新产品；
- “视觉观察”和“业务确认”分离，有利于避免高置信度幻觉传播到检索和记忆。

### 5.10 多模态上下文融合：来源标记 + 确定性冲突处理

常见方案：把所有模态直接拼成一个 Prompt、由多模态模型自行决定优先级、先分别解析再由规则和模型融合、使用专门的多模态向量空间。

当前选择：先分别处理文字、已确认 ASR 转写和图片观察，再由 `MultimodalContextFuser` 生成带来源标记的统一上下文。

统一上下文至少区分：

```text
USER_TEXT          用户键入的原文
ASR_TRANSCRIPT     用户确认后的语音转写
IMAGE_OBSERVATION  图片模型提取的观察
MEMORY_CONTEXT     已批准且与当前问题相关的长期记忆
```

选择理由：

- 语音描述的是症状、时间顺序和环境，图片提供型号标签、屏幕文字和指示灯观察，两者证据性质不同；
- 直接把多种内容拼接进 Prompt，容易让模型把用户猜测当成产品事实，或静默覆盖冲突；
- 当前项目需要明确的冲突优先级：用户当前明确纠正 > 用户确认的转写/文字 > 标签 OCR 和目录匹配 > 图片外观观察 > 历史记忆候选；
- 冲突不能由模型悄悄解决，必须进入身份确认或上下文澄清节点；
- 语音、图片和文字可以独立失败：ASR 失败时继续使用图片和文字，视觉失败时继续使用已确认文字和语音。

这个设计的核心不是“让模型看更多输入”，而是让每个结论都能回答“来自哪种模态、是否经过用户确认、是否有官方资料支持”。

## 6. 数据库、检索与 RAG

### 6.1 关系数据库：PostgreSQL

常见方案：PostgreSQL、MySQL、SQLite、MongoDB、云数据库。

当前选择：PostgreSQL。

选择理由：

- 需要保存会话、消息、运行、证据、引用、文档、索引版本、记忆和审计记录等关系数据；
- 事务、约束、JSON 字段、全文能力和扩展生态完整；
- 可以同时承载 pgvector、BM25 扩展、LangGraph Checkpoint 和 Store；
- 单机 Docker Compose 下运行简单，未来也可迁移到托管 PostgreSQL；
- MongoDB 更适合文档型数据，但本项目的身份、版本、引用、权限和审计关系较多。

### 6.2 向量检索：pgvector

常见方案：pgvector、Milvus、Qdrant、Weaviate、Elasticsearch/OpenSearch 向量检索、云向量数据库。

当前选择：pgvector。

选择理由：

- 当前知识库规模是固定演示产品和公开资料，不需要单独维护一个向量数据库集群；
- 向量、文档元数据、产品型号、版本和权限过滤可以放在同一个 PostgreSQL 事务边界内；
- Docker Compose 部署更简单，备份和开发环境更容易复现；
- 当规模显著增长或需要分布式向量检索时，可以通过 `Retriever` 接口替换为 Qdrant 或 Milvus；
- 当前目标是可靠的混合检索和可解释过滤，不是追求超大规模向量吞吐。

### 6.3 关键词检索：PostgreSQL BM25 扩展

常见方案：PostgreSQL 全文检索、BM25 扩展、Elasticsearch、OpenSearch、专用搜索引擎、数据库 `LIKE`。

当前选择：PostgreSQL BM25 扩展，与 pgvector 并存。

选择理由：

- 产品型号、错误码、菜单名称和版本号对精确关键词匹配非常敏感；
- 仅使用向量检索可能把相似但不同型号的内容召回；
- BM25 对关键词频率和文档长度有较好的排序解释性；
- 和向量结果通过 RRF 融合，可以兼顾语义召回与精确术语匹配；
- Elasticsearch/OpenSearch 功能更强，但会增加一个需要部署、监控、备份和同步的基础设施。

### 6.4 混合检索：向量 + BM25 + RRF + 可选 Reranker

常见方案：只做向量检索、只做关键词检索、加权融合、RRF、Cross-Encoder Reranker、商业 Reranker API。

当前选择：向量召回和 BM25 召回并行，通过 RRF 融合，必要时再使用 Reranker。

选择理由：

- 产品问答同时包含自然语言描述和必须精确匹配的型号、错误码、版本号；
- RRF 不要求不同检索器的分数处于同一量纲，工程实现稳定；
- Reranker 可以作为质量增强，而不是系统唯一依赖；
- Reranker 失败时回退到 RRF，符合项目的明确降级设计；
- 检索结果保存证据 ID、来源位置和元数据，便于引用验证和离线评测。

### 6.5 切片与元数据

常见方案：固定字符切片、按 token 切片、按标题/段落切片、语义切片、整页保存。

当前选择：结构化切片，并绑定产品、型号、版本、平台、文档和页码/段落位置等元数据。

选择理由：

- 操作步骤和警告信息不能被随意切断；
- 元数据过滤可以阻止不同型号资料混入当前答案；
- 页码、段落和原始 URL 可以支撑用户可验证引用；
- 固定演示产品适合先建立可评测的基线，再根据召回指标调整切片策略。

## 7. Web Search 与安全抓取

### 7.1 搜索服务：Tavily Search API + 自定义适配层

常见方案：Tavily、Bing Web Search、Google Programmable Search、SerpAPI、Brave Search、自建爬虫。

当前选择：Tavily，通过自定义 Adapter 接入。

选择理由：

- 项目需要面向研究型问答的搜索结果，而不是完整通用搜索引擎；
- Adapter 可以统一来源过滤、查询记录、超时、错误和供应商替换；
- Web Search 只搜索公开官方资料，不能绕过可信来源注册表；
- 自建爬虫需要自行处理排名、限流、验证码、版权和维护成本，不适合当前交付范围；
- 无搜索服务时，系统必须退回本地证据并明确说明无法获取最新信息。

### 7.2 网页抓取安全

常见方案：直接请求 URL、使用搜索服务返回摘要、沙箱抓取器、带 SSRF 防护的安全抓取器。

当前选择：带 URL 规范化、可信主机校验、DNS/IP 校验、重定向限制、响应大小限制和内容类型限制的安全抓取器。

选择理由：

- 搜索结果中的 URL 不能直接视为可信；
- 必须阻止回环、私有地址、链路本地地址、云元数据地址、DNS rebinding、非 HTTPS 和恶意跳转；
- 网页正文和上传文档都可能包含 Prompt Injection，抓取内容只能作为不可信证据，不能改变系统指令或工具权限；
- 安全规则应作为确定性服务执行，不能交给模型自行判断。

## 8. 文件、缓存与异步任务

### 8.1 对象存储：MinIO，生产可替换为 S3

常见方案：本地文件系统、MinIO、Amazon S3、阿里云 OSS、Azure Blob Storage。

当前选择：开发和面试环境使用 MinIO，生产环境可替换为 S3 兼容对象存储。

选择理由：

- 音频、图片、PDF 和原始文档不适合直接放进 PostgreSQL；
- MinIO 提供 S3 兼容接口，适合 Docker Compose 一键启动；
- 通过对象存储适配层可以平滑迁移到云端 S3；
- 对象键、文件大小、内容类型、保留时间和删除策略可以统一控制；
- 不把用户上传文件写进 Agent 可写的主机文件系统。

音频对象和转写记录分开管理：`AudioAsset` 保存对象键、真实 MIME、编码、时长、采样率、声道数、大小和保留时间；`Transcription` 保存 ASR 供应商、模型、语言、原始文本、规范化文本、置信度、状态和用户是否确认；`TranscriptionSegment` 保存可定位的分段和词级时间信息。这样可以单独删除音频，也可以保留经用户确认的文本审计记录。

### 8.2 缓存与事件暂存：Redis

常见方案：Redis、Memcached、RabbitMQ、Kafka、数据库轮询。

当前选择：Redis，用于缓存、Celery Broker/Result Backend 的配合，以及 SSE 事件流的短期保留。

选择理由：

- 需要缓存搜索结果、短期运行状态和 24 小时内的 SSE 事件；
- Redis 数据结构适合 Stream、过期时间和轻量队列场景；
- 当前规模不需要 Kafka 的分区、消费组和长期日志能力；
- Redis 不是最终事实来源，运行终态、最终答案和审计数据仍写入 PostgreSQL。

### 8.3 异步任务：Celery

常见方案：同步执行、FastAPI BackgroundTasks、Celery、RQ、Dramatiq、Arq、Kafka 消费者。

当前选择：Celery + Redis。

选择理由：

- 文档解析、OCR、Embedding、索引重建可能耗时较长，不应阻塞 API 请求；
- Celery 有成熟的重试、任务状态和定时任务能力；
- 文档入库需要幂等、失败重试和活动索引原子切换，Celery 适合表达这类后台任务；
- FastAPI BackgroundTasks 更适合轻量任务，进程重启时可靠性不足；
- Kafka 对当前单机面试成品过重，未来若演化为事件驱动平台再考虑。

## 9. 数据访问、迁移与部署

### 9.1 ORM 与迁移：SQLAlchemy 2 + Alembic

常见方案：SQLAlchemy、Django ORM、SQLModel、Tortoise ORM、手写 SQL；迁移可用 Alembic、Django Migrations 或 Flyway。

当前选择：SQLAlchemy 2 + Alembic。

选择理由：

- SQLAlchemy 对 PostgreSQL、异步访问、复杂查询和扩展支持成熟；
- 业务领域模型可以和框架内部 Checkpoint/Store 表保持边界；
- Alembic 能把数据库结构变化版本化，适合 CI 和全新环境初始化；
- 不让 ORM 自动隐藏向量、BM25、索引版本和事务边界等重要数据库行为。

### 9.2 部署：Docker Compose

常见方案：本机直接安装、Docker Compose、Kubernetes、Docker Swarm、云容器平台、Serverless。

当前选择：Docker Compose。

选择理由：

- 项目交付目标是可复现的面试成品，而不是高可用生产集群；
- 前端、后端、PostgreSQL、Redis、MinIO 和 Celery 可以一条命令启动；
- 环境隔离和依赖版本更容易统一；
- Kubernetes 对服务发现、滚动发布和弹性伸缩很强，但超出当前产品范围，会分散对核心 Agent/RAG 能力的学习；
- 未来迁移 Kubernetes 时，容器化边界仍然可以复用。

### 9.3 身份与访问：签名 HttpOnly Cookie + 管理员 API Key

常见方案：JWT、OAuth/OIDC、Session Cookie、匿名设备 ID、完整用户账号系统。

当前选择：本地单用户场景使用服务端签发的稳定匿名 `user_subject_id`，以签名、HttpOnly、SameSite Cookie 保存；知识库管理接口使用环境变量中的 `ADMIN_API_KEY` 换取短期管理会话。

选择理由：

- 当前产品不是多租户 SaaS，不需要为了演示引入完整注册、登录、OIDC 和账号体系；
- 身份由服务端签发，浏览器不能自行指定其他用户的记忆命名空间；
- HttpOnly Cookie 降低脚本直接读取身份凭据的风险；
- 管理密钥不进入前端包、浏览器持久化和 Agent 上下文；
- 未来升级为多用户系统时，可在身份适配层替换为 OAuth/OIDC。

## 10. 工程质量、测试与可观测性

### 10.1 Python 质量工具

常见方案：Flake8 + Black + isort、Ruff、Mypy、Pyright、Pylint。

当前选择：Ruff + Pyright + Pytest。

选择理由：

- Ruff 将大量 lint 和格式化能力集中到一个高速工具中；
- Pyright 对类型检查和异步代码边界有较好支持；
- Pytest 适合单元、集成、故障注入和异步测试；
- 工具少而职责清楚，降低 CI 配置复杂度。

### 10.2 前端质量工具

常见方案：ESLint、Biome、Jest、Vitest、Cypress、Playwright。

当前选择：ESLint、Vitest、Playwright。

选择理由：

- ESLint 生态成熟，适合 React 和 TypeScript 规则；
- Vitest 与 Vite 配合自然，适合组件和工具函数测试；
- Playwright 适合覆盖完整浏览器链路：上传图片、确认型号、接收 SSE、恢复运行、查看引用和删除记忆；
- 只做单元测试无法证明多轮暂停恢复和浏览器交互真正可用。

### 10.3 可观测性：OpenTelemetry + 结构化日志 + Langfuse

常见方案：只打日志、Prometheus/Grafana、OpenTelemetry、LangSmith、Langfuse、Datadog、Jaeger。

当前选择：OpenTelemetry 作为通用 Trace 基础，配合结构化日志，Langfuse 作为可配置的 LLM Trace 后端。

选择理由：

- 一次回答可能经过 API、LangGraph 节点、DeepAgents 子 Agent、检索、Web Search、模型和数据库，需要跨组件关联；
- OpenTelemetry 让 Trace、Span、错误和耗时不绑定单一厂商；
- Langfuse 更适合记录 Prompt、模型、Token、成本、评测版本和 LLM 调用细节；
- 结构化日志便于本地 Docker 环境快速排查；
- Trace 中必须脱敏长期记忆和密钥，不能把隐藏推理当作产品输出。

### 10.4 CI：GitHub Actions

常见方案：GitHub Actions、GitLab CI、Jenkins、CircleCI、本地脚本。

当前选择：GitHub Actions。

选择理由：

- 代码仓库和 Pull Request 流程天然集成；
- 可执行 Ruff、Pyright、ESLint、单元测试、集成测试、E2E 和快速评测集；
- 适合保存评测报告和测试产物；
- Jenkins 更灵活，但需要额外维护服务器和插件。

### 10.5 音频和多模态质量评测

常见方案：只测试最终答案、只测试 ASR 的整体 WER/CER、人工抽查、按模态和关键实体分别评测。

当前选择：同时评测 ASR、关键字段、确认触发、模态融合和端到端答案质量。

重点指标包括：

- 整体和关键字段 CER/WER；
- 品牌、型号、版本、错误码和菜单名称的实体准确率；
- 语言识别准确率；
- 低置信度样本正确触发转写确认率；
- 用户编辑率、重录率和 ASR 失败率；
- ASR 首字延迟、完整转写延迟和端到端延迟；
- 图文音冲突是否正确进入澄清，而不是静默覆盖；
- ASR 失败后图片/文字路径是否仍可完成回答；
- 回答是否区分语音描述、图片观察和官方资料引用。

选择理由：

- ASR 的 WER 低，不代表型号和错误码识别正确；
- 多模态系统的风险通常发生在“融合和路由”阶段，而不是单一模型输出阶段；
- 将语音案例、图文音组合案例、低置信度案例和不可回答案例加入锁定测试集，才能验证产品边界没有被模型绕过。

## 11. 关键选型之间的协作关系

这些技术不是孤立选择，而是形成一条完整链路：

1. React + TypeScript 负责文字输入、录音/音频上传、转写编辑确认、图片上传和结果展示；
2. FastAPI + OpenAPI 提供稳定的 HTTP 契约，SSE 推送音频上传、ASR、转写确认、模态融合和回答事件；
3. LangGraph 保存主流程状态，决定 ASR 是否需要确认、何时暂停、从哪里恢复、如何检索和通过发布门禁；
4. `SpeechRecognizer` 将云端或本地 ASR 统一成结构化转写，`MultimodalContextFuser` 保留文字、语音、图片和记忆的来源标记；
5. DeepAgents 只在复杂研究节点中负责规划、子 Agent 协作和上下文管理，不负责音频确认或产品身份最终确认；
6. PostgreSQL 保存业务事实，pgvector 和 BM25 提供混合召回；用户确认后的转写可以作为查询上下文，但不能单独作为产品事实证据；
7. MinIO 保存音频、图片和原始资料，Redis 保存短期缓存和事件，Celery 执行文档解析、OCR、Embedding 和索引任务；
8. OpenTelemetry、结构化日志和 Langfuse 记录一次运行的完整证据链，但不记录原始音频内容；
9. Pytest、Vitest、Playwright 和按模态划分的评测集验证功能、可靠性和答案质量。

其中最关键的边界是：

- 模型负责理解和生成候选，不负责越权改变业务状态；
- LangGraph 负责“下一步做什么、何时暂停、失败如何恢复”；
- DeepAgents 负责“复杂研究任务如何拆解和执行”；
- 数据库负责业务事实和审计，Redis 不作为最终事实来源；
- Web 页面和上传文档是证据来源，不是系统指令；
- 视觉模型猜测不能直接成为产品身份或长期记忆；
- ASR 转写不能直接成为产品型号、错误码或操作步骤的事实证据；
- 每个回答都应能区分用户当前输入、音频转写、图片观察、长期记忆和官方文档证据。

## 12. 建议学习顺序

### 第一阶段：工程基础

学习 Python 3.12、TypeScript strict、Git、Docker Compose、HTTP、JSON、SSE、PostgreSQL 基础和 SQLAlchemy/Alembic。

目标是能够独立启动项目、定义 API、读写数据库、上传文件并返回流式事件。

### 第二阶段：前后端交互与音频输入

学习 React 组件、TanStack Query、Zustand、OpenAPI 类型生成、SSE 重连、`MediaRecorder`、音频上传、播放器和 Playwright。

目标是完成一个可以上传图片和音频、显示音频时长、播放录音、编辑/确认转写、创建运行、显示阶段进度和展示引用的前端。

### 第三阶段：RAG

学习文档解析、结构化切片、Embedding、向量检索、BM25、RRF、Reranker、元数据过滤和引用定位。

目标是先完成没有 Agent 的本地知识问答，并用固定评测集验证召回质量。

### 第四阶段：LangGraph

学习 State、Node、Edge、Reducer、Checkpoint、interrupt、resume、错误边、并行分支和状态测试。

目标是实现“缺型号时暂停，用户补充后从正确节点恢复”的可重复流程。

### 第五阶段：DeepAgents 与上下文工程

学习 Todo、task 委派、子 Agent、Skills、虚拟文件系统、CompositeBackend、摘要、结果卸载和结构化输出。

目标是让复杂研究进入受限子图，并确保子 Agent 不能越过工具白名单和发布门禁。

### 第六阶段：多模态、Web Search 与安全

学习 ASR、MediaRecorder、音频编码与媒体安全、OCR、视觉模型、产品身份解析、来源标记、SSRF、DNS rebinding、Prompt Injection、网页证据可信度和降级策略。

目标是做到“能识别候选，但不会仅凭图片或未经确认的语音自动确认；能联网，但不会信任或执行网页、音频转写中的指令”。

### 第七阶段：质量与交付

学习 OpenTelemetry、LLM Trace、评测集设计、LLM-as-Judge 校准、故障注入、成本统计和 CI 门禁。

目标是能够解释答案为什么成立、为什么拒答、哪里发生降级，以及如何用数据证明版本升级没有破坏质量。

## 13. 面试讲解时的简短总结

如果需要在面试中用一段话说明整体技术选型，可以这样表达：

> 前端使用 React、TypeScript、Vite、TanStack Query 和 Zustand，支持文字、图片和音频输入，并提供转写编辑确认。后端使用 Python、FastAPI 和 Pydantic，通过 OpenAPI 保持前后端契约一致，并用 SSE 推送音频上传、ASR、转写确认、多模态融合和 Agent 运行事件。系统级流程使用 LangGraph，因为它适合处理类型化状态、条件分支、暂停恢复、Checkpoint 和可靠性边界；复杂研究使用受 LangGraph 约束的 DeepAgents 子图，以获得 Todo、子 Agent、Skills 和上下文管理能力。语音通过 `SpeechRecognizer` 适配云端或本地 ASR，输出带语言、分段、时间戳、置信度和模型版本的结构化转写；低置信度转写必须由用户确认后才能进入身份解析和检索。数据层使用 PostgreSQL，同时用 pgvector 和 BM25 做混合检索，使用 RRF 和可选 Reranker 提升召回质量。MinIO 保存音频、图片和原始资料，Redis 支撑缓存和短期事件，Celery 处理文档入库。模型、视觉、语音和 ASR 都通过适配层接入，避免业务代码绑定供应商。部署采用 Docker Compose，质量和可观测性使用 Ruff、Pyright、Pytest、Vitest、Playwright、OpenTelemetry 和 Langfuse。整个选型的核心是可控、可恢复、可评测和可替换，而不是让模型获得无限权限。

## 14. 最终判断标准

后续如果要替换某项技术，不应只问“新工具是否更流行”，而应检查：

- 是否仍能保存并恢复业务状态；
- 是否能维持产品身份、版本和证据的隔离；
- 是否支持失败降级和可重复测试；
- 是否能保留当前 API、数据和模型适配边界；
- 是否增加了需要维护的基础设施；
- 是否真的改善了延迟、质量、成本或安全性。

只要替换方案不能改善这些核心指标，就没有必要为了追逐新技术而改变当前选型。
