from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.api.knowledge import router as knowledge_router
from app.rag.reranker import qwen_reranker


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await qwen_reranker.aclose()


app = FastAPI(title="AI School Introduction Assistant", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(knowledge_router)
