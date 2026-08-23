from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.prompts.rag_prompt import RAG_INPUT_TEMPLATE
from app.prompts.school_prompt import SCHOOL_SYSTEM_PROMPT
from app.rag.retriever import retriever_service
from app.services.llm_service import llm_service

@dataclass(frozen=True)
class SourceInfo:
    title: str
    source: str


@dataclass(frozen=True)
class RAGResult:
    answer: str
    sources: list[SourceInfo]

class RAGService:
    @staticmethod
    def _format_context(documents: list[Document]) -> str:
        formatted_documents: list[str] = []

        for index, document in enumerate(documents, start=1):
            source = document.metadata.get("source", "未知来源")

            formatted_documents.append(
                f"[资料 {index}]\n"
                f"来源：{source}\n"
                f"内容：{document.page_content}"
            )

        return "\n\n".join(formatted_documents)

    @staticmethod
    def _build_sources(documents: list[Document]) -> list[SourceInfo]:
        sources: list[SourceInfo] = []
        seen_sources: set[str] = set()

        for document in documents:
            source = str(document.metadata.get("source", "未知来源"))

            # 同一个文件可能检索到多个片段，只返回一次
            if source in seen_sources:
                continue

            seen_sources.add(source)

            sources.append(
                SourceInfo(
                    title=str(document.metadata.get("title", "未知资料")),
                    source=source,
                )
            )

        return sources

    @staticmethod
    def _history_to_messages(history) -> list[BaseMessage]:
        messages: list[BaseMessage] = []
        for item in history or ():
            if item.role == "user":
                messages.append(HumanMessage(content=item.content))
            else:
                messages.append(AIMessage(content=item.content))
        return messages

    @staticmethod
    async def contextualize_query(question: str, history=None) -> str:
        """如果存在多轮历史，将指代/省略句改写为自包含检索 Query。"""
        if not history:
            return question.strip()

        recent = history[-4:] if len(history) > 4 else history
        conv_text = "\n".join(
            f"{item.role}: {item.content}" for item in recent
        )
        prompt = [
            SystemMessage(
                content=(
                    "你是一个搜索查询改写助手。根据对话历史，将用户最新的简短提问改写为一个自包含、语义完整的搜索语句，用于在长沙工业学院知识库中检索。\n"
                    "规则：\n"
                    "1. 补全省略的主语（如专业名称、设施、部门或场景）；\n"
                    "2. 消除代词指代（如'这个专业'、'那学费呢'、'有空调吗'）；\n"
                    "3. 保持简练，直接输出改写后的检索语句，不要输出任何问候或解释；\n"
                    "4. 若当前提问本身已自包含，直接输出原句。"
                )
            ),
            HumanMessage(
                content=f"对话历史：\n{conv_text}\n\n最新提问：{question}\n\n改写后的检索语句："
            ),
        ]
        try:
            rewritten = await llm_service.invoke(prompt)
            cleaned = rewritten.strip().strip('"').strip("'")
            if cleaned and len(cleaned) <= 100:
                return cleaned
        except Exception:
            pass
        return question.strip()

    async def prepare(
        self,
        question: str,
        history=None,
    ) -> tuple[list[BaseMessage], list[SourceInfo]] | None:
        """检索并组装生成所需的消息与来源；无相关片段时返回 None。"""
        search_query = await self.contextualize_query(question, history)
        documents = await retriever_service.search(
            query=search_query,
            top_k=5,
        )

        if not documents:
            return None

        context = self._format_context(documents)

        rag_message = RAG_INPUT_TEMPLATE.format(
            context=context,
            question=question,
        )

        messages = [
            SystemMessage(content=SCHOOL_SYSTEM_PROMPT),
            *self._history_to_messages(history),
            HumanMessage(content=rag_message),
        ]

        return messages, self._build_sources(documents)


    async def answer(self, question: str, history=None) -> RAGResult:
        prepared = await self.prepare(question, history)

        if prepared is None:
            return RAGResult(
                answer="根据目前的学校资料，我暂时无法回答这个问题。",
                sources=[],
            )

        messages, sources = prepared
        answer = await llm_service.invoke(messages)

        return RAGResult(
            answer=answer,
            sources=sources,
        )


rag_service = RAGService()
