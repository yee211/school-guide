"""Offline routing regressions; no database or model requests."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("LLM_API_KEY", "offline-test")
os.environ.setdefault("LLM_MODEL_ID", "offline-test")

from langchain_core.messages import AIMessage
from app.agents.query_router import QueryRouter
from app.services.rag_service import RAGService


class RouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_rewrite_is_reused(self):
        router = QueryRouter(SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content=""))))
        history = [SimpleNamespace(role="user", content="软件工程怎么样")]
        with patch.object(router, "_fast_structured_question", AsyncMock(return_value=None)), patch("app.agents.query_router.rag_service.contextualize_query", AsyncMock(return_value="软件工程学费")) as rewrite, patch.object(router._agentic_rag, "prepare", AsyncMock(return_value=None)) as prepare:
            await router.prepare("学费呢", history)
            rewrite.assert_awaited_once()
            prepare.assert_awaited_once_with("学费呢", history, search_query="软件工程学费")

    async def test_intent_failure_falls_back(self):
        router = QueryRouter(SimpleNamespace(ainvoke=AsyncMock(side_effect=TimeoutError("offline"))))
        with patch.object(router, "_fast_structured_question", AsyncMock(return_value=None)), patch.object(router._agentic_rag, "prepare", AsyncMock(return_value=None)) as prepare:
            await router.prepare("学校概况")
            prepare.assert_awaited_once_with("学校概况", None, search_query="学校概况")

    async def test_structured_rewrite_preserves_original_question(self):
        router = QueryRouter(None)
        history = [SimpleNamespace(role="user", content="软件工程分数线")]
        tool = SimpleNamespace(content="table")
        with patch.object(router, "_fast_structured_question", AsyncMock(return_value="2025湖南物理类软件工程分数线")), patch("app.agents.query_router.rag_service.contextualize_query", AsyncMock(return_value="2025湖南物理类软件工程分数线")), patch.object(router, "_structured_tool_result", AsyncMock(return_value=(tool, []))) as query:
            messages, _ = await router.prepare("湖南", history)
            query.assert_awaited_once_with("2025湖南物理类软件工程分数线", "fast_structured")
            self.assertEqual(messages[-3].content, "湖南")

    async def test_rag_skips_existing_rewrite(self):
        service = RAGService()
        with patch.object(service, "contextualize_query", AsyncMock()) as rewrite, patch("app.services.rag_service.retriever_service.search", AsyncMock(return_value=[])) as search:
            await service.prepare("学费呢", [], search_query="软件工程学费")
            rewrite.assert_not_awaited()
            search.assert_awaited_once_with(query="软件工程学费", top_k=5)


if __name__ == "__main__":
    unittest.main()
