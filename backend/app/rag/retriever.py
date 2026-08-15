import asyncio
import logging
from dataclasses import dataclass
from time import perf_counter

import openai
from langchain_core.documents import Document

from app.core.config import HYBRID_CANDIDATE_COUNT
from app.core.exceptions import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMProviderError,
    LLMTimeoutError,
)
from app.rag.indexer import build_chunk_id, get_embedding_model
from app.rag.metadata import RetrievalFilters, infer_retrieval_filters
from app.rag.postgres_store import postgres_knowledge_store
from app.rag.reranker import cross_encoder_reranker


logger = logging.getLogger(__name__)

RRF_RANK_CONSTANT = 60


@dataclass(slots=True)
class RetrievalTrace:
    retrieval_query: str
    filters: dict[str, list[str]]
    semantic_results: list[tuple[Document, float]]
    lexical_results: list[tuple[Document, float]]
    fused_candidates: list[Document]
    documents: list[Document]
    timings_ms: dict[str, float]
    rerank_fallback: bool = False


class RetrieverService:
    async def _semantic_search(
        self,
        query: str,
        top_k: int,
        score_threshold: float | None,
        filters: RetrievalFilters,
    ) -> list[tuple[Document, float]]:
        try:
            query_embedding = await get_embedding_model().aembed_query(query)
        except openai.AuthenticationError as exc:
            logger.error("Embedding authentication failed")
            raise LLMAuthenticationError("向量模型鉴权失败") from exc
        except openai.APITimeoutError as exc:
            logger.warning("Embedding request timed out")
            raise LLMTimeoutError("向量模型响应超时") from exc
        except openai.APIConnectionError as exc:
            logger.warning("Unable to connect to embedding provider")
            raise LLMConnectionError("无法连接向量模型") from exc
        except openai.APIError as exc:
            logger.exception("Embedding provider returned an error")
            raise LLMProviderError("向量模型服务异常") from exc

        results = await asyncio.to_thread(
            postgres_knowledge_store.semantic_search,
            query_embedding,
            top_k,
            filters,
        )
        return [
            (document, score)
            for document, score in results
            if score_threshold is None or score >= score_threshold
        ]

    @staticmethod
    def _fuse_results(
        semantic_results: list[tuple[Document, float]],
        lexical_results: list[tuple[Document, float]],
        limit: int,
    ) -> list[Document]:
        documents: dict[str, Document] = {}
        fused_scores: dict[str, float] = {}

        for results in (semantic_results, lexical_results):
            for rank, (document, _) in enumerate(results, start=1):
                key = build_chunk_id(document)
                documents[key] = document
                fused_scores[key] = (
                    fused_scores.get(key, 0.0)
                    + 1.0 / (RRF_RANK_CONSTANT + rank)
                )

        ranked_keys = sorted(
            fused_scores,
            key=fused_scores.__getitem__,
            reverse=True,
        )
        return [documents[key] for key in ranked_keys[:limit]]

    async def search(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float | None = None,
    ) -> list[Document]:
        trace = await self.search_with_trace(
            query=query,
            top_k=top_k,
            score_threshold=score_threshold,
        )
        return trace.documents

    async def search_with_trace(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float | None = None,
        candidate_count: int | None = None,
    ) -> RetrievalTrace:
        total_started = perf_counter()
        retrieval_query = query.strip()
        if not retrieval_query or top_k <= 0:
            return RetrievalTrace(
                retrieval_query=retrieval_query,
                filters={},
                semantic_results=[],
                lexical_results=[],
                fused_candidates=[],
                documents=[],
                timings_ms={"total": 0.0},
            )

        retrieval_limit = max(
            candidate_count or HYBRID_CANDIDATE_COUNT,
            top_k,
        )
        filter_started = perf_counter()
        catalog = await asyncio.to_thread(
            postgres_knowledge_store.get_filter_catalog
        )
        filters = infer_retrieval_filters(retrieval_query, catalog)
        filter_ms = (perf_counter() - filter_started) * 1000

        async def timed_semantic_search():
            started = perf_counter()
            results = await self._semantic_search(
                retrieval_query,
                retrieval_limit,
                score_threshold,
                filters,
            )
            return results, (perf_counter() - started) * 1000

        async def timed_lexical_search():
            started = perf_counter()
            results = await asyncio.to_thread(
                postgres_knowledge_store.bm25_search,
                retrieval_query,
                retrieval_limit,
                filters,
            )
            return results, (perf_counter() - started) * 1000

        semantic_timed, lexical_timed = await asyncio.gather(
            timed_semantic_search(),
            timed_lexical_search(),
        )
        semantic_results, semantic_ms = semantic_timed
        lexical_results, lexical_ms = lexical_timed

        fusion_started = perf_counter()
        candidates = self._fuse_results(
            semantic_results,
            lexical_results,
            retrieval_limit,
        )
        fusion_ms = (perf_counter() - fusion_started) * 1000

        rerank_started = perf_counter()
        rerank_fallback = False
        if not candidates:
            documents = []
        else:
            try:
                documents = await asyncio.to_thread(
                    cross_encoder_reranker.rerank,
                    retrieval_query,
                    candidates,
                    top_k,
                )
            except Exception:
                rerank_fallback = True
                logger.exception(
                    "Cross-encoder reranking failed; using fused ranking"
                )
                documents = candidates[:top_k]

        timings_ms = {
            "filter": round(filter_ms, 2),
            "semantic": round(semantic_ms, 2),
            "bm25": round(lexical_ms, 2),
            "fusion": round(fusion_ms, 2),
            "rerank": round(
                (perf_counter() - rerank_started) * 1000,
                2,
            ),
            "total": round(
                (perf_counter() - total_started) * 1000,
                2,
            ),
        }
        logger.info(
            "Retrieval completed: semantic=%d lexical=%d fused=%d final=%d "
            "filters=%s timings_ms=%s rerank_fallback=%s",
            len(semantic_results),
            len(lexical_results),
            len(candidates),
            len(documents),
            filters.as_dict(),
            timings_ms,
            rerank_fallback,
        )
        return RetrievalTrace(
            retrieval_query=retrieval_query,
            filters=filters.as_dict(),
            semantic_results=semantic_results,
            lexical_results=lexical_results,
            fused_candidates=candidates,
            documents=documents,
            timings_ms=timings_ms,
            rerank_fallback=rerank_fallback,
        )


retriever_service = RetrieverService()
