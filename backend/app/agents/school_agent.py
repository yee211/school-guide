import asyncio

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, BaseMessage

from app.prompts.school_prompt import SCHOOL_SYSTEM_PROMPT
from app.services.llm_service import llm_service
from app.services.rag_service import RAGResult, SourceInfo, rag_service
from app.structured.query import query_admission_data, structured_query_service


class SchoolAgent:
    """路由 agent：LLM 意图识别，结构化问题走数据库 tool，否则走 RAG。"""

    def __init__(self) -> None:
        self._llm_tools = llm_service.with_tools([query_admission_data])

    async def chat(self, message: str) -> RAGResult:
        messages: list[BaseMessage] = [
            SystemMessage(content=SCHOOL_SYSTEM_PROMPT),
            HumanMessage(content=message),
        ]

        response = await self._llm_tools.ainvoke(messages)

        if not response.tool_calls:
            return await rag_service.answer(message)

        messages.append(response)
        sources: list[SourceInfo] = []
        seen_sources: set[str] = set()

        for tool_call in response.tool_calls:
            if tool_call["name"] != "query_admission_data":
                continue
            question = tool_call.get("args", {}).get("question") or message
            result = await asyncio.to_thread(
                structured_query_service.query_and_format,
                question,
            )
            # 结构化查询无有效结果时回退 RAG（避免误判意图后卡在空结果）
            if not result.score_rows and not result.plan_rows:
                return await rag_service.answer(message)
            messages.append(
                ToolMessage(
                    content=result.format_context(),
                    tool_call_id=tool_call["id"],
                )
            )
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

        final_answer = await llm_service.invoke(messages)
        return RAGResult(answer=final_answer, sources=sources)


school_agent = SchoolAgent()
