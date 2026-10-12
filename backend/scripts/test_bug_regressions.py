"""Offline regression checks for the project bug audit."""
import unittest
from pathlib import Path
from unittest.mock import patch
from langchain_core.documents import Document
from types import SimpleNamespace
from unittest.mock import AsyncMock
from app.rag.cleaner import DocumentCleaner
from app.rag.splitter import split_documents
from app.rag.upload_loader import load_uploaded_documents
from app.structured.parsers import parse_summary, _parse_int
from app.structured.normalize import parse_score_rank, normalize_province
from app.structured.query import StructuredResult
from app.agents.answer_requirements import admission_clarification

class BugRegressions(unittest.TestCase):
    def test_real_control_lines(self):
        path = Path(__file__).resolve().parents[1] / "data/raw/长沙工业学院历年录取分数线汇总.md"
        rows, _ = parse_summary(path.read_text(encoding="utf-8"), path.name)
        lines = {(r["subject_category"], r["batch"]): r["score"] for r in rows if r["year"] == 2026 and r["score_type"] == "控制线"}
        self.assertEqual(lines, {("历史类", "本科"):446, ("物理类", "本科"):400, ("历史类", "高职专科"):200, ("物理类", "高职专科"):200})

    def test_cleaning_preserves_semantic_lines(self):
        text = "历史沿革\n图书馆前身可追溯至\n1958\n总时长:1小时\n坐4号线直达\n换乘6号线"
        self.assertEqual(DocumentCleaner.clean_text(text), text)

    def test_text_decoding(self):
        for encoding in ("gb18030", "utf-8-sig"):
            self.assertEqual(load_uploaded_documents("资料.md", "湖南省招生计划".encode(encoding))[0].page_content, "湖南省招生计划")

    def test_numeric_boundaries(self):
        self.assertEqual(parse_score_rank("132431"), (None,132431))
        self.assertEqual(parse_score_rank("位次500"), (None,500))
        self.assertEqual(parse_score_rank("465 (132,431)"), (465,132431))
        self.assertEqual(_parse_int("4,800元"), 4800)
        self.assertEqual(normalize_province("上海市"), "上海市")

    def test_plan_context_contains_requirements_and_batch(self):
        row = dict(year=2026,province="湖南省",subject_category="物理类",group_no=None,major="人工智能",plan=10,tuition=4800,duration=4,source_file="plan.md",subject_requirement="物理、化学",batch="本科批")
        text = StructuredResult(plan_rows=[row]).format_context()
        self.assertIn("物理、化学", text)
        self.assertIn("本科批", text)
        lines = text.splitlines()
        self.assertEqual(lines[1].count("|"), lines[2].count("|"))

    def test_splitter_does_not_rescan_source(self):
        text = "# 招生\n| 专业 | 计划 |\n|---|---|\n| 人工智能 | 10 |\n\n" + "正文包含 a|b，不属于表格。" * 100
        with patch("app.rag.splitter._heading_context", side_effect=AssertionError("source rescan")), patch("app.rag.splitter._table_header_before", side_effect=AssertionError("source rescan")):
            chunks = split_documents([Document(page_content=text)])
        self.assertGreater(len(chunks), 1)
        self.assertNotIn("| 专业 | 计划 |", chunks[-1].page_content)

    def test_transactional_cache_does_not_reuse_legacy_namespace(self):
        from app.structured.query import StructuredQueryService
        from app.rag.metadata import RetrievalFilters
        service = StructuredQueryService()
        with patch.object(service, "_data_version", return_value=1):
            key = service._cache_key(RetrievalFilters(years=("2026",)), None)
        self.assertTrue(key.startswith("structured:v2:query:1:"))
        self.assertFalse(key.startswith("structured:query:1:"))

    def test_policy_question_does_not_require_score_conditions(self):
        self.assertIsNone(admission_clarification("复读生能报吗"))
        self.assertIsNone(admission_clarification("专升本怎么报"))

class AsyncRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_empty_llm_stream_is_an_error(self):
        from app.services.llm_service import LLMService
        from app.core.exceptions import LLMEmptyResponseError
        async def empty(_):
            yield SimpleNamespace(content=" ")
        service = LLMService.__new__(LLMService)
        service._llm = SimpleNamespace(astream=empty)
        with self.assertRaises(LLMEmptyResponseError):
            _ = [text async for text in service.stream([])]

    async def test_all_retrieval_failures_are_service_errors(self):
        from app.agents.agentic_rag import AgenticRAG
        from app.core.exceptions import LLMConnectionError
        from langchain_core.messages import AIMessage
        planner = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="")))
        with self.assertRaises(LLMConnectionError):
            await AgenticRAG(planner, AsyncMock(side_effect=RuntimeError("offline"))).prepare("学校概况")

if __name__ == "__main__":
    unittest.main()
