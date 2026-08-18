import asyncio

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.prompts.school_prompt import SCHOOL_SYSTEM_PROMPT
from app.rag.metadata import infer_retrieval_filters
from app.services.rag_service import SourceInfo, rag_service
from app.structured.query import query_admission_data, structured_query_service


class QueryRouter:
    """根据消息+历史决定走结构化查询还是 RAG，并组装生成所需的消息与来源。

    三条互斥分支（按优先级）：
    1. 规则快通道：消息自包含结构化问题 → 直接查库，跳过意图 LLM
    2. 意图 LLM：模型决定是否调用 query_admission_data
    3. RAG 兜底：开放性问答

    对外入口 prepare 返回 ``(gen_messages, sources)``；返回 None 表示无内容可答。
    """

    def __init__(self, llm_tools) -> None:
        # 由 SchoolAgent 注入已绑定工具的意图 LLM
        self._llm_tools = llm_tools

    @staticmethod
    def _history_to_messages(history) -> list[BaseMessage]:
        """把前端传来的历史对话转成 LangChain 消息，让 agent 记住上下文。"""
        messages: list[BaseMessage] = []
        for item in history or ():
            if item.role == "user":
                messages.append(HumanMessage(content=item.content))
            else:
                messages.append(AIMessage(content=item.content))
        return messages

    @staticmethod
    async def _fast_structured_question(message: str) -> str | None:
        """规则快通道：消息本身已是自包含的结构化问题（专业/专业组 + 分数/计划关键词）。

        只有同时命中「专业或专业组」且「录取分数/招生计划」关键词才触发，直接返回查询串；
        否则（含「湖南」这类需合并上一轮上下文的补充追问、缩写专业）返回 None，交给意图 LLM。
        """
        catalog = await asyncio.to_thread(structured_query_service.get_catalog)
        filters = infer_retrieval_filters(message, catalog)
        targeted = bool(filters.majors or filters.groups)
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
    ) -> tuple[list[BaseMessage], list[SourceInfo]] | None:
        """快通道命中时合成 AIMessage+ToolMessage，复用与工具调用一致的生成格式。"""
        tool_call_id = "fast_structured"
        tool_result = await self._structured_tool_result(message, tool_call_id)
        if tool_result is None:
            return await rag_service.prepare(message, history)

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
                        "args": {"question": message},
                        "id": tool_call_id,
                        "type": "tool_call",
                    }
                ],
            ),
            tool_message,
        ]
        return base_messages, sources

    async def _prepare_generation(
        self,
        message: str,
        history,
        response,
    ) -> tuple[list[BaseMessage], list[SourceInfo]] | None:
        """准备最终生成的 messages 与来源；返回 None 表示无内容可答。"""
        if not response.tool_calls:
            return await rag_service.prepare(message, history)

        base_messages: list[BaseMessage] = [
            SystemMessage(content=SCHOOL_SYSTEM_PROMPT),
            *self._history_to_messages(history),
            HumanMessage(content=message),
            response,
        ]
        sources: list[SourceInfo] = []

        for tool_call in response.tool_calls:
            if tool_call["name"] != "query_admission_data":
                continue
            question = tool_call.get("args", {}).get("question") or message
            tool_result = await self._structured_tool_result(
                question,
                tool_call["id"],
            )
            if tool_result is None:
                return await rag_service.prepare(message, history)
            base_messages.append(tool_result[0])
            sources.extend(tool_result[1])

        return base_messages, sources

    async def prepare(
        self,
        message: str,
        history=None,
    ) -> tuple[list[BaseMessage], list[SourceInfo]] | None:
        """路由并组装生成所需的消息与来源；返回 None 表示无内容可答。"""
        if await self._fast_structured_question(message) is not None:
            return await self._fast_structured_messages(message, history)

        messages: list[BaseMessage] = [
            SystemMessage(content=SCHOOL_SYSTEM_PROMPT),
            *self._history_to_messages(history),
            HumanMessage(content=message),
        ]
        response = await self._llm_tools.ainvoke(messages)
        return await self._prepare_generation(message, history, response)
