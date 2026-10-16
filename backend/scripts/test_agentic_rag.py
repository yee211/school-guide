"""Offline agent behavior tests; model/tool responses are controlled."""
import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("LLM_API_KEY", "offline-test")
os.environ.setdefault("LLM_MODEL_ID", "offline-test")

from langchain_core.messages import AIMessage, ToolMessage
from app.agents.agentic_rag import AgenticRAG, RetrievalState
from app.agents.retrieval_tools import Evidence, ToolResult, execute_retrieval
from app.services.rag_service import SourceInfo
from app.agents.query_router import QueryRouter


def evidence(key="one", source="data/raw/专业.md", content="2026年软件工程专业特色"):
    return Evidence(key, content, (SourceInfo("专业", source),))


def call(name="search_school_knowledge", query="软件工程特色", ident="t1"):
    arg = "question" if name == "query_admission_data" else "query"
    return {"name": name, "args": {arg: query}, "id": ident, "type": "tool_call"}


def response(*calls):
    return AIMessage(content="planner text must never become evidence", tool_calls=list(calls))


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_planner_runs_before_any_retrieval(self):
        order = []
        async def plan(messages):
            order.append("plan")
            return response(call("query_admission_data", "软件工程招生计划")) if len(order) == 1 else response()
        async def execute(name, query):
            order.append(name)
            return ToolResult((evidence(),))
        await AgenticRAG(SimpleNamespace(ainvoke=plan), execute).prepare("软件工程招生计划")
        self.assertEqual(order, ["plan", "query_admission_data", "plan"])

    async def test_mixed_question_uses_two_tools_and_merges_sources(self):
        planner = SimpleNamespace(ainvoke=AsyncMock(side_effect=[response(call("query_admission_data", "2026软件工程学费")), response(call(ident="t2")), response()]))
        executor = AsyncMock(side_effect=[ToolResult((evidence("row", "plans.md", "学费5800元"),)), ToolResult((evidence(),))])
        messages, sources = await AgenticRAG(planner, executor).prepare("软件工程的学费和特色")
        self.assertEqual(executor.await_count, 2)
        self.assertEqual(len(sources), 2)
        self.assertIn("5800", messages[-1].content)
        self.assertNotIn("planner text", messages[-1].content)
        self.assertEqual(planner.ainvoke.await_count, 3)

    async def test_duplicate_query_reuses_result_and_deduplicates_evidence(self):
        planner = SimpleNamespace(ainvoke=AsyncMock(side_effect=[response(call()), response(call(ident="t2")), response()]))
        executor = AsyncMock(return_value=ToolResult((evidence(), evidence())))
        messages, sources = await AgenticRAG(planner, executor).prepare("专业特色")
        executor.assert_awaited_once()
        self.assertEqual(len(sources), 1)
        self.assertEqual(messages[-1].content.count("[资料"), 1)

    async def test_no_tools_cannot_answer_from_model_memory(self):
        planner = SimpleNamespace(ainvoke=AsyncMock(return_value=response()))
        executor = AsyncMock(return_value=ToolResult((evidence(),)))
        messages, _ = await AgenticRAG(planner, executor).prepare("学校特色")
        executor.assert_awaited_once_with("search_school_knowledge", "学校特色")
        self.assertNotIn("planner text", messages[-1].content)

    async def test_empty_result_can_trigger_requery(self):
        planner = SimpleNamespace(ainvoke=AsyncMock(side_effect=[response(call()), response(call(query="软件工程培养方向", ident="t2")), response()]))
        executor = AsyncMock(side_effect=[ToolResult(note="未找到"), ToolResult((evidence(),))])
        prepared = await AgenticRAG(planner, executor).prepare("专业特色")
        self.assertIsNotNone(prepared)
        self.assertEqual(executor.await_count, 2)

    async def test_tool_failure_allows_other_tool(self):
        planner = SimpleNamespace(ainvoke=AsyncMock(side_effect=[response(call()), response(call("query_admission_data", "软件工程人数", "t2")), response()]))
        executor = AsyncMock(side_effect=[RuntimeError("offline"), ToolResult((evidence(),))])
        messages, _ = await AgenticRAG(planner, executor).prepare("专业人数和特色")
        self.assertIn("工具执行失败", messages[-1].content)
        self.assertEqual(executor.await_count, 2)

    async def test_planner_failure_uses_default_retrieval(self):
        planner = SimpleNamespace(ainvoke=AsyncMock(side_effect=RuntimeError("offline")))
        executor = AsyncMock(return_value=ToolResult((evidence(),)))
        self.assertIsNotNone(await AgenticRAG(planner, executor).prepare("专业特色"))
        executor.assert_awaited_once()

    async def test_call_budget_and_complete_tool_protocol(self):
        planner = SimpleNamespace(ainvoke=AsyncMock(return_value=response(call(ident="t1"), call(query="课程", ident="t2"), call(query="师资", ident="t3"))))
        executor = AsyncMock(return_value=ToolResult((evidence(),)))
        with patch("app.agents.agentic_rag.AGENT_MAX_TOOL_CALLS", 2):
            await AgenticRAG(planner, executor).prepare("专业介绍")
        self.assertEqual(executor.await_count, 2)
        self.assertEqual(planner.ainvoke.await_count, 1)

    async def test_timeout_keeps_partial_evidence(self):
        planner = SimpleNamespace(ainvoke=AsyncMock(side_effect=[response(call()), TimeoutError()]))
        executor = AsyncMock(return_value=ToolResult((evidence(),)))
        messages, sources = await AgenticRAG(planner, executor).prepare("专业特色")
        self.assertEqual(len(sources), 1)
        self.assertIn("时间上限", messages[-1].content)

    async def test_tool_timeout_is_bounded(self):
        planner = SimpleNamespace(ainvoke=AsyncMock(return_value=response(call())))
        async def slow(*args):
            await asyncio.sleep(1)
        with patch("app.agents.agentic_rag.AGENT_TIMEOUT_SECONDS", 0.02):
            self.assertIsNone(await AgenticRAG(planner, slow).prepare("专业特色"))

    async def test_invalid_tool_does_not_execute(self):
        planner = SimpleNamespace(ainvoke=AsyncMock(side_effect=[response(call("delete_database")), response(), response()]))
        executor = AsyncMock(return_value=ToolResult(note="未找到"))
        messages, sources = await AgenticRAG(planner, executor).prepare("专业特色")
        executor.assert_awaited_once_with("search_school_knowledge", "专业特色")
        self.assertEqual(sources, [])
        self.assertIn("未取得可用事实证据", messages[-1].content)

    async def test_all_question_types_enter_agent(self):
        questions = (
            "2025年湖南物理类软件工程录取分数线",
            "软件工程招生人数和就业方向",
            "2025年湖南物理类环境工程录取分数线",
            "2025年湖南物理类软件工程录取分是多少？这个分数我有机会吗？",
            "宿舍环境怎么样",
        )
        for question in questions:
            with self.subTest(question=question):
                router = QueryRouter(None)
                with patch.object(router._agentic_rag, "prepare", AsyncMock(return_value=None)) as agent:
                    await router.prepare(question)
                agent.assert_awaited_once_with(question, None, search_query=question)

    async def test_sources_only_include_admitted_evidence(self):
        state = RetrievalState()
        with patch("app.agents.agentic_rag.AGENT_CONTEXT_CHARS", 20):
            state.add(ToolResult((evidence(content="ok"), evidence("huge", "excluded.md", "x" * 50))))
        self.assertEqual(list(state.evidence), ["one"])
        self.assertTrue(state.notes)

    async def test_structured_tool_keeps_complete_row_and_source(self):
        from app.structured.query import StructuredResult
        row = dict(year=2026, province="湖南省", subject_category="物理类", group_no="101", major="软件工程", plan=40, tuition=5800, duration=4, source_file="plans.md")
        with patch("app.agents.retrieval_tools.structured_query_service.query_and_format", return_value=StructuredResult(plan_rows=[row], source_files=("plans.md",))):
            result = await execute_retrieval("query_admission_data", "2026年湖南软件工程招生计划")
        self.assertIn("40 | 5800 | 4", result.evidence[0].content)
        self.assertEqual(result.evidence[0].sources[0].source, "plans.md")

    async def test_stream_preserves_sse_contract(self):
        from app.agents.school_agent import SchoolAgent
        router = SimpleNamespace(prepare=AsyncMock(return_value=([AIMessage(content="evidence")], [SourceInfo("专业", "major.md")])))
        async def stream(_messages):
            yield "第一段"
            yield "第二段"
        with patch("app.agents.school_agent.llm_service.stream", stream):
            events = [event async for event in SchoolAgent(router).stream("专业特色")]
        self.assertEqual([e["type"] for e in events], ["delta", "delta", "done"])
        self.assertEqual(events[-1]["sources"], [{"title": "专业", "source": "major.md"}])

    async def test_rewrite_preserves_mixed_original_question_for_agent(self):
        router = QueryRouter(None)
        history = [SimpleNamespace(role="user", content="软件工程")]
        with patch("app.agents.query_router.rag_service.contextualize_query", AsyncMock(return_value="软件工程招生计划")), patch.object(router._agentic_rag, "prepare", AsyncMock(return_value=None)) as agent:
            await router.prepare("软件工程招生计划和就业方向", history)
        agent.assert_awaited_once_with("软件工程招生计划和就业方向", history, search_query="软件工程招生计划")

    async def test_document_tool_preserves_metadata(self):
        from langchain_core.documents import Document
        doc = Document(page_content="特色内容", metadata={"source": "major.md", "title": "软件工程", "years": ["2026"]})
        with patch("app.agents.retrieval_tools.retriever_service.search", AsyncMock(return_value=[doc])):
            result = await execute_retrieval("search_school_knowledge", "软件工程")
        self.assertIn("2026", result.evidence[0].content)
        self.assertEqual(result.evidence[0].sources[0].source, "major.md")


if __name__ == "__main__":
    unittest.main()
