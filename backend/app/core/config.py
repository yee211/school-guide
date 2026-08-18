import os

from dotenv import load_dotenv

load_dotenv()

#ds
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
# 意图识别专用模型（路由用，可用更快档位；默认与生成模型相同）
INTENT_LLM_MODEL_ID = os.getenv("INTENT_LLM_MODEL_ID") or LLM_MODEL_ID
# DeepSeek V4 系列默认开启思考模式：思考模式下发生工具调用后，后续多轮必须回传
# reasoning_content，而 LangChain 会丢弃该字段从而触发 400。本项目以检索+组织回答
# 为主，默认关闭思考模式；如需开启请设置 LLM_ENABLE_THINKING=true。
LLM_ENABLE_THINKING = os.getenv("LLM_ENABLE_THINKING", "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

#embedding
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY")
EMBEDDING_MODEL_ID = os.getenv("EMBEDDING_MODEL_ID")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL")

# PostgreSQL + pgvector
POSTGRES_DSN = os.getenv("POSTGRES_DSN") or os.getenv("DATABASE_URL")
POSTGRES_CONNECT_TIMEOUT = max(
    1,
    int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5")),
)

# Redis（结构化查询缓存）
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
STRUCTURED_CACHE_TTL = max(
    60,
    int(os.getenv("STRUCTURED_CACHE_TTL", "3600")),
)

# rerank（千问云端 Rerank API，无需本地模型）
RERANKER_API_KEY = os.getenv("RERANKER_API_KEY")
RERANKER_MODEL_ID = os.getenv("RERANKER_MODEL_ID", "qwen3-rerank")
RERANKER_BASE_URL = os.getenv("RERANKER_BASE_URL")
# 混合检索召回：语义/BM25 各取 Top N
SEMANTIC_RECALL_K = max(1, int(os.getenv("SEMANTIC_RECALL_K", "15")))
BM25_RECALL_K = max(1, int(os.getenv("BM25_RECALL_K", "15")))
# 融合去重后交给 reranker 的候选数上限（20–30 条）
HYBRID_CANDIDATE_COUNT = max(
    1,
    int(os.getenv("HYBRID_CANDIDATE_COUNT", "30")),
)
