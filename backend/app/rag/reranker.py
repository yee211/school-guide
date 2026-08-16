import logging

import httpx
from langchain_core.documents import Document

from app.core.config import (
    RERANKER_API_KEY,
    RERANKER_BASE_URL,
    RERANKER_MODEL_ID,
)


logger = logging.getLogger(__name__)


class QwenReranker:
    """调用千问（DashScope 百炼）云端 Rerank API 做重排序，无需本地模型。"""

    def __init__(self) -> None:
        self._client = httpx.Client(timeout=30.0)

    def rerank(
        self,
        query: str,
        documents: list[Document],
        top_k: int,
    ) -> list[Document]:
        if not documents or top_k <= 0:
            return []

        if not RERANKER_BASE_URL:
            raise RuntimeError("未配置 RERANKER_BASE_URL，无法调用 Rerank API")

        url = f"{RERANKER_BASE_URL.rstrip('/')}/reranks"
        response = self._client.post(
            url,
            headers={
                "Authorization": f"Bearer {RERANKER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": RERANKER_MODEL_ID,
                "query": query,
                "documents": [
                    document.page_content for document in documents
                ],
                "top_n": min(top_k, len(documents)),
            },
        )
        response.raise_for_status()
        results = response.json().get("results", [])

        ordered = sorted(
            results,
            key=lambda item: item.get("relevance_score", 0.0),
            reverse=True,
        )

        ranked: list[Document] = []
        for item in ordered:
            index = item.get("index")
            if isinstance(index, int) and 0 <= index < len(documents):
                ranked.append(documents[index])
            if len(ranked) >= top_k:
                break
        return ranked


qwen_reranker = QwenReranker()
