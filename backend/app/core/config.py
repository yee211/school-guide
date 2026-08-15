import os

from dotenv import load_dotenv

load_dotenv()

#ds
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL_ID = os.getenv("LLM_MODEL_ID")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")

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

# rerank
RERANK_MODEL_ID = os.getenv(
    "RERANK_MODEL_ID",
    "BAAI/bge-reranker-base",
)
RERANK_BATCH_SIZE = max(
    1,
    int(os.getenv("RERANK_BATCH_SIZE", "8")),
)
RERANK_MAX_LENGTH = max(
    128,
    int(os.getenv("RERANK_MAX_LENGTH", "512")),
)
HYBRID_CANDIDATE_COUNT = max(
    10,
    int(os.getenv("HYBRID_CANDIDATE_COUNT", "50")),
)
