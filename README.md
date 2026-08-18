# 谭锃个人主页 · 校园智答（School Introduction Assistant）

个人开发者作品集网站，内嵌「校园智答」作为首个可交互项目。校园智答针对长沙工业学院的招生录取、专业设置、学费、校园生活等问题，提供基于知识库的智能问答。

## 技术栈

- **后端**：FastAPI + LangChain + PostgreSQL（pgvector）
- **前端**：Vue 3 + TypeScript + Vite（个人主页 + 项目在线体验）
- **检索**：混合检索（向量检索 + BM25 词法检索 + bge-reranker 重排）
- **结构化数据**：录取分数线 / 招生计划抽取进 PostgreSQL 表，SQL 精确查询
- **缓存**：Redis（Cache-Aside + 版本号失效）

## 架构

```
用户提问
   │
   ▼
路由 agent（LLM 意图识别）
   ├─ 结构化问题（分数线/学费/计划数）→ query_admission_data tool → SQL 精确查询
   └─ 非结构化问题（概况/图书馆/校园生活）→ RAG 混合检索 → LLM 生成
```

- **结构化数据**（7 个录取/招生 Markdown）→ 抽取进 `school_admission_scores` / `school_admission_plans` 两张表，规则解析查询条件后拼 SQL 精确命中
- **非结构化数据**（概况/图书馆/校园生活）→ RAG 向量检索

## 依赖

| 依赖 | 说明 |
|---|---|
| Python | 3.12+ |
| PostgreSQL | 需安装 **pgvector** 扩展 |
| Redis | 结构化查询缓存（可选，挂了自动降级） |
| Node.js | 前端构建（18+） |

## 快速开始

### 1. 配置环境变量

```bash
cd backend
cp .env.example .env   # 然后编辑 .env 填入真实值
```

关键配置：

```ini
# PostgreSQL（含 pgvector）
POSTGRES_DSN=postgresql://user:password@127.0.0.1:5432/school_assistant
# Redis（结构化查询缓存）
REDIS_URL=redis://:password@127.0.0.1:6379/0
# LLM（OpenAI 兼容接口）
LLM_API_KEY=...
LLM_MODEL_ID=...
LLM_BASE_URL=...
# Embedding（OpenAI 兼容接口）
EMBEDDING_API_KEY=...
EMBEDDING_MODEL_ID=...
EMBEDDING_BASE_URL=...
```

### 2. 安装依赖

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows
pip install -r requirements.txt
```

### 3. 建 RAG 索引 + 导入结构化数据

```bash
cd backend
PYTHONPATH=. python -m scripts.build_index         # 非结构化文件 → 向量索引
PYTHONPATH=. python -m scripts.import_structured   # 7 个录取/招生文件 → 数据库表
```

> 数据文件更新后，重跑这两个命令即可（幂等，全量重建）。

### 4. 启动后端

```bash
cd backend
PYTHONPATH=. python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

接口：
- `POST /chat` —— 非流式问答
- `POST /chat/stream` —— SSE 流式问答
- `POST /knowledge/upload` —— 上传知识文档

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev   # 默认 http://127.0.0.1:5173，已代理 /chat 到后端
```

## 测试脚本

| 脚本 | 验证内容 |
|---|---|
| `scripts/test_structured.py` | 结构化数据解析、落库、精确查询（需数据库） |
| `scripts/test_postgres_store.py` | RAG 存储结构、索引、BM25 过滤（需数据库） |
| `scripts/test_metadata_filters.py` | 元数据抽取 + 过滤推断（纯逻辑） |
| `scripts/test_incremental_index.py` | 增量索引一致性（需数据库） |
| `scripts/evaluate_retrieval.py` | RAG 检索指标（recall/mrr/ndcg/hit_rate） |

运行方式（`backend` 目录下）：

```bash
PYTHONPATH=. python -m scripts.test_structured
PYTHONPATH=. python -m scripts.evaluate_retrieval
```

## 目录结构

```
backend/
├── app/
│   ├── agents/       # 路由 agent（意图识别 + tool 编排）
│   ├── api/          # FastAPI 接口
│   ├── core/         # 配置、异常、数据库连接、Redis 缓存、常量
│   ├── prompts/      # 提示词
│   ├── rag/          # RAG 检索管线（索引/检索/切分/元数据/重排）
│   ├── services/     # LLM 服务、RAG 服务
│   └── structured/   # 结构化数据（解析/落库/查询）
├── data/raw/         # 知识库源文件
├── evals/            # 检索评估用例
└── scripts/          # 建库/导入/测试脚本
frontend/             # Vue 3 前端
```
