import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.api.knowledge import router as knowledge_router
from app.rag.reranker import qwen_reranker
from app.rag.retriever import retriever_service


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 预热：触发 jieba 分词、向量/rerank/数据库连接的懒加载，
    # 避免首个真实用户踩冷启动（评估显示首问向量调用可达 2.3s）。
    try:
        await retriever_service.search("学校概况", top_k=3)
        logger.info("知识库检索预热完成")
    except Exception:
        logger.warning("知识库检索预热失败，不影响启动", exc_info=True)

    yield
    await qwen_reranker.aclose()


app = FastAPI(title="AI School Introduction Assistant", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(knowledge_router)
