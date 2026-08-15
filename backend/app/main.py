from fastapi import FastAPI
from app.api.chat import router as chat_router
from app.api.knowledge import router as knowledge_router
app = FastAPI(title="AI School Introduction Assistant")
app.include_router(chat_router)
app.include_router(knowledge_router)
