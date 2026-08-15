from functools import lru_cache
from hashlib import sha256
import json
import logging

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from app.core.config import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_MODEL_ID,
)
from app.rag.postgres_store import postgres_knowledge_store


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_embedding_model() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        api_key=EMBEDDING_API_KEY,
        base_url=EMBEDDING_BASE_URL,
        model=EMBEDDING_MODEL_ID,
        chunk_size=20,
        timeout=30.0,
        max_retries=2,
        check_embedding_ctx_length=False,
    )


def rebuild_index(chunks: list[Document]) -> int:
    if not chunks:
        raise ValueError("没有可以写入知识库的文本片段")

    chunks_by_id = {
        build_chunk_id(chunk): chunk
        for chunk in chunks
    }
    desired_ids = list(chunks_by_id)
    existing_ids = postgres_knowledge_store.list_ids()
    pending_ids = [
        chunk_id
        for chunk_id in desired_ids
        if chunk_id not in existing_ids
    ]
    pending_documents = [
        chunks_by_id[chunk_id]
        for chunk_id in pending_ids
    ]
    embeddings = (
        get_embedding_model().embed_documents(
            [document.page_content for document in pending_documents]
        )
        if pending_documents
        else []
    )
    stats = postgres_knowledge_store.sync_documents(
        documents=pending_documents,
        embeddings=embeddings,
        ids=pending_ids,
        desired_ids=desired_ids,
    )
    logger.info(
        "Knowledge index synchronized: total=%d added=%d removed=%d",
        stats.total,
        stats.added,
        stats.removed,
    )
    return stats.total


def build_chunk_id(document: Document) -> str:
    metadata = document.metadata
    identity = "|".join(
        [
            str(EMBEDDING_MODEL_ID or ""),
            str(metadata.get("source", "")),
            str(metadata.get("page", "")),
            str(metadata.get("slide", "")),
            str(metadata.get("sheet", "")),
            str(metadata.get("start_index", "")),
            json.dumps(
                {
                    "years": metadata.get("years", []),
                    "subject_categories": metadata.get(
                        "subject_categories",
                        [],
                    ),
                    "provinces": metadata.get("provinces", []),
                    "majors": metadata.get("majors", []),
                    "document_type": metadata.get("document_type", ""),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            document.page_content,
        ]
    )
    digest = sha256(identity.encode("utf-8")).hexdigest()
    return f"school-chunk-{digest}"
