"""Grounding, clarification and automatic missing-item retrieval regressions."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
os.environ.setdefault("LLM_API_KEY", "offline-test")
os.environ.setdefault("LLM_MODEL_ID", "offline-test")

from langchain_core.messages import AIMessage
from app.agents.answer_requirements import (
    Clarification, CoverageItem, CoverageReport, admission_clarification,
    build_requirements, validate_coverage,
)
from app.agents.agentic_rag import AgenticRAG
from app.agents.query_router import QueryRouter
from app.agents.retrieval_tools import Evidence, ToolResult
from app.agents.school_agent import SchoolAgent
from app.services.rag_service import SourceInfo


def item(key, content, facts=None):
    return Evidence(key, content, (SourceInfo("资料", key+".md"),), facts or {})


def supported(req_id, *keys):
    return CoverageItem(requirement_id=req_id, status="supported", evidence_ids=list(keys))


class RequirementTests(unittest.TestCase):
    def test_two_majors_three_metrics_produce_six_items(self):
        requirements = build_requirements("2025年湖南物理类比较软件工程和人工智能的学费、招生人数、就业方向")
        self.assertEqual(len(requirements), 6)
        self.assertEqual(len({r.id for r in requirements}), 6)
        jobs = [r for r in requirements if not r.field]
        self.assertTrue(all("2025" not in r.query for r in jobs))
        self.assertTrue(all("2025" in r.query for r in requirements if r.field))

    def test_each_explicit_year_is_a_separate_requirement(self):
        reqs = build_requirements("2024年和2025年湖南物理类软件工程学费")
        self.assertEqual(len(reqs), 2)
        self.assertEqual({r.years for r in reqs}, {("2024",), ("2025",)})

    def test_group_number_must_match(self):
        reqs = build_requirements("2025湖南物理类107组招生计划")
        row = dict(year=2025, province="湖南省", subject_category="物理类", group_no="物理108", plan=40)
        result = validate_coverage(reqs, {"e": item("e", "表", row)}, CoverageReport(items=[supported("r1", "e")]))
        self.assertEqual(result["r1"], "missing")

    def test_missing_score_conditions_are_requested(self):
        result = admission_clarification("计算机多少分能上")
        self.assertIsInstance(result, Clarification)
        self.assertIn("省份", result.answer)
        self.assertIn("年份", result.answer)
        self.assertIn("科类", result.answer)
        self.assertNotIn("请补充专业", result.answer)

    def test_all_groups_are_valid_without_one_group_number(self):
        self.assertIsNone(admission_clarification("2025年湖南物理类各专业组投档线是多少？"))
        self.assertIsNone(admission_clarification("2024年湖南历史类投档线是多少？"))
        self.assertIsNotNone(admission_clarification("湖南物理类各专业组投档线是多少？"))

    def test_group_score_query_does_not_mix_major_scores(self):
        from app.structured.query import structured_query_service
        from app.structured.parsers import GROUP_FLOOR
        self.assertEqual(structured_query_service._infer_score_type("2025年湖南物理类各专业组投档线是多少？"), (GROUP_FLOOR,))

    def test_complete_conditions_do_not_ask(self):
        self.assertIsNone(admission_clarification("2025年湖南物理类软件工程分数线"))

    def test_historical_overview_is_not_blocked(self):
        self.assertIsNone(admission_clarification("软件工程历年分数线趋势"))
        self.assertIsNone(admission_clarification("投档线是什么意思"))

    def test_fabricated_evidence_id_cannot_mark_supported(self):
        reqs = build_requirements("软件工程学费")
        result = validate_coverage(reqs, {}, CoverageReport(items=[supported("r1", "invented")]))
        self.assertEqual(result["r1"], "missing")

    def test_nonmatching_year_and_empty_tuition_cannot_cover_fee(self):
        reqs = build_requirements("2025湖南物理类软件工程学费")
        base = dict(major="软件工程", year=2025, province="湖南省", subject_category="物理类", tuition=5800)
        for changes in ({"year": 2024}, {"tuition": None}, {"province": "江西省"}, {"major": "人工智能"}):
            row = {**base, **changes}
            result = validate_coverage(reqs, {"e": item("e", "学费表", row)}, CoverageReport(items=[supported("r1", "e")]))
            self.assertEqual(result["r1"], "missing")
        result = validate_coverage(reqs, {"e": item("e", "学费表", base)}, CoverageReport(items=[supported("r1", "e")]))
        self.assertEqual(result["r1"], "supported")

    def test_document_cannot_substitute_precise_fee(self):
        reqs = build_requirements("软件工程学费")
        result = validate_coverage(reqs, {"e": item("e", "软件工程学费5800")}, CoverageReport(items=[supported("r1", "e")]))
        self.assertEqual(result["r1"], "missing")


class CoverageTests(unittest.IsolatedAsyncioTestCase):
    async def test_premature_stop_triggers_missing_item_lookup(self):
        planner = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="")))
        doc = item("doc", "软件工程就业方向：软件开发")
        row = item("fee", "软件工程学费5800", dict(major="软件工程", tuition=5800))
        executor = AsyncMock(side_effect=[ToolResult((doc,)), ToolResult((row,))])
        checker = SimpleNamespace(ainvoke=AsyncMock(side_effect=[
            CoverageReport(items=[supported("r2", "doc")]),
            CoverageReport(items=[supported("r1", "fee"), supported("r2", "doc")]),
        ]))
        messages, sources = await AgenticRAG(planner, executor, checker).prepare("软件工程学费和就业方向")
        self.assertEqual(executor.await_count, 2)
        executor.assert_any_await("query_admission_data", "软件工程 学费")
        self.assertIn("有证据", messages[-1].content)
        self.assertEqual(len(sources), 2)

    async def test_independent_missing_items_are_parallel(self):
        planner = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="")))
        started = 0
        both = asyncio.Event()
        async def executor(name, query):
            nonlocal started
            if "学费和" in query:
                return ToolResult(note="未找到")
            started += 1
            if started == 2:
                both.set()
            await asyncio.wait_for(both.wait(), 0.5)
            return ToolResult(note="未找到")
        checker = SimpleNamespace(ainvoke=AsyncMock(return_value=CoverageReport()))
        with patch("app.agents.agentic_rag.AGENT_MAX_ROUNDS", 3):
            messages, _ = await AgenticRAG(planner, executor, checker).prepare("软件工程学费和就业方向")
        self.assertEqual(started, 2)
        self.assertIn("未找到匹配证据", messages[-1].content)

    async def test_clarification_stream_avoids_model_and_database(self):
        router = QueryRouter(None)
        with patch.object(router._agentic_rag, "prepare", AsyncMock()) as agent, patch("app.agents.school_agent.llm_service.stream") as stream:
            events = [e async for e in SchoolAgent(router).stream("计算机多少分能上")]
        agent.assert_not_awaited()
        stream.assert_not_called()
        self.assertEqual([e["type"] for e in events], ["delta", "done"])
        self.assertEqual(events[-1]["sources"], [])

    async def test_history_resolved_before_asking_again(self):
        router = QueryRouter(None)
        history = [SimpleNamespace(role="user", content="2025年湖南物理类软件工程分数线")]
        with patch("app.agents.query_router.rag_service.contextualize_query", AsyncMock(return_value="2025年湖南物理类人工智能分数线")), patch.object(router._agentic_rag, "prepare", AsyncMock(return_value=None)) as agent:
            await router.prepare("人工智能呢", history)
        agent.assert_awaited_once_with("人工智能呢", history, search_query="2025年湖南物理类人工智能分数线")


if __name__ == "__main__":
    unittest.main()
