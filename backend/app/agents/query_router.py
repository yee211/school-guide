import asyncio
import logging

from langchain_core.messages import (
    BaseMessage,
)

from app.agents.answer_requirements import Clarification, admission_clarification, normalize_years
from app.agents.agentic_rag import AgenticRAG
from app.services.rag_service import SourceInfo, rag_service


logger = logging.getLogger(__name__)


class QueryRouter:
    """补全问题并检查必要条件，所有可检索请求统一进入 Agentic RAG。

    保留 QueryRouter 名称以兼容调用方，不再通过规则绕过 Agent。
    """

    def __init__(self, llm_tools, coverage_checker=None) -> None:
        # 由 SchoolAgent 注入绑定两类检索工具的规划模型
        self._agentic_rag = AgenticRAG(llm_tools, coverage_checker=coverage_checker)

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
        return await self._agentic_rag.prepare(
            message, history, search_query=search_query
        )
