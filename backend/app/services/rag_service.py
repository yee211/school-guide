from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage

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

    async def answer(self, question: str) -> RAGResult:
        documents = await retriever_service.search(
            query=question,
            top_k=5,
        )

        if not documents:
            return RAGResult(
                answer="根据目前的学校资料，我暂时无法回答这个问题。",
                sources=[],
            )

        context = self._format_context(documents)

        rag_message = RAG_INPUT_TEMPLATE.format(
            context=context,
            question=question,
        )

        messages = [
            SystemMessage(content=SCHOOL_SYSTEM_PROMPT),
            HumanMessage(content=rag_message),
        ]

        answer = await llm_service.invoke(messages)

        return RAGResult(
            answer=answer,
            sources=self._build_sources(documents),
        )


rag_service = RAGService()
