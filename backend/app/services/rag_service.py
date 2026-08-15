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

    async def prepare(
        self,
        question: str,
        history=None,
    ) -> tuple[list[BaseMessage], list[SourceInfo]] | None:
        """检索并组装生成所需的消息与来源；无相关片段时返回 None。"""
        documents = await retriever_service.search(
            query=question,
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
