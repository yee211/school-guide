import unittest
from langchain_core.documents import Document
from app.rag.metadata import enrich_document_metadata, infer_retrieval_filters, FilterCatalog

class CampusLifeMetadataTests(unittest.TestCase):
    def test_mixed_life_chunk_remains_retrievable(self):
        doc = enrich_document_metadata(Document(page_content="食堂分南区和北区。快递站：菜鸟驿站在12栋女寝北楼下。图书馆有插座。", metadata={"source": "data/raw/school_life.txt"}))
        filters = infer_retrieval_filters("学校食堂和快递站在哪里？", FilterCatalog())
        self.assertIn(doc.metadata["document_type"], filters.document_types)

    def test_library_document_keeps_library_type(self):
        doc = enrich_document_metadata(Document(page_content="图书馆开馆时间", metadata={"source": "data/raw/library.txt"}))
        self.assertEqual(doc.metadata["document_type"], "图书馆")


class BaselineTests(unittest.IsolatedAsyncioTestCase):
    async def test_original_query_precedes_planning(self):
        from unittest.mock import AsyncMock
        from types import SimpleNamespace
        from langchain_core.messages import AIMessage
        from app.agents.agentic_rag import AgenticRAG
        from app.agents.retrieval_tools import ToolResult, Evidence
        executor = AsyncMock(return_value=ToolResult((Evidence("life", "菜鸟驿站在12栋女寝北楼下", ()),)))
        question = "学校食堂和快递站在哪里？"
        async def plan(messages):
            executor.assert_awaited_once_with("search_school_knowledge", question)
            self.assertIn("12栋", messages[-1].content)
            return AIMessage(content="", tool_calls=[])
        prepared = await AgenticRAG(SimpleNamespace(ainvoke=plan), executor).prepare(question, search_query="改写问题")
        self.assertIn("12栋", prepared[0][-1].content)
    def test_two_life_requirements(self):
        from app.agents.answer_requirements import build_requirements
        self.assertEqual(len(build_requirements("学校食堂和快递站在哪里？")), 2)


class LexicalRecallTests(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_category_does_not_block_bm25(self):
        from unittest.mock import patch, AsyncMock
        from app.rag.retriever import RetrieverService
        from app.rag.metadata import RetrievalFilters
        doc = Document(page_content="菜鸟驿站在12栋女寝北楼下", metadata={"document_type": "图书馆"})
        filters = RetrievalFilters(years=("2025",), provinces=("湖南省",), document_types=("校园生活",))
        with patch("app.rag.retriever.postgres_knowledge_store.get_filter_catalog", return_value=FilterCatalog()), patch("app.rag.retriever.infer_retrieval_filters", return_value=filters), patch.object(RetrieverService, "_semantic_search", new=AsyncMock(return_value=[])), patch("app.rag.retriever.postgres_knowledge_store.bm25_search", return_value=[(doc, 1)]) as bm25, patch("app.rag.retriever.qwen_reranker.rerank", new=AsyncMock(return_value=[doc])):
            trace = await RetrieverService().search_with_trace("学校食堂和快递站在哪里？")
        actual = bm25.call_args.kwargs["filters"]
        self.assertEqual(actual.document_types, ())
        self.assertEqual(actual.years, ("2025",))
        self.assertEqual(actual.provinces, ("湖南省",))
        self.assertIn("12栋", trace.documents[0].page_content)
