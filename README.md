# School Guide · 校园智答

面向长沙工业学院校园与招生场景的独立知识库问答项目。系统将招生录取等结构化问题交给 PostgreSQL 精确查询，将学校概况、校园生活和图书馆等开放性问题交给 RAG 检索，并通过 SSE 流式返回带来源的回答。

> 本项目及其回答仅用于信息查询与技术展示。招生、收费及校园安排可能调整，重要信息请以学校官方最新通知为准。

## 功能

- **六类知识导航**：学校概况、学院专业、招生与学费、录取分数、校园生活、图书馆服务。
- **24 个快捷问题**：根据仓库现有知识资料配置，不在前端写死答案。
- **结构化精确查询**：招生计划、学费、投档分与位次解析到 PostgreSQL 表后按条件查询。
- **混合检索**：向量与 BM25 词法召回并行，RRF 融合后调用重排服务。
- **检索过滤与回退**：提取年份、省份、科类、专业和资料类型；过滤无结果时自动进行无过滤召回。
- **多轮对话**：结合最近对话改写追问，并自动选择结构化查询或 RAG。
- **知识库上传**：清洗、切分后增量写入索引，并同步结构化数据。
- **流式交互**：SSE 输出、停止生成、复制、重新生成、本地历史记录及移动端适配。

## 系统架构

```text
用户提问
   │
   ▼
FastAPI / QueryRouter
   ├─ 自包含的招生与录取问题 ──→ PostgreSQL 结构化查询
   ├─ 需要判断或结合上下文 ────→ LLM 意图路由
   └─ 开放性校园问题 ──────────→ 混合检索
                                  ├─ pgvector 语义召回
                                  ├─ PostgreSQL BM25 词法召回
                                  ├─ 元数据过滤与空结果回退
                                  └─ RRF 融合 + reranker
   │
   ▼
LLM 生成回答 ──→ SSE 流式响应 + 资料来源
```

知识库源文件位于 `backend/data/raw/`。录取分数和招生计划进入结构化表，其余资料进入向量与词法索引。上传新资料时使用增量索引，批量初始化和源文件整体更新时可运行全量同步脚本。

## 技术栈

| 模块 | 技术 |
|---|---|
| 前端 | Vue 3、TypeScript、Vite、Lucide、Marked、DOMPurify |
| API | FastAPI、Pydantic、Uvicorn、SSE |
| Agent / RAG | LangChain、上下文改写、混合检索、RRF、reranker |
| 数据 | PostgreSQL、pgvector、BM25、Redis |
| 文档处理 | Microsoft MarkItDown、文档清洗、分块上下文补全、元数据提取 |
| 部署 | Docker Compose、Nginx、宝塔面板 |

## 本地运行

环境要求：Python 3.12+、Node.js 18+、PostgreSQL 16 + pgvector；Redis 可选，异常时会降级。

### 1. 配置后端

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item backend/.env.example backend/.env
```

在 `backend/.env` 中填写 PostgreSQL、Redis、LLM、Embedding 和 reranker 配置。不要提交 `.env`、API Key 或数据库密码。

### 2. 初始化数据

```powershell
cd backend
python -m scripts.build_index
python -m scripts.import_structured
```

两个脚本均可重复运行：前者同步知识索引，后者重载招生与录取结构化数据。

### 3. 启动项目

```powershell
# 后端（backend 目录）
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端（另一个终端）
cd frontend
npm install
npm run dev
```

Vite 默认运行于 `http://127.0.0.1:5173`，并将 `/chat` 与 `/knowledge` 代理到本地后端。跨域部署时可在 `frontend/.env` 设置 `VITE_API_BASE_URL`。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/chat` | 非流式问答 |
| `POST` | `/chat/stream` | SSE 流式问答 |
| `POST` | `/knowledge/upload` | 上传并增量索引知识文档，最大 10 MB |
| `GET` | `/docs` | FastAPI 接口文档 |

## 验证

```powershell
cd frontend
npm run build

cd ../backend
python -m scripts.test_cleaner
python -m scripts.test_import_crawled
python -m scripts.test_metadata_filters
python -m scripts.test_structured
python -m scripts.evaluate_retrieval
```

部分脚本需要已配置的 PostgreSQL、Embedding 或 reranker 服务。

| 脚本 | 验证内容 |
|---|---|
| `test_cleaner.py` | 文档清洗规则 |
| `test_metadata_filters.py` | 元数据抽取与过滤推断 |
| `test_incremental_index.py` | 增量索引一致性 |
| `test_structured.py` | 结构化解析、入库与查询 |
| `test_retrieval.py` | 混合检索流程 |
| `evaluate_retrieval.py` | Recall、MRR、NDCG、Hit Rate |

## 目录结构

```text
backend/
├── app/
│   ├── agents/       # 查询路由与工具编排
│   ├── api/          # Chat、SSE、知识上传接口
│   ├── core/         # 配置、数据库、Redis、异常
│   ├── prompts/      # 系统与 RAG 提示词
│   ├── rag/          # 清洗、切分、索引、检索、重排
│   ├── services/     # LLM 与 RAG 服务
│   └── structured/   # 招生和录取数据解析与查询
├── data/raw/         # 知识库源文件
├── evals/            # 检索评估用例
└── scripts/          # 初始化、导入、测试和评估
frontend/
├── src/components/   # 校园问答与知识导航组件
├── src/data/         # 知识模块和快捷问题配置
└── src/services/     # Chat 与 SSE 客户端
deploy/               # Docker Compose、Dockerfile、Nginx 配置与部署指南
```

## 部署

仓库提供 Docker Compose 后端方案：PostgreSQL、Redis 和 FastAPI 运行于容器中，前端构建产物由 Nginx 提供，`/chat` 与 `/knowledge` 反向代理到仅监听本机的后端端口。

完整步骤、Nginx SSE 配置、初始化和维护命令见 [`deploy/DEPLOY.md`](deploy/DEPLOY.md)。推荐将前端与 API 部署在同一站点，例如 `guide.tanzeng.xyz`。
