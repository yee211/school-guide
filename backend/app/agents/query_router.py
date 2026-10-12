import asyncio
import logging
import re

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.agents.answer_requirements import Clarification, admission_clarification, normalize_years
from app.agents.agentic_rag import AgenticRAG
from app.prompts.school_prompt import SCHOOL_SYSTEM_PROMPT
from app.rag.metadata import infer_retrieval_filters
from app.services.rag_service import SourceInfo, rag_service
from app.structured.query import structured_query_service


logger = logging.getLogger(__name__)


class QueryRouter:
    """根据消息+历史决定走结构化查询还是 RAG，并组装生成所需的消息与来源。

    简单精确问题走规则快通道，其他问题进入有预算的工具检索循环。

    对外入口 prepare 返回 ``(gen_messages, sources)``；返回 None 表示无内容可答。
    """

    def __init__(self, llm_tools, coverage_checker=None) -> None:
        # 由 SchoolAgent 注入绑定两类检索工具的规划模型
        self._agentic_rag = AgenticRAG(llm_tools, coverage_checker=coverage_checker)

    MAX_HISTORY_MESSAGES = 8  # 最多保留最近 4 轮问答（8 条消息）
    MAX_HISTORY_CONTENT_CHARS = 1000  # 历史单条消息内容截断保护

    @classmethod
    def _history_to_messages(cls, history) -> list[BaseMessage]:
        """把前端传来的历史对话按滑动窗口修剪后转成 LangChain 消息，防止上下文失控。"""
        if not history:
            return []

        trimmed = (
            history[-cls.MAX_HISTORY_MESSAGES:]
            if len(history) > cls.MAX_HISTORY_MESSAGES
            else history
        )

        messages: list[BaseMessage] = []
        for item in trimmed:
            content = (item.content or "").strip()
            if len(content) > cls.MAX_HISTORY_CONTENT_CHARS:
                content = content[:cls.MAX_HISTORY_CONTENT_CHARS] + "…[截断]"
            if item.role == "user":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(AIMessage(content=content))
        return messages

    @staticmethod
    def _requires_narrative(message: str) -> bool:
        return bool(re.search(
            r"比较|对比|区别|推荐|就业|特色|课程|培养|前景|师资|宿舍|住宿|校园|优势|怎么样|如何|介绍|政策|设施|环境|地址|电话|联系|交通|图书|食堂|位置|办学|面积",
            message,
        ))

    @staticmethod
    async def _fast_structured_question(message: str) -> str | None:
        """规则快通道：消息本身已是自包含的结构化问题（专业/专业组 + 分数/计划关键词）。

        只有同时命中「专业或专业组」且「录取分数/招生计划」关键词才触发，直接返回查询串；
        混合问题或条件不足时返回 None，进入检索 Agent。
        """
        # Mixed questions must retrieve narrative evidence as well as exact rows.
        if QueryRouter._requires_narrative(message):
            return None
        catalog = await asyncio.wait_for(asyncio.to_thread(structured_query_service.get_catalog), timeout=10.0)
        filters = infer_retrieval_filters(message, catalog)
        remainder = message
        for major in filters.majors:
            remainder = remainder.replace(major, "")
        if len(filters.majors) > 1 or re.search(r"和|及|同时|另外|还有|并且|分别|与|、", remainder):
            return None
        targeted = bool(
            filters.majors
            or filters.groups
            or (filters.provinces and filters.years)
        )
        is_score_or_plan = bool(
            set(filters.document_types) & {"录取分数", "招生计划"}
        )
        return message if (targeted and is_score_or_plan) else None

    async def _structured_tool_result(
        self,
        question: str,
        tool_call_id: str,
    ) -> tuple[ToolMessage, list[SourceInfo]] | None:
        """执行结构化精确查询并组装 ToolMessage；无有效结果且无引导信息时返回 None。"""
        result = await asyncio.to_thread(
            structured_query_service.query_and_format,
            question,
        )
        # 结构化查询无有效结果且无引导信息时回退 RAG（避免误判意图后卡在空结果）
        if not result.score_rows and not result.plan_rows and not result.guidance:
            return None

        sources: list[SourceInfo] = []
        seen_sources: set[str] = set()
        for source_file in result.source_files:
            if source_file in seen_sources:
                continue
            seen_sources.add(source_file)
            sources.append(
                SourceInfo(
                    title=source_file.split("/")[-1].removesuffix(".md"),
                    source=source_file,
                )
            )

        tool_message = ToolMessage(
            content=result.format_context(),
            tool_call_id=tool_call_id,
        )
        return tool_message, sources

    async def _fast_structured_messages(
        self,
        message: str,
        history,
        search_query: str | None = None,
    ) -> tuple[list[BaseMessage], list[SourceInfo]] | None:
        """快通道命中时合成 AIMessage+ToolMessage，复用与工具调用一致的生成格式。"""
        tool_call_id = "fast_structured"
        try:
            tool_result = await asyncio.wait_for(
                self._structured_tool_result(search_query or message, tool_call_id),
                timeout=10.0,
            )
        except Exception:
            logger.warning("Fast structured query failed; entering retrieval agent", exc_info=True)
            tool_result = None
        if tool_result is None:
            return await self._agentic_rag.prepare(
                message, history, search_query=search_query or message
            )

        tool_message, sources = tool_result
        base_messages: list[BaseMessage] = [
            SystemMessage(content=SCHOOL_SYSTEM_PROMPT),
            *self._history_to_messages(history),
            HumanMessage(content=message),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "query_admission_data",
                        "args": {"question": search_query or message},
                        "id": tool_call_id,
                        "type": "tool_call",
                    }
                ],
            ),
            tool_message,
        ]
        return base_messages, sources

    async def prepare(
        self,
        message: str,
        history=None,
    ) -> tuple[list[BaseMessage], list[SourceInfo]] | Clarification | None:
        """路由并组装生成所需的消息与来源；返回 None 表示无内容可答。"""
        search_query = normalize_years(message.strip())
        # Clarification must use the resolved current question, not arbitrary old history.
        if history:
            try:
                search_query = normalize_years(await asyncio.wait_for(
                    rag_service.contextualize_query(message, history), timeout=6.0
                ))
            except TimeoutError:
                logger.warning("Query rewriting timed out; retaining original question")
        clarification = admission_clarification(search_query)
        if clarification:
            return clarification
        async def fast_query(query):
            try:
                return await self._fast_structured_question(query)
            except Exception:
                logger.warning("Fast structured routing unavailable", exc_info=True)
                return None

        if not self._requires_narrative(message) and await fast_query(search_query) is not None:
            return await self._fast_structured_messages(message, history, search_query=search_query)

        return await self._agentic_rag.prepare(
            message, history, search_query=search_query
        )
